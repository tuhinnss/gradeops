"""Tesseract OCR fallback."""

import logging

import pytesseract
from PIL import Image

from app.services.ocr.base import BaseOCR, OCRResult

logger = logging.getLogger(__name__)


class TesseractOCR(BaseOCR):
    name = "tesseract"

    def __init__(self, lang: str = "eng"):
        self.lang = lang

    def is_available(self) -> bool:
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            logger.warning("Tesseract not found on PATH")
            return False

    def extract(self, image: Image.Image) -> OCRResult:
        data = pytesseract.image_to_data(
            image, lang=self.lang, output_type=pytesseract.Output.DICT
        )
        texts = []
        confidences = []
        for i, word in enumerate(data["text"]):
            if word.strip():
                texts.append(word)
                conf = float(data["conf"][i])
                if conf >= 0:
                    confidences.append(conf / 100.0)

        text = " ".join(texts).strip()
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.3
        if not text:
            text = pytesseract.image_to_string(image, lang=self.lang).strip()
            avg_conf = 0.25 if text else 0.0

        return OCRResult(text=text, confidence=avg_conf, engine=self.name)
