"""Question-wise answer segmentation using OpenCV and rubric-guided splitting."""

import logging
import re
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from app.services.text_utils import clean_ocr_text, normalize_question_label

logger = logging.getLogger(__name__)

# Line-start question markers in OCR text (same spirit as rubric parser)
OCR_QUESTION_RE = re.compile(
    r"(?:^|\n)\s*"
    r"(?:Q(?:uestion)?[\s\.\:\-]*(\d{1,2})|(\d{1,2})[\.\)]\s+[A-Za-z])",
    re.IGNORECASE,
)


@dataclass
class AnswerRegion:
    question_number: str
    page_index: int
    bbox: dict  # x0, y0, x1, y1 in pixel coords
    crop: Image.Image


class LayoutSegmenter:
    """
    Segment exam pages into question regions.

    Priority:
    1. Rubric-guided even split (most reliable when rubric is known).
    2. OCR-detected Q1, Q2, … markers with deduplication.
    3. Single full-page region only as last resort.
    """

    def __init__(self, min_region_height: int = 100):
        self.min_region_height = min_region_height

    def segment_page(
        self,
        image: Image.Image,
        page_index: int,
        full_page_text: str = "",
        expected_questions: list[str] | None = None,
    ) -> list[AnswerRegion]:
        full_page_text = clean_ocr_text(full_page_text)
        img_np = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape

        # When rubric defines questions, use structured split — avoids fake Q bands
        if expected_questions and len(expected_questions) >= 1:
            normalized = [
                normalize_question_label(q.replace("Q", "")) for q in expected_questions
            ]
            normalized = [q for q in normalized if q]
            if normalized:
                return self._split_evenly(image, page_index, normalized, h, w)

        marker_y_positions = self._find_question_markers(full_page_text, gray, h, w)
        if marker_y_positions:
            regions = self._split_by_markers(
                image, page_index, marker_y_positions, h, w
            )
            if regions:
                return self._dedupe_regions(regions)

        # Full page as single answer only — never invent Q1..Qn from noise bands
        return [
            AnswerRegion(
                question_number="Q1",
                page_index=page_index,
                bbox={"x0": 0, "y0": 0, "x1": w, "y1": h},
                crop=image.copy(),
            )
        ]

    def _find_question_markers(
        self, text: str, gray: np.ndarray, height: int, width: int
    ) -> list[tuple[str, int]]:
        """Find question labels in OCR; map to approximate vertical positions."""
        seen: dict[str, int] = {}

        for m in OCR_QUESTION_RE.finditer(text):
            num_str = m.group(1) or m.group(2)
            if not num_str:
                continue
            label = normalize_question_label(num_str)
            if not label or label in seen:
                continue
            seen[label] = len(seen)

        if not seen:
            return []

        # Spread markers evenly — OCR rarely gives pixel Y; order is reliable
        n = len(seen)
        ordered = sorted(seen.items(), key=lambda x: int(x[0].replace("Q", "")))
        step = max(height // (n + 1), self.min_region_height)
        return [
            (label, min(step * (i + 1), height - 1))
            for i, (label, _) in enumerate(ordered)
        ]

    def _dedupe_regions(self, regions: list[AnswerRegion]) -> list[AnswerRegion]:
        """Keep one region per question number (largest area)."""
        best: dict[str, AnswerRegion] = {}
        for r in regions:
            label = normalize_question_label(r.question_number.replace("Q", ""))
            if not label:
                continue
            r.question_number = label
            prev = best.get(label)
            if prev is None:
                best[label] = r
            else:
                area_prev = (prev.bbox["y1"] - prev.bbox["y0"]) * (
                    prev.bbox["x1"] - prev.bbox["x0"]
                )
                area_r = (r.bbox["y1"] - r.bbox["y0"]) * (r.bbox["x1"] - r.bbox["x0"])
                if area_r > area_prev:
                    best[label] = r
        return sorted(
            best.values(),
            key=lambda x: int(x.question_number.replace("Q", "")),
        )

    def _split_by_markers(
        self,
        image: Image.Image,
        page_index: int,
        markers: list[tuple[str, int]],
        height: int,
        width: int,
    ) -> list[AnswerRegion]:
        regions: list[AnswerRegion] = []
        sorted_markers = sorted(markers, key=lambda m: m[1])

        for i, (qnum, y_start) in enumerate(sorted_markers):
            y_end = sorted_markers[i + 1][1] if i + 1 < len(sorted_markers) else height
            y_start = max(0, y_start - 10)
            y_end = min(height, y_end)
            if y_end - y_start < self.min_region_height:
                continue
            crop = image.crop((0, y_start, width, y_end))
            regions.append(
                AnswerRegion(
                    question_number=qnum,
                    page_index=page_index,
                    bbox={"x0": 0, "y0": y_start, "x1": width, "y1": y_end},
                    crop=crop,
                )
            )
        return regions

    def _split_evenly(
        self,
        image: Image.Image,
        page_index: int,
        questions: list[str],
        height: int,
        width: int,
    ) -> list[AnswerRegion]:
        """Split page into N strips aligned to rubric question list."""
        n = len(questions)
        strip_h = max(height // n, self.min_region_height)
        regions = []
        for i, qnum in enumerate(questions):
            y0 = i * strip_h
            y1 = height if i == n - 1 else min((i + 1) * strip_h, height)
            if y1 - y0 < self.min_region_height // 2:
                continue
            crop = image.crop((0, y0, width, y1))
            regions.append(
                AnswerRegion(
                    question_number=qnum,
                    page_index=page_index,
                    bbox={"x0": 0, "y0": y0, "x1": width, "y1": y1},
                    crop=crop,
                )
            )
        return regions

    def try_layoutparser(self, image: Image.Image, page_index: int) -> list[AnswerRegion] | None:
        """
        Optional LayoutParser — disabled by default path in pipeline when rubric exists.
        Maps blocks to Q1..Qn only if blocks match rubric count; otherwise returns None.
        """
        try:
            import layoutparser as lp

            model = lp.Detectron2LayoutModel(
                "lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config",
                extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.6],
                label_map={0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"},
            )
            img_np = np.array(image.convert("RGB"))
            layout = model.detect(img_np)
            text_blocks = sorted(
                [b for b in layout if b.type in ("Text", "Title", "List")],
                key=lambda b: b.block.y_1,
            )
            if len(text_blocks) < 2 or len(text_blocks) > 25:
                return None
            regions = []
            w, _h = image.size
            for i, block in enumerate(text_blocks):
                x0, y0, x1, y1 = (
                    int(block.block.x_1),
                    int(block.block.y_1),
                    int(block.block.x_2),
                    int(block.block.y_2),
                )
                if (y1 - y0) < self.min_region_height:
                    continue
                crop = image.crop((x0, y0, x1, y1))
                regions.append(
                    AnswerRegion(
                        question_number=f"Q{i + 1}",
                        page_index=page_index,
                        bbox={"x0": x0, "y0": y0, "x1": x1, "y1": y1},
                        crop=crop,
                    )
                )
            return self._dedupe_regions(regions) if regions else None
        except Exception as exc:
            logger.debug("LayoutParser unavailable: %s", exc)
            return None
