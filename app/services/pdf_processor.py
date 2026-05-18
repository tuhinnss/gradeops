"""PDF to image conversion and page metadata."""

import logging
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from PIL import Image

from app.config import get_settings
from app.services.image_preprocess import preprocess_for_ocr

logger = logging.getLogger(__name__)


@dataclass
class PageImage:
    page_index: int
    image: Image.Image
    width: int
    height: int
    pdf_rect: tuple[float, float, float, float]


class PDFProcessor:
    """Convert PDF pages to high-resolution images using PyMuPDF."""

    def __init__(self, dpi: int | None = None):
        settings = get_settings()
        self.dpi = dpi or settings.pdf_dpi
        self.zoom = self.dpi / 72.0

    def get_page_count(self, pdf_path: Path) -> int:
        with fitz.open(pdf_path) as doc:
            return len(doc)

    def pdf_to_images(self, pdf_path: Path) -> list[PageImage]:
        settings = get_settings()
        pages: list[PageImage] = []
        matrix = fitz.Matrix(self.zoom, self.zoom)

        with fitz.open(pdf_path) as doc:
            for idx, page in enumerate(doc):
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                if settings.ocr_preprocess:
                    img = preprocess_for_ocr(img, enabled=True)
                rect = page.rect
                pages.append(
                    PageImage(
                        page_index=idx,
                        image=img,
                        width=pix.width,
                        height=pix.height,
                        pdf_rect=(rect.x0, rect.y0, rect.x1, rect.y1),
                    )
                )
        logger.info("Converted %s to %d page images at %d DPI", pdf_path.name, len(pages), self.dpi)
        return pages

    @staticmethod
    def pil_to_numpy(image: Image.Image) -> np.ndarray:
        return np.array(image.convert("RGB"))

    @staticmethod
    def save_page_preview(image: Image.Image, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, format="PNG")
        return output_path
