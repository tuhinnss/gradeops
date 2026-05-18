"""Annotate original PDF with marks, comments, and total score."""

import logging
from pathlib import Path

import fitz

from app.schemas.evaluation import QuestionResult

logger = logging.getLogger(__name__)

# PyMuPDF standard colors (RGB 0-1)
RED = (0.86, 0.15, 0.15)
GREEN = (0.13, 0.55, 0.13)
BLUE = (0.1, 0.35, 0.75)
GRAY = (0.4, 0.4, 0.4)


class PDFAnnotator:
    """Write marks and justifications onto the original answer sheet PDF."""

    def annotate(
        self,
        source_pdf: Path,
        results: list[QuestionResult],
        answer_regions: list[dict],
        output_path: Path,
        student_id: str,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        region_map: dict[str, list[dict]] = {}
        for region in answer_regions:
            q = region["question_number"].upper()
            region_map.setdefault(q, []).append(region)

        total_awarded = sum(r.marks_awarded for r in results)
        max_total = sum(r.max_marks for r in results)

        with fitz.open(source_pdf) as doc:
            for result in results:
                q = result.question.upper()
                regions = region_map.get(q, [])
                if not regions:
                    regions = region_map.get(q.replace("Q", "Q"), [])

                for region in regions:
                    page_idx = region["page_index"]
                    if page_idx >= len(doc):
                        continue
                    page = doc[page_idx]
                    self._annotate_region(page, region, result)

            if len(doc) > 0:
                last_page = doc[-1]
                self._add_summary_footer(
                    last_page, student_id, total_awarded, max_total, results
                )

            doc.save(str(output_path))

        logger.info("Annotated PDF saved to %s", output_path)
        return output_path

    def _annotate_region(self, page: fitz.Page, region: dict, result: QuestionResult) -> None:
        from app.config import get_settings

        settings = get_settings()
        zoom = settings.pdf_dpi / 72.0

        bbox = region["bbox"]
        x1 = bbox["x1"] / zoom + 8
        y0 = bbox["y0"] / zoom

        mark_color = GREEN if result.marks_awarded >= result.max_marks * 0.6 else RED
        mark_text = f"{result.marks_awarded:.1f}/{result.max_marks:.0f}"

        page.insert_text(
            fitz.Point(x1, max(y0, 20)),
            mark_text,
            fontsize=14,
            fontname="helv",
            color=mark_color,
        )

        comment = result.justification[:180]
        if len(result.justification) > 180:
            comment += "..."

        page.insert_textbox(
            fitz.Rect(x1, y0 + 18, page.rect.width - 20, y0 + 80),
            comment,
            fontsize=7,
            fontname="helv",
            color=GRAY,
            align=fitz.TEXT_ALIGN_LEFT,
        )

        if result.is_blank:
            page.draw_rect(
                fitz.Rect(
                    bbox["x0"] / zoom,
                    bbox["y0"] / zoom,
                    bbox["x1"] / zoom,
                    bbox["y1"] / zoom,
                ),
                color=RED,
                width=1.5,
                dashes="[4 2]",
            )
            page.insert_text(
                fitz.Point(bbox["x0"] / zoom + 4, bbox["y0"] / zoom + 14),
                "BLANK",
                fontsize=10,
                color=RED,
            )

    def _add_summary_footer(
        self,
        page: fitz.Page,
        student_id: str,
        total: float,
        max_total: float,
        results: list[QuestionResult],
    ) -> None:
        y = page.rect.height - 60
        summary = (
            f"GRADEOPS Evaluation | Student: {student_id} | "
            f"Total: {total:.1f}/{max_total:.1f}"
        )
        page.insert_text(
            fitz.Point(40, y),
            summary,
            fontsize=11,
            fontname="helv",
            color=BLUE,
        )

        breakdown = " | ".join(
            f"{r.question}: {r.marks_awarded:.1f}" for r in results[:12]
        )
        page.insert_text(
            fitz.Point(40, y + 16),
            breakdown,
            fontsize=8,
            fontname="helv",
            color=GRAY,
        )
