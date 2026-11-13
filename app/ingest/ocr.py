import re

import numpy as np
import pypdfium2 as pdfium
import wordninja

_engine = None


def _ocr():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def _unglue(line: str) -> str:
    """OCR drops spaces ('secondquarterof2026'); split long glued alphabetic runs."""
    def fix(tok):
        if len(tok) > 14 and tok.isalnum():
            return " ".join(wordninja.split(tok))
        return tok
    return " ".join(fix(t) for t in line.split())


def ocr_pages(path) -> list:
    pdf = pdfium.PdfDocument(str(path))
    pages = []
    for i in range(len(pdf)):
        img = np.array(pdf[i].render(scale=2).to_pil().convert("RGB"))
        res, _ = _ocr()(img)
        pages.append("\n".join(_unglue(r[1]) for r in (res or [])))
    return pages


def ocr_pdf(path) -> str:
    return "\n\n".join(ocr_pages(path))
