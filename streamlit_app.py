import os
import re
from datetime import datetime
from typing import List

import streamlit as st
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

KEY_RE = re.compile(r"\b\d{44}\b")


def extract_keys_from_pdf(pdf_path: str) -> List[str]:
    reader = PdfReader(pdf_path)
    keys, seen = [], set()
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
    if not h or not h.strip():
        return "_____ : _____"
    s = h.strip()
    if s in {"_____ : _____", "_____:_____", "____ : ____"}:
        return "_____ : _____"
    return s


def render_pdf(out_path: str, data: str, hora: str, keys: List[str]):
    c = canvas.Canvas(out_path, pagesize=A4)
    _, h = A4

    left = 20 * mm
    top = h - 20 * mm
    lh = 6.2 * mm
    y = top

    def draw(txt: str, size=11):
        nonlocal y
        c.setFont("Helvetica", size)
        c.drawString(left, y, txt)
        y -= lh

    # Cabeçalho
    draw("CLIENTE:")
    y -= lh * 1.2

    draw("DATA DA COLETA:")
    draw(data)
    y -= lh * 0.6

    draw("HORA DA COLETA:")
    draw(hora)
    y -= lh * 0.8

    # Lista
    draw("CHAVES DE ACESSO:")
    y -= lh * 0.2

    c.setFont("Helvetica", 10.8)
    for k in keys:
        if y < 40 * mm:
            c.showPage()
            y = top
            c.setFont("Helvetica", 10.8)
        c.drawString(left, y, k)
        y -= lh * 0.85

    y -= lh * 0.8
    draw(f"TOTAL DA REMESSA:  {len(keys)} VOLUMES")

    # Assinaturas no rodapé
    if y < 55 * mm:
        c.showPage()

    y_sig = 25 * mm
    c.setFont("Helvetica", 9.5)
    c.drawString(left + 70 * mm, y_sig + 12, "ASSINATURA DO REPRESENTANTE")
    c.drawString(left + 140 * mm, y_sig + 12, "ASSINATURA DO MOTORISTA")
    c.line(left + 55 * mm, y_sig + 10, left + 118 * mm, y_sig + 10)
    c.line(left + 130 * mm, y_sig + 10, left + 193 * mm, y_sig + 10)

    c.save()


st.set_page_config(page_title="Extrator de Chaves NF-e", layout="centered")
st.title("Extrator de Chaves NF-e (PDF → PDF para imprimir)")

pdf = st.file_uploader("Envie o PDF", type=["pdf"])
data = st.text_input("Data da coleta", value=today_br())
hora = st.text_input("Hora da coleta", value="_____ : _____")

if st.button("Gerar arquivos", disabled=(pdf is None)):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    tmp_in = os.path.join(os.getcwd(), f"entrada_{ts}.pdf")
    with open(tmp_in, "wb") as f:
        f.write(pdf.read())

    keys = extract_keys_from_pdf(tmp_in)
    if not keys:
        st.error("Não encontrei chaves de acesso (44 dígitos) no PDF.")
    else:
        hora_norm = normalize_hora(hora)
        out_pdf = os.path.join(os.getcwd(), f"Chaves_de_Acesso_{ts}.pdf")
        out_txt = os.path.join(os.getcwd(), f"Chaves_{ts}.txt")

        render_pdf(out_pdf, (data or today_br()).strip(), hora_norm, keys)

        with open(out_txt, "w", encoding="utf-8") as f:
            f.write("\n".join(keys) + "\n")

        st.success(f"{len(keys)} chaves encontradas.")

        with open(out_pdf, "rb") as f:
            st.download_button(
                "Baixar PDF pronto para imprimir",
                data=f,
                file_name=os.path.basename(out_pdf),
                mime="application/pdf",
            )

        with open(out_txt, "rb") as f:
            st.download_button(
                "Baixar TXT (opcional)",
                data=f,
                file_name=os.path.basename(out_txt),
                mime="text/plain",
            )

        st.text_area("Prévia (primeiras 10 chaves)", "\n".join(keys[:10]), height=220)

    # limpeza do arquivo de entrada
    try:
        os.remove(tmp_in)
    except Exception:
        pass
