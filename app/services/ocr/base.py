"""Base OCR interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL import Image


@dataclass
class OCRResult:
    text: str
    confidence: float
    engine: str


class BaseOCR(ABC):
    name: str = "base"

    @abstractmethod
    def extract(self, image: Image.Image) -> OCRResult:
        pass

    def is_available(self) -> bool:
        return True
