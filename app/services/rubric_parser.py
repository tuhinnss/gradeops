"""Parse marking schemes from JSON or PDF into structured rubrics."""

import json
import logging
import re
from pathlib import Path

import fitz

from app.core.exceptions import RubricParseError
from app.schemas.rubric import PartialCreditRule, RubricItem, RubricSchema
from app.services.ocr.ocr_service import OCRService
from app.services.pdf_processor import PDFProcessor
from app.services.text_utils import (
    clean_ocr_text,
    extract_bullet_key_points,
    extract_marks_from_block,
    extract_rubric_key_points,
    find_question_blocks,
    log_rubric_parse_debug,
    normalize_question_label,
    parse_declared_exam_total,
    repair_missing_questions,
    validate_rubric_items,
)

logger = logging.getLogger(__name__)

# Minimum native text length to skip OCR (typed solution PDFs)
MIN_NATIVE_TEXT_CHARS = 400


class RubricParser:
    """Extract structured rubric from JSON file or PDF marking scheme."""

    def __init__(self):
        self.ocr = OCRService()
        self.pdf_processor = PDFProcessor()

    def parse_file(self, file_path: Path, source_type: str) -> RubricSchema:
        if source_type == "json":
            return self.parse_json(file_path)
        if source_type == "pdf":
            return self.parse_pdf(file_path)
        raise RubricParseError(f"Unsupported rubric type: {source_type}")

    def parse_json(self, file_path: Path) -> RubricSchema:
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RubricParseError(f"Invalid JSON rubric: {exc}") from exc

        return self._normalize_json(raw)

    def parse_json_string(self, content: str) -> RubricSchema:
        try:
            raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RubricParseError(f"Invalid JSON rubric: {exc}") from exc
        return self._normalize_json(raw)

    def _normalize_json(self, raw: dict | list) -> RubricSchema:
        if isinstance(raw, list):
            items = [self._parse_item_dict(i) for i in raw]
            return self._finalize_schema(RubricSchema(items=items))

        if "questions" in raw:
            raw = {"items": raw["questions"]}
        if "rubric" in raw:
            raw = raw["rubric"]

        items_data = raw.get("items", raw.get("questions", []))
        if not items_data:
            raise RubricParseError("Rubric JSON must contain 'items' or 'questions' array")

        items = [self._parse_item_dict(i) for i in items_data]
        return self._finalize_schema(
            RubricSchema(title=raw.get("title", "Exam Rubric"), items=items)
        )

    def _finalize_schema(self, schema: RubricSchema) -> RubricSchema:
        """Validate, dedupe, and fix marks before returning."""
        validated = validate_rubric_items(schema.items)
        if not validated:
            raise RubricParseError("Rubric contains no valid questions after validation")
        return RubricSchema(title=schema.title, items=validated)

    def _parse_item_dict(self, data: dict) -> RubricItem:
        raw_q = str(
            data.get("question_number")
            or data.get("question")
            or data.get("id")
            or ""
        )
        label = normalize_question_label(raw_q.lstrip("Qq")) or ""
        if not label:
            label = normalize_question_label(raw_q) or f"Q{raw_q}"

        partial_rules = []
        for rule in data.get("partial_credit_rules", []):
            if isinstance(rule, dict):
                partial_rules.append(
                    PartialCreditRule(
                        condition=rule.get("condition", ""),
                        marks=float(rule.get("marks", 0)),
                    )
                )
            elif isinstance(rule, str):
                partial_rules.append(PartialCreditRule(condition=rule, marks=0))

        marks = float(data.get("max_marks", data.get("marks", 0)) or 0)
        key_points = [
            str(kp).strip()
            for kp in data.get("key_points", data.get("points", []))
            if kp and len(str(kp).strip()) >= 3
        ]

        return RubricItem(
            question_number=label,
            max_marks=marks,
            key_points=key_points,
            negative_conditions=list(
                data.get("negative_conditions", data.get("penalties", []))
            ),
            partial_credit_rules=partial_rules,
        )

    @staticmethod
    def _extract_native_pdf_text(file_path: Path) -> str:
        """
        Extract embedded text via PyMuPDF (fast, accurate for typed solution PDFs).
        Prefer this over OCR for rubrics — saves RAM and avoids missing Q1/Q5.
        """
        parts: list[str] = []
        with fitz.open(file_path) as doc:
            for page in doc:
                parts.append(page.get_text())
        return clean_ocr_text("\n\n".join(parts))

    def parse_pdf(self, file_path: Path) -> RubricSchema:
        """
        Parse rubric/solutions PDF: native text first, OCR only if needed.
        """
        full_text = self._extract_native_pdf_text(file_path)
        source = "native_pdf"

        if len(full_text) < MIN_NATIVE_TEXT_CHARS:
            logger.info(
                "Native text short (%d chars); falling back to OCR for %s",
                len(full_text),
                file_path.name,
            )
            pages = self.pdf_processor.pdf_to_images(file_path)
            ocr_parts: list[str] = []
            for page in pages:
                ocr_result = self.ocr.extract_text(page.image)
                ocr_parts.append(ocr_result.text)
            full_text = clean_ocr_text("\n\n".join(ocr_parts))
            source = "ocr"

            if len(full_text) < MIN_NATIVE_TEXT_CHARS:
                full_text = self._extract_native_pdf_text(file_path) or full_text

        if not full_text.strip():
            raise RubricParseError("Could not extract text from rubric PDF")

        logger.info(
            "Rubric PDF %s: extracted %d chars via %s",
            file_path.name,
            len(full_text),
            source,
        )
        return self.parse_text(full_text, source=source)

    def parse_text(self, text: str, *, source: str = "text") -> RubricSchema:
        """
        Parse marking scheme from text using line-anchored question headers.
        """
        text = clean_ocr_text(text)
        declared_total = parse_declared_exam_total(text)
        blocks = find_question_blocks(text)
        items: list[RubricItem] = []

        for block in blocks:
            key_points = extract_rubric_key_points(block.body)
            if not key_points:
                key_points = extract_bullet_key_points(block.body)

            negative = self._extract_negative_conditions(block.body)
            partial_rules = self._extract_partial_rules(block.body)

            max_marks = block.max_marks
            if max_marks <= 0:
                max_marks = extract_marks_from_block(block.body)

            # Section-sourced marks are authoritative even for short True/False stems
            if max_marks <= 0 and not key_points:
                continue
            if not key_points and block.body.strip():
                key_points = [block.body.strip()[:400]]

            items.append(
                RubricItem(
                    question_number=block.question_number,
                    max_marks=max_marks,
                    key_points=key_points,
                    negative_conditions=negative,
                    partial_credit_rules=partial_rules,
                )
            )

        if not items:
            items = self._fallback_line_parser(text)

        if not items:
            raise RubricParseError("Could not parse rubric structure from PDF text")

        items = repair_missing_questions(items, blocks, declared_total)
        schema = self._finalize_schema(RubricSchema(items=items))

        log_rubric_parse_debug(
            source,
            text,
            blocks,
            schema.items,
            declared_total,
        )

        return schema

    def _extract_negative_conditions(self, text: str) -> list[str]:
        negatives = []
        for line in text.splitlines():
            lower = line.lower()
            if any(
                kw in lower
                for kw in ("deduct", "penalty", "incorrect", "wrong", "no marks")
            ):
                cleaned = re.sub(r"^[\-\*•]\s*", "", line.strip())
                if cleaned and len(cleaned) > 6:
                    negatives.append(cleaned)
        return negatives[:8]

    def _extract_partial_rules(self, text: str) -> list[PartialCreditRule]:
        rules = []
        for m in re.finditer(
            r"(?:partial|award)\s*[:\-]?\s*(.+?)\s*[\(\-]\s*(\d+(?:\.\d+)?)\s*(?:marks?|m)?\s*\)?",
            text,
            re.IGNORECASE,
        ):
            rules.append(
                PartialCreditRule(condition=m.group(1).strip(), marks=float(m.group(2)))
            )
        return rules

    def _fallback_line_parser(self, text: str) -> list[RubricItem]:
        """Last resort: one item per line that looks like a question header."""
        items = []
        for line in text.splitlines():
            line = line.strip()
            if len(line) < 8:
                continue
            m = re.match(
                r"^(?:Q(?:uestion)?\s*)?(\d{1,2})[\.\):\-]\s*(?:\((\d+(?:\.\d+)?)\s*m(?:arks?)?\))?\s*(.+)$",
                line,
                re.IGNORECASE,
            )
            if not m:
                continue
            label = normalize_question_label(m.group(1))
            if not label:
                continue
            marks = float(m.group(2)) if m.group(2) else extract_marks_from_block(line)
            desc = m.group(3).strip()
            items.append(
                RubricItem(
                    question_number=label,
                    max_marks=marks or 1.0,
                    key_points=[desc] if len(desc) >= 8 else [],
                )
            )
        return items
