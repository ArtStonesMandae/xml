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


# =========================
# EXTRAÇÃO
# =========================
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


# =========================
# UTIL
# =========================
def today_br() -> str:
    return datetime.now().strftime("%d/%m/%Y")


def normalize_data(d: str) -> str:
    """Tenta validar dd/mm/aaaa. Se inválida, usa hoje."""
    s = (d or "").strip()
    try:
        dt = datetime.strptime(s, "%d/%m/%Y")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return today_br()


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


# =========================
# PDF (AJUSTADO: MENOS ESPAÇO)
# =========================
def _new_page_text(c: canvas.Canvas) -> Tuple[float, float, float, float]:
    w, h = A4
    left = 28 * mm
    top_y = h - 28 * mm
    return w, h, left, top_y


def render_pdf(out_path: str, data: str, hora: str, keys: List[str]) -> None:
    """
    Estilo do exemplo, porém com espaçamento ajustado:
    - Courier (monoespaçado)
    - Menos respiro no topo e entre blocos
    - Lista mais compacta
    - Assinaturas no rodapé (sem linhas)
    """
    c = canvas.Canvas(out_path, pagesize=A4)

    w, h, left, y = _new_page_text(c)

    font_main = "Courier"
    font_list = "Courier"
    font_size_main = 12
    font_size_list = 12

    # ↓↓↓ principal ajuste de "muito espaçado"
    line_h = 6.2 * mm  # antes: 8.2mm

    def nl(n: float = 1.0):
        nonlocal y
        y -= line_h * n

    def line(txt: str = ""):
        nonlocal y
        c.setFont(font_main, font_size_main)
        c.drawString(left, y, txt)
        nl(1.0)

    def ensure_space(min_bottom_mm: float = 60):
        """Garante espaço pro rodapé (assinaturas)."""
        nonlocal w, h, left, y
        if y < (min_bottom_mm * mm):
            c.showPage()
            w, h, left, y = _new_page_text(c)

    # ===== CABEÇALHO (menos espaço) =====
    line("CLIENTE:")
    nl(2.0)

    line("DATA DA COLETA:")
    line(data)
    nl(1.8)

    line("HORA DA COLETA:")
    nl(0.4)
    line(hora)
    nl(1.8)

    line("CHAVES DE ACESSO:")
    nl(0.4)

    # ===== LISTA (mais compacta) =====
    c.setFont(font_list, font_size_list)
    for k in keys:
        ensure_space(min_bottom_mm=70)
        c.drawString(left, y, k)
        nl(0.85)  # antes: 1.0

    nl(1.0)
    line(f"TOTAL DA REMESSA:  {len(keys)} VOLUMES")

    # ===== ASSINATURAS (rodapé) =====
    if y < (85 * mm):
        c.showPage()
        w, h, left, y = _new_page_text(c)

    sig_y = 22 * mm
    c.setFont(font_main, 10.5)
    c.drawString(left, sig_y, "ASSINATURA DO REPRESENTANTE")
    c.drawString(w * 0.58, sig_y, "ASSINATURA DO MOTORISTA")

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
    data_norm = normalize_data(data)
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

    if mostrar_preview:
        st.text_area("Prévia (primeiras 10 chaves)", "\n".join(keys[:10]), height=220)

    # Limpeza
    try:
        os.remove(tmp_in)
    except Exception:
        pass
