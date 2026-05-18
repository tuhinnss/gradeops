"""Unified OCR service with engine selection, cleanup, and fallback chain."""

import logging
from typing import Any

from PIL import Image, ImageEnhance

from app.config import get_settings
from app.core.exceptions import OCRProcessingError
from app.services.ocr.base import BaseOCR, OCRResult
from app.services.ocr.florence_ocr import Florence2OCR
from app.services.ocr.nougat_ocr import NougatOCR
from app.services.ocr.tesseract_ocr import TesseractOCR
from app.services.text_utils import adjust_ocr_confidence, clean_ocr_text, is_noise_fragment

logger = logging.getLogger(__name__)


class OCRService:
    """
    OCR facade: primary engine from settings, fallback to Tesseract.

    Post-processes text (cleanup + confidence). Light image preprocessing
    improves handwritten readability without heavy models.
    """

    def __init__(self):
        settings = get_settings()
        self.primary_name = settings.ocr_engine
        self._engines: dict[str, Any] = {
            "florence2": Florence2OCR(),
            "nougat": NougatOCR(),
            "tesseract": TesseractOCR(),
        }
        self._fallback_chain = self._build_chain()

    def _build_chain(self) -> list:
        order = [self.primary_name]
        for name in ("florence2", "nougat", "tesseract"):
            if name not in order:
                order.append(name)
        chain = []
        for name in order:
            engine = self._engines.get(name)
            if engine and engine.is_available():
                chain.append(engine)
        if not chain:
            raise OCRProcessingError(
                "No OCR engine available. Install Tesseract or transformers models."
            )
        return chain

    @staticmethod
    def preprocess_image(image: Image.Image) -> Image.Image:
        """Lightweight contrast/sharpen for handwritten scans (low RAM)."""
        img = image.convert("RGB")
        w, h = img.size
        # Downscale very large pages to speed OCR on weak hardware
        max_side = 2000
        if max(w, h) > max_side:
            scale = max_side / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        # Contrast/sharpen only — avoids slow filters on large pages (low RAM)
        img = ImageEnhance.Contrast(img).enhance(1.12)
        return ImageEnhance.Sharpness(img).enhance(1.08)

    def extract_text(self, image: Image.Image) -> OCRResult:
        image = self.preprocess_image(image)
        last_error: Exception | None = None

        for engine in self._fallback_chain:
            try:
                result = engine.extract(image)
                if result.text or engine.name == "tesseract":
                    text = clean_ocr_text(result.text)
                    conf = adjust_ocr_confidence(result.confidence, text)
                    if is_noise_fragment(text):
                        conf = min(conf, 0.3)
                    logger.debug(
                        "OCR %s conf=%.2f len=%d",
                        engine.name,
                        conf,
                        len(text),
                    )
                    return OCRResult(text=text, confidence=conf, engine=engine.name)
            except Exception as exc:
                logger.warning("OCR engine %s failed: %s", engine.name, exc)
                last_error = exc

        raise OCRProcessingError(
            f"All OCR engines failed. Last error: {last_error}",
            details={"engines_tried": [e.name for e in self._fallback_chain]},
        )

    def extract_batch(self, images: list[Image.Image]) -> list[OCRResult]:
        return [self.extract_text(img) for img in images]

    def is_blank(self, text: str) -> bool:
        settings = get_settings()
        cleaned = clean_ocr_text(text)
        alnum = "".join(c for c in cleaned if c.isalnum())
        if len(alnum) < settings.blank_answer_min_chars:
            return True
        if is_noise_fragment(cleaned):
            return True
        return False
