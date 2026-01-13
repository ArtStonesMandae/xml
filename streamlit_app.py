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
# PDF HELPERS
# =========================
def _page_geometry() -> Tuple[float, float, float, float, float]:
    """
    Retorna: (w, h, left, right, top)
    """
    w, h = A4
    left = 16 * mm
    right = 16 * mm
    top = h - 16 * mm
    return w, h, left, right, top


def _fit_font_size_for_column(text_sample: str, col_width: float, font: str, max_size: float) -> float:
    size = max_size
    while size >= 7.0:
        if pdfmetrics.stringWidth(text_sample, font, size) <= col_width:
            return size
        size -= 0.2
    return 7.0


def _pages_for(n_items: int, cols: int, lines_per_col: int) -> int:
    per_page = max(1, cols * max(1, lines_per_col))
    return (n_items + per_page - 1) // per_page


def _choose_columns_and_font(
    keys: List[str],
    w: float,
    left: float,
    right: float,
    gutter: float,
    lines_per_col: int,
    font: str,
    max_font: float,
    min_font_ok: float = 8.5,
) -> Tuple[int, float, float]:
    """
    Decide 2 ou 3 colunas.
    Só aceita 3 colunas se:
    - reduzir páginas E
    - a fonte ficar >= min_font_ok (pra não “invadir” outra coluna)
    """
    sample = max(keys, key=len) if keys else "0" * 44

    # 2 colunas
    avail2 = w - left - right - gutter * 1
    col_w2 = avail2 / 2
    size2 = _fit_font_size_for_column(sample, col_w2, font, max_font)
    pages2 = _pages_for(len(keys), 2, lines_per_col)

    # 3 colunas
    avail3 = w - left - right - gutter * 2
    col_w3 = avail3 / 3
    size3 = _fit_font_size_for_column(sample, col_w3, font, max_font)
    pages3 = _pages_for(len(keys), 3, lines_per_col)

    if size3 >= min_font_ok and pages3 < pages2:
        return 3, size3, col_w3

    return 2, size2, col_w2


# =========================
# PDF (FINAL)
# =========================
def render_pdf(out_path: str, data: str, hora: str, keys: List[str]) -> None:
    c = canvas.Canvas(out_path, pagesize=A4)

    w, h, left, right, top = _page_geometry()

    font_main = "Courier"
    font_list = "Courier"

    line_h = 6.0 * mm

    # ----- Rodapé fixo (assinaturas) -----
    sig_line_y = 22 * mm        # linha das assinaturas
    label_y = sig_line_y - 8    # texto abaixo da linha
    sig_block_top = sig_line_y + 6 * mm  # “topo” do bloco de assinatura

    # TOTAL sempre acima das assinaturas (e nunca vai pra outra página “à toa”)
    total_min_y = sig_block_top + 10 * mm

    # Espaço mínimo entre última chave e TOTAL
    gap_keys_to_total = 1.8

    # Gutter maior evita colunas “coladas”
    gutter = 16 * mm

    y = top

    def new_page_repeat_title():
        nonlocal y, w, h, left, right, top
        c.showPage()
        w, h, left, right, top = _page_geometry()
        y = top
        c.setFont(font_main, 11)
        c.drawString(left, y, "CHAVES DE ACESSO:")
        y -= line_h * 1.1

    # =========================
    # HEADER COM CAIXAS
    # =========================
    header_h = 9 * mm
    c.rect(left, y - header_h + 2, w - left - right, header_h, stroke=1, fill=0)
    c.setFont(font_main, 11)
    c.drawString(left + 3 * mm, y - 6 * mm, f"CLIENTE:  ArtStones     DATA DA COLETA:  {data}")
    y -= header_h + 4 * mm

    box_w = 55 * mm
    box_h = 22 * mm
    c.rect(left, y - box_h, box_w, box_h, stroke=1, fill=0)
    c.setFont(font_main, 11)
    c.drawString(left + 3 * mm, y - 7 * mm, "HORA DA COLETA:")
    c.drawString(left + 3 * mm, y - 16 * mm, hora)

    # Espaçamento maior antes das chaves
    y -= box_h + 12 * mm

    c.setFont(font_main, 11)
    c.drawString(left, y, "CHAVES DE ACESSO:")
    y -= line_h * 1.0

    # =========================
    # LISTA EM COLUNAS
    # =========================
    list_line_h = 5.0 * mm

    # Aqui é o ponto-chave: a lista pode descer até “logo acima do TOTAL”
    # (que por sua vez é logo acima das assinaturas).
    list_bottom = total_min_y + (list_line_h * 1.0)

    usable_h = y - list_bottom
    lines_per_col = max(1, int(usable_h // list_line_h))

    cols, list_size, col_w = _choose_columns_and_font(
        keys=keys,
        w=w,
        left=left,
        right=right,
        gutter=gutter,
        lines_per_col=lines_per_col,
        font=font_list,
        max_font=10.0,
        min_font_ok=8.5,
    )

    idx = 0
    lowest_y_on_page = y

    while idx < len(keys):
        page_start_y = y
        lowest_y_on_page = y

        for col in range(cols):
            x = left + col * (col_w + gutter)
            yy = page_start_y
            c.setFont(font_list, list_size)

            for _ in range(lines_per_col):
                if idx >= len(keys):
                    break
                c.drawString(x, yy, keys[idx])
                lowest_y_on_page = min(lowest_y_on_page, yy)
                yy -= list_line_h
                idx += 1

            if idx >= len(keys):
                break

        if idx < len(keys):
            new_page_repeat_title()
            usable_h = y - list_bottom
            lines_per_col = max(1, int(usable_h // list_line_h))

    # =========================
    # TOTAL (sempre na mesma página, acima das assinaturas)
    # =========================
    total_y = lowest_y_on_page - (list_line_h * gap_keys_to_total)
    total_y = max(total_y, total_min_y)  # garante que não invade assinaturas

    c.setFont(font_main, 11)
    c.drawString(left, total_y, f"TOTAL DA REMESSA:  {len(keys)} VOLUMES")

    # =========================
    # ASSINATURAS (linha acima, texto abaixo)
    # =========================
    c.line(left, sig_line_y, w * 0.45, sig_line_y)
    c.line(w * 0.58, sig_line_y, w - right, sig_line_y)

    c.setFont(font_main, 10)
    c.drawString(left, label_y, "ASSINATURA DO REPRESENTANTE")
    c.drawString(w * 0.58, label_y, "ASSINATURA DO MOTORISTA")

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
