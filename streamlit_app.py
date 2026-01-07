# Script completo atualizado:
# - Caixa (retângulo) envolvendo "CLIENTE + DATA" na 1ª linha
# - Caixa (retângulo) envolvendo "HORA DA COLETA + hora" (como no exemplo)
# - Espaçamento maior entre HORA e "CHAVES DE ACESSO:"
# - Mantém colunas 2/3, sem quebrar chaves, total perto do fim e assinaturas com linha acima

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
# PDF
# =========================
def _page_geometry() -> Tuple[float, float, float, float, float, float]:
    w, h = A4
    left = 18 * mm
    right = 18 * mm
    top = h - 18 * mm
    bottom_sig = 26 * mm
    return w, h, left, right, top, bottom_sig


def _fit_font_size_for_column(text_sample: str, col_width: float, font: str, max_size: float) -> float:
    size = max_size
    while size >= 7.5:
        if pdfmetrics.stringWidth(text_sample, font, size) <= col_width:
            return size
        size -= 0.2
    return 7.5


def _choose_columns(keys: List[str], lines_per_col: int) -> int:
    n = len(keys)
    per_page_2 = lines_per_col * 2
    pages_2 = (n + per_page_2 - 1) // per_page_2 if per_page_2 else 10**9
    per_page_3 = lines_per_col * 3
    pages_3 = (n + per_page_3 - 1) // per_page_3 if per_page_3 else 10**9
    return 3 if pages_3 < pages_2 else 2


def render_pdf(out_path: str, data: str, hora: str, keys: List[str]) -> None:
    c = canvas.Canvas(out_path, pagesize=A4)

    w, h, left, right, top, bottom_sig = _page_geometry()
    gutter = 10 * mm

    font_main = "Courier"
    font_list = "Courier"

    main_size = 11
    line_h = 6.0 * mm
    y = top

    def draw(txt: str, size: float = main_size):
        nonlocal y
        c.setFont(font_main, size)
        c.drawString(left, y, txt)
        y -= line_h

    def new_page_repeat_title():
        nonlocal y, w, h, left, right, top, bottom_sig
        c.showPage()
        w, h, left, right, top, bottom_sig = _page_geometry()
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
    c.drawString(left + 3 * mm, y - 6 * mm,
                 f"CLIENTE:  ArtStones     DATA DA COLETA:  {data}")
    y -= header_h + 4 * mm

    box_w = 55 * mm
    box_h = 22 * mm
    c.rect(left, y - box_h, box_w, box_h, stroke=1, fill=0)
    c.drawString(left + 3 * mm, y - 7 * mm, "HORA DA COLETA:")
    c.drawString(left + 3 * mm, y - 16 * mm, hora)
    y -= box_h + 12 * mm  # espaçamento maior aqui 👈

    c.setFont(font_main, 11)
    c.drawString(left, y, "CHAVES DE ACESSO:")
    y -= line_h * 1.0

    # =========================
    # LISTA EM COLUNAS
    # =========================
    list_bottom = bottom_sig + 22 * mm
    list_line_h = 5.0 * mm
    usable_h = y - list_bottom
    lines_per_col = max(1, int(usable_h // list_line_h))

    cols = _choose_columns(keys, lines_per_col)

    available_w = w - left - right - gutter * (cols - 1)
    col_w = available_w / cols

    sample = max(keys, key=len) if keys else "0" * 44
    list_size = _fit_font_size_for_column(sample, col_w, font_list, 10.0)

    idx = 0
    lowest_y_on_page = y  # 👈 controla o ponto mais baixo da lista

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
    # TOTAL DA REMESSA (AGORA CERTO)
    # =========================
    total_y = lowest_y_on_page - (list_line_h * 1.6)

    if total_y < (bottom_sig + 20 * mm):
        c.showPage()
        w, h, left, right, top, bottom_sig = _page_geometry()
        total_y = h - 30 * mm

    c.setFont(font_main, 11)
    c.drawString(left, total_y, f"TOTAL DA REMESSA:  {len(keys)} VOLUMES")

    # =========================
    # ASSINATURAS
    # =========================
    sig_line_y = 22 * mm
    label_y = sig_line_y - 8

    c.line(left, sig_line_y, w * 0.45, sig_line_y)
    c.line(w * 0.58, sig_line_y, w - right, sig_line_y)

    c.setFont(font_main, 10)
    c.drawString(left, label_y, "ASSINATURA DO REPRESENTANTE")
    c.drawString(w * 0.58, label_y, "ASSINATURA DO MOTORISTA")

    c.save()
