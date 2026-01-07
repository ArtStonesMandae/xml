import os
import re
from datetime import datetime
from typing import List, Tuple

import streamlit as st
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

KEY_RE = re.compile(r"\b\d{44}\b")


def extract_keys_from_pdf(pdf_path: str) -> List[str]:
    """Extrai chaves de 44 dígitos do PDF, removendo duplicadas e preservando ordem."""
    reader = PdfReader(pdf_path)
    keys: List[str] = []
    seen = set()

    for page in reader.pages:
        text = page.extract_text() or ""
        for k in KEY_RE.findall(text):
            if k not in seen:
                seen.add(k)
                keys.append(k)

    return keys


def today_br() -> str:
    return datetime.now().strftime("%d/%m/%Y")


def normalize_hora(h: str) -> str:
    """Mantém o padrão '_____ : _____' quando vazio/placeholder."""
    if not h or not h.strip():
        return "_____ : _____"
    s = h.strip()
    if s in {"_____ : _____", "_____:_____", "____ : ____"}:
        return "_____ : _____"
    return s


def write_txt(out_path: str, keys: List[str]) -> None:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(keys))
        f.write("\n")


def _new_page(c: canvas.Canvas) -> Tuple[float, float, float, float]:
    """Retorna (w, h, left, top_y) para nova página com margens fixas."""
    w, h = A4
    left = 30 * mm
    top_y = h - 30 * mm
    return w, h, left, top_y


def render_pdf(out_path: str, data: str, hora: str, keys: List[str]) -> None:
    """
    Gera PDF A4 pronto para imprimir, com layout 'arejado' no padrão do exemplo:
    - Espaços grandes entre blocos
    - Lista começa mais abaixo
    - Assinaturas alinhadas e com linhas
    """
    c = canvas.Canvas(out_path, pagesize=A4)

    w, h, left, y = _new_page(c)

    # Tipografia: o exemplo tem "cara de documento operacional".
    # Helvetica funciona bem; se quiser ainda mais "datilografado", troque para "Courier".
    font_main = "Helvetica"
    font_list = "Helvetica"

    line_h = 7.0 * mm  # altura base de linha (mais confortável)

    def spacer(lines: float = 1.0):
        nonlocal y
        y -= line_h * lines

    def draw_line(txt: str, size: float = 11, font: str = None):
        nonlocal y
        c.setFont(font or font_main, size)
        c.drawString(left, y, txt)
        y -= line_h

    def ensure_space(min_y_mm: float = 35):
        """Se y estiver perto do rodapé, cria nova página."""
        nonlocal w, h, left, y
        if y < (min_y_mm * mm):
            c.showPage()
            w, h, left, y = _new_page(c)

    # ===== CABEÇALHO (com respiro igual ao exemplo) =====
    draw_line("CLIENTE:", size=11)
    spacer(3.0)

    draw_line("DATA DA COLETA:", size=11)
    draw_line(data, size=11)
    spacer(3.0)

    draw_line("HORA DA COLETA:", size=11)
    draw_line(hora, size=11)
    spacer(2.5)

    # ===== LISTA =====
    draw_line("CHAVES DE ACESSO:", size=11)
    spacer(1.2)

    # Lista com tamanho levemente menor e espaçamento agradável
    c.setFont(font_list, 10.6)
    for k in keys:
        ensure_space(min_y_mm=40)
        c.drawString(left, y, k)
        y -= line_h * 0.95

    spacer(2.2)

    draw_line(f"TOTAL DA REMESSA:  {len(keys)} VOLUMES", size=11)

    # ===== ASSINATURAS NO RODAPÉ (sempre na última página) =====
    # Se o conteúdo ficou muito baixo, cria nova página para o rodapé ficar limpo.
    if y < (60 * mm):
        c.showPage()
        w, h, left, y = _new_page(c)

    sig_y = 25 * mm

    c.setFont(font_main, 9.5)
    c.drawCentredString(w * 0.35, sig_y + 12, "ASSINATURA DO REPRESENTANTE")
    c.drawCentredString(w * 0.75, sig_y + 12, "ASSINATURA DO MOTORISTA")

    # Linhas de assinatura
    c.line(w * 0.20, sig_y + 10, w * 0.50, sig_y + 10)
    c.line(w * 0.60, sig_y + 10, w * 0.90, sig_y + 10)

    c.save()


# =========================
# UI - Streamlit
# =========================
st.set_page_config(page_title="Extrator de Chaves NF-e", layout="centered")
st.title("Extrator de Chaves NF-e (PDF → PDF para imprimir)")

pdf = st.file_uploader("Envie o PDF", type=["pdf"])
data = st.text_input("Data da coleta", value=today_br())
hora = st.text_input("Hora da coleta", value="_____ : _____")

col1, col2 = st.columns(2)
with col1:
    gerar_txt = st.checkbox("Gerar TXT (opcional)", value=True)
with col2:
    mostrar_preview = st.checkbox("Mostrar prévia (10 primeiras chaves)", value=True)

if pdf is not None:
    st.caption(f"Arquivo: {pdf.name}")

if st.button("Gerar arquivos", disabled=(pdf is None)):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")

    # Em ambiente de servidor, /tmp é mais seguro.
    tmp_in = os.path.join("/tmp", f"entrada_{ts}.pdf")
    out_pdf = os.path.join("/tmp", f"Chaves_de_Acesso_{ts}.pdf")
    out_txt = os.path.join("/tmp", f"Chaves_{ts}.txt")

    # Salva o PDF enviado
    with open(tmp_in, "wb") as f:
        f.write(pdf.read())

    # Extrai chaves
    keys = extract_keys_from_pdf(tmp_in)
    if not keys:
        st.error("Não encontrei chaves de acesso (44 dígitos) no PDF.")
        try:
            os.remove(tmp_in)
        except Exception:
            pass
        st.stop()

    # Normaliza campos
    data_norm = (data or today_br()).strip()
    hora_norm = normalize_hora(hora)

    # Gera PDF final
    render_pdf(out_pdf, data_norm, hora_norm, keys)

    # TXT opcional
    if gerar_txt:
        write_txt(out_txt, keys)

    st.success(f"{len(keys)} chaves encontradas.")

    # Downloads
    with open(out_pdf, "rb") as f:
        st.download_button(
            "Baixar PDF pronto para imprimir",
            data=f,
            file_name=os.path.basename(out_pdf),
            mime="application/pdf",
        )

    if gerar_txt:
        with open(out_txt, "rb") as f:
            st.download_button(
                "Baixar TXT (opcional)",
                data=f,
                file_name=os.path.basename(out_txt),
                mime="text/plain",
            )

    # Prévia
    if mostrar_preview:
        st.text_area("Prévia (primeiras 10 chaves)", "\n".join(keys[:10]), height=220)

    # Limpeza
    try:
        os.remove(tmp_in)
    except Exception:
        pass
