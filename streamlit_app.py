import os
import re
from datetime import datetime
from typing import List, Tuple

import streamlit as st
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics

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
    s = (d or "").strip()
    try:
        dt = datetime.strptime(s, "%d/%m/%Y")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return today_br()


def normalize_hora(h: str) -> str:
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
# PDF (CLIENTE FIXO + DATA AO LADO + COLUNAS 2/3 SEM QUEBRAR TEXTO)
# =========================
def _page_geometry() -> Tuple[float, float, float, float, float, float]:
    """
    Retorna: (w, h, left, right, top, bottom)
    bottom já reserva área para TOTAL + assinaturas.
    """
    w, h = A4
    left = 18 * mm
    right = 18 * mm
    top = h - 18 * mm
    bottom = 42 * mm  # reserva rodapé (total + assinaturas)
    return w, h, left, right, top, bottom


def _fit_font_size_for_column(text_sample: str, col_width: float, font: str, max_size: float) -> float:
    """
    Escolhe um tamanho de fonte que NÃO estoure a coluna.
    Mantém o texto em 1 linha (sem quebra).
    """
    size = max_size
    while size >= 7.5:
        if pdfmetrics.stringWidth(text_sample, font, size) <= col_width:
            return size
        size -= 0.2
    return 7.5


def _choose_columns(keys: List[str], lines_per_col: int) -> int:
    """
    Regra prática:
    - tenta 2 colunas; se ainda ficar muito longo (muitas páginas), tenta 3.
    (3 colunas pode aumentar folhas em alguns casos, mas economiza quando o problema é largura/compactação.)
    """
    n = len(keys)
    # páginas com 2 colunas
    per_page_2 = lines_per_col * 2
    pages_2 = (n + per_page_2 - 1) // per_page_2

    # páginas com 3 colunas
    per_page_3 = lines_per_col * 3
    pages_3 = (n + per_page_3 - 1) // per_page_3

    # Preferência: 2 colunas sempre, exceto quando 3 reduzir páginas
    return 3 if pages_3 < pages_2 else 2


def render_pdf(out_path: str, data: str, hora: str, keys: List[str]) -> None:
    """
    Gera PDF:
    - CLIENTE fixo: ArtStones
    - DATA na mesma linha (ao lado)
    - Lista de chaves em 2 colunas; se 3 reduzir páginas, usa 3
    - Fonte menor para caber (nunca quebra a chave)
    - TOTAL + assinaturas no rodapé da última página
    """
    c = canvas.Canvas(out_path, pagesize=A4)

    w, h, left, right, top, bottom = _page_geometry()
    gutter = 10 * mm  # espaço entre colunas

    font_main = "Courier"
    font_list = "Courier"

    # Cabeçalho (compacto)
    main_size = 11
    line_h = 6.2 * mm

    y = top

    def line(txt: str, size: float = main_size):
        nonlocal y
        c.setFont(font_main, size)
        c.drawString(left, y, txt)
        y -= line_h

    # ===== CABEÇALHO =====
    # Cliente fixo + data ao lado (mesma linha)
    line(f"CLIENTE:  ArtStones     DATA DA COLETA:  {data}", size=11)
    y -= line_h * 0.6

    # Hora (mantém a estética do exemplo, mas sem excesso de espaço)
    line("HORA DA COLETA:", size=11)
    line(hora, size=11)
    y -= line_h * 0.8

    line("CHAVES DE ACESSO:", size=11)
    y -= line_h * 0.4

    # Área útil para colunas (do y atual até bottom)
    usable_h = y - bottom
    # Quantidade de linhas por coluna, com um espaçamento ligeiramente compacto
    list_line_h = 5.2 * mm
    lines_per_col = max(1, int(usable_h // list_line_h))

    # Define 2 ou 3 colunas
    cols = _choose_columns(keys, lines_per_col)

    # Largura da coluna
    available_w = w - left - right - gutter * (cols - 1)
    col_w = available_w / cols

    # Fonte da lista: escolhe tamanho que caiba na coluna (sem quebrar texto)
    sample = max(keys, key=len) if keys else "0" * 44
    list_size = _fit_font_size_for_column(sample, col_w, font_list, max_size=10.0)

    def new_page():
        nonlocal y, w, h, left, right, top, bottom, usable_h, lines_per_col
        c.showPage()
        w, h, left, right, top, bottom = _page_geometry()
        y = top

        # Repetir somente o título da seção na nova página (para economizar espaço)
        c.setFont(font_main, 11)
        c.drawString(left, y, "CHAVES DE ACESSO:")
        y -= line_h * 1.1

        usable_h = y - bottom
        lines_per_col = max(1, int(usable_h // list_line_h))

    # ===== LISTAGEM EM COLUNAS =====
    idx = 0
    while idx < len(keys):
        # por página
        for col in range(cols):
            x = left + col * (col_w + gutter)
            yy = y
            c.setFont(font_list, list_size)

            for _ in range(lines_per_col):
                if idx >= len(keys):
                    break
                # 1 chave por linha, sem quebra
                c.drawString(x, yy, keys[idx])
                yy -= list_line_h
                idx += 1

            if idx >= len(keys):
                break

        if idx < len(keys):
            new_page()

    # ===== RODAPÉ NA ÚLTIMA PÁGINA =====
    # TOTAL + assinaturas (sem linhas)
    c.setFont(font_main, 11)
    c.drawString(left, bottom + 18 * mm, f"TOTAL DA REMESSA:  {len(keys)} VOLUMES")

    sig_y = 18 * mm
    c.setFont(font_main, 10)
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

    with open(tmp_in, "wb") as f:
        f.write(pdf.read())

    keys = extract_keys_from_pdf(tmp_in)
    if not keys:
        st.error("Não encontrei chaves de acesso (44 dígitos) no PDF.")
        try:
            os.remove(tmp_in)
        except Exception:
            pass
        st.stop()

    data_norm = normalize_data(data)
    hora_norm = normalize_hora(hora)

    render_pdf(out_pdf, data_norm, hora_norm, keys)

    if gerar_txt:
        write_txt(out_txt, keys)

    st.success(f"{len(keys)} chaves encontradas.")

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

    try:
        os.remove(tmp_in)
    except Exception:
        pass
