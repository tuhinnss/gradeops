"""Nougat document OCR for academic/handwritten sheets."""

import logging

import torch
from PIL import Image
from transformers import NougatProcessor, VisionEncoderDecoderModel

from app.config import get_settings
from app.services.ocr.base import BaseOCR, OCRResult

logger = logging.getLogger(__name__)


class NougatOCR(BaseOCR):
    name = "nougat"
    _model = None
    _processor = None

    def __init__(self):
        settings = get_settings()
        self.model_id = settings.nougat_model_id
        self.device = settings.ocr_device
        if self.device == "cuda" and not torch.cuda.is_available():
            self.device = "cpu"

    def _load(self) -> None:
        if NougatOCR._model is not None:
            return
        logger.info("Loading Nougat model: %s on %s", self.model_id, self.device)
        NougatOCR._processor = NougatProcessor.from_pretrained(self.model_id)
        NougatOCR._model = VisionEncoderDecoderModel.from_pretrained(self.model_id)
        NougatOCR._model.to(self.device)
        NougatOCR._model.eval()

    def is_available(self) -> bool:
        try:
            from transformers import NougatProcessor  # noqa: F401

            return True
        except ImportError:
            return False

    def extract(self, image: Image.Image) -> OCRResult:
        self._load()
        assert NougatOCR._model is not None and NougatOCR._processor is not None

        if image.mode != "RGB":
            image = image.convert("RGB")

        pixel_values = NougatOCR._processor(image, return_tensors="pt").pixel_values.to(
            self.device
        )
        with torch.no_grad():
            outputs = NougatOCR._model.generate(
                pixel_values,
                max_length=2048,
                num_beams=2,
            )
        text = NougatOCR._processor.batch_decode(outputs, skip_special_tokens=True)[0]
        text = text.strip()
        confidence = 0.7 if len(text) > 10 else 0.4 if text else 0.0
        return OCRResult(text=text, confidence=confidence, engine=self.name)
