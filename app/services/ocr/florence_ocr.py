"""Florence-2 vision model for handwritten OCR."""

import logging

import torch
from PIL import Image
from transformers import AutoModelForCausalLM, AutoProcessor

from app.config import get_settings
from app.services.ocr.base import BaseOCR, OCRResult

logger = logging.getLogger(__name__)


class Florence2OCR(BaseOCR):
    name = "florence2"
    _model = None
    _processor = None

    def __init__(self):
        settings = get_settings()
        self.model_id = settings.florence_model_id
        self.device = settings.ocr_device
        if self.device == "cuda" and not torch.cuda.is_available():
            self.device = "cpu"

    def _load(self) -> None:
        if Florence2OCR._model is not None:
            return
        logger.info("Loading Florence-2 model: %s on %s", self.model_id, self.device)
        Florence2OCR._processor = AutoProcessor.from_pretrained(
            self.model_id, trust_remote_code=True
        )
        Florence2OCR._model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            trust_remote_code=True,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
        ).to(self.device)
        Florence2OCR._model.eval()

    def is_available(self) -> bool:
        try:
            import transformers  # noqa: F401

            return True
        except ImportError:
            return False

    def extract(self, image: Image.Image) -> OCRResult:
        self._load()
        assert Florence2OCR._model is not None and Florence2OCR._processor is not None

        if image.mode != "RGB":
            image = image.convert("RGB")

        task_prompt = "<OCR>"
        inputs = Florence2OCR._processor(
            text=task_prompt, images=image, return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            generated_ids = Florence2OCR._model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=1024,
                num_beams=3,
                do_sample=False,
            )

        generated_text = Florence2OCR._processor.batch_decode(
            generated_ids, skip_special_tokens=False
        )[0]
        parsed = Florence2OCR._processor.post_process_generation(
            generated_text, task=task_prompt, image_size=image.size
        )
        text = ""
        if isinstance(parsed, dict):
            text = parsed.get("<OCR>", "") or parsed.get("ocr", "") or str(parsed)
        else:
            text = str(parsed)

        text = text.strip()
        confidence = 0.75 if len(text) > 10 else 0.45 if text else 0.0
        return OCRResult(text=text, confidence=confidence, engine=self.name)
