"""OCR image preprocessing — denoise, contrast, deskew."""

import logging

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def preprocess_for_ocr(image: Image.Image, enabled: bool = True) -> Image.Image:
    """Enhance page images before OCR when preprocessing is enabled."""
    if not enabled:
        return image

    try:
        arr = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        gray = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        rgb = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)
        return Image.fromarray(rgb)
    except Exception as exc:
        logger.debug("Preprocess skipped: %s", exc)
        return image
