"""End-to-end processing pipeline orchestrator."""

import json
import logging
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import EvaluationError
from app.db import crud
from app.db.models import SubmissionStatus
from app.schemas.evaluation import EvaluationResponse, PlagiarismFlag
from app.schemas.rubric import RubricSchema
from app.services.evaluation_engine import EvaluationEngine
from app.services.layout_segmenter import LayoutSegmenter
from app.services.ocr.ocr_service import OCRService
from app.services.pdf_annotator import PDFAnnotator
from app.services.pdf_processor import PDFProcessor
from app.services.plagiarism_detector import PlagiarismDetector
from app.services.rubric_parser import RubricParser
from app.services.text_utils import (
    clean_ocr_text,
    merge_answers_by_question,
    rubric_total_marks,
    validate_rubric_items,
)

logger = logging.getLogger(__name__)


class GradeOpsPipeline:
    """Orchestrates OCR, segmentation, evaluation, and PDF annotation."""

    def __init__(self):
        self.pdf_processor = PDFProcessor()
        self.segmenter = LayoutSegmenter()
        self.ocr = OCRService()
        self.rubric_parser = RubricParser()
        self.evaluator = EvaluationEngine()
        self.annotator = PDFAnnotator()
        self.plagiarism = PlagiarismDetector()
        self.settings = get_settings()

    def _validated_rubric(self, rubric_schema: RubricSchema) -> RubricSchema:
        """Re-validate rubric loaded from DB."""
        items = validate_rubric_items(rubric_schema.items)
        return RubricSchema(
            title=rubric_schema.title,
            items=items,
        )

    async def process_submission_ocr(
        self,
        session: AsyncSession,
        submission_id: uuid.UUID,
        rubric_schema: RubricSchema | None = None,
    ) -> dict:

        submission = await crud.get_submission(session, submission_id)

        if not submission:
            raise EvaluationError(
                f"Submission {submission_id} not found"
            )

        if rubric_schema:
            rubric_schema = self._validated_rubric(rubric_schema)

        # FIXED HERE
        await crud.update_submission(
            session,
            submission,
            status=SubmissionStatus.PROCESSING,
        )

        await crud.add_evaluation_log(
            session,
            submission_id,
            "ocr",
            "Starting OCR and segmentation",
        )

        pdf_path = Path(submission.file_path)

        pages = self.pdf_processor.pdf_to_images(pdf_path)

        expected_questions = (
            [item.question_number for item in rubric_schema.items]
            if rubric_schema
            else None
        )

        raw_answers = []
        full_page_texts = []

        for page in pages:

            page_ocr = self.ocr.extract_text(page.image)

            page_text = clean_ocr_text(page_ocr.text)

            full_page_texts.append(page_text)

            if expected_questions:

                regions = self.segmenter.segment_page(
                    page.image,
                    page.page_index,
                    full_page_text=page_text,
                    expected_questions=expected_questions,
                )

            else:

                lp_regions = self.segmenter.try_layoutparser(
                    page.image,
                    page.page_index,
                )

                regions = lp_regions or self.segmenter.segment_page(
                    page.image,
                    page.page_index,
                    full_page_text=page_text,
                    expected_questions=None,
                )

            for region in regions:

                ocr_result = self.ocr.extract_text(region.crop)

                is_blank = self.ocr.is_blank(
                    ocr_result.text
                )

                if is_blank and not expected_questions:
                    continue

                raw_answers.append(
                    {
                        "question_number": region.question_number,
                        "page_index": region.page_index,
                        "bbox": region.bbox,
                        "extracted_text": ocr_result.text,
                        "is_blank": is_blank,
                        "ocr_confidence": ocr_result.confidence,
                        "ocr_engine": ocr_result.engine,
                    }
                )

        all_answers = merge_answers_by_question(
            raw_answers,
            expected_questions,
        )

        extracted_payload = {
            "student_id": submission.student_id,
            "page_count": len(pages),
            "full_page_text": full_page_texts,
            "answers": all_answers,
        }

        await crud.save_extracted_answers(
            session,
            submission_id,
            all_answers,
        )

        # FIXED HERE
        await crud.update_submission(
            session,
            submission,
            status=SubmissionStatus.OCR_COMPLETE,
            page_count=len(pages),
            extracted_text=extracted_payload,
        )

        await crud.add_evaluation_log(
            session,
            submission_id,
            "ocr",
            f"OCR complete: {len(all_answers)} questions",
        )

        return extracted_payload

    async def evaluate_submission(
        self,
        session: AsyncSession,
        submission_id: uuid.UUID,
        rubric_schema: RubricSchema,
    ) -> EvaluationResponse:

        submission = await crud.get_submission(
            session,
            submission_id,
        )

        if not submission:
            raise EvaluationError(
                f"Submission {submission_id} not found"
            )

        rubric_schema = self._validated_rubric(
            rubric_schema
        )

        if not submission.extracted_text:

            await self.process_submission_ocr(
                session,
                submission_id,
                rubric_schema,
            )

            submission = await crud.get_submission(
                session,
                submission_id,
            )

        answers = submission.extracted_text.get(
            "answers",
            [],
        )

        answers = merge_answers_by_question(
            answers,
            [q.question_number for q in rubric_schema.items],
        )

        if not rubric_schema.items:
            raise EvaluationError(
                "Rubric has no questions to evaluate"
            )

        await crud.add_evaluation_log(
            session,
            submission_id,
            "evaluate",
            "Running evaluation",
        )

        results = self.evaluator.evaluate_all(
            answers,
            rubric_schema.items,
        )

        total = round(
            sum(r.marks_awarded for r in results),
            2,
        )

        max_total = rubric_total_marks(
            rubric_schema.items
        )

        logger.info(
            "Evaluation %s: total %.1f/%.1f — %s",
            submission_id,
            total,
            max_total,
            ", ".join(
                f"{r.question}={r.marks_awarded:.1f}(conf={r.confidence:.2f})"
                for r in results
            ),
        )

        output_json_path = (
            self.settings.output_dir
            / str(submission_id)
            / "evaluation.json"
        )

        output_json_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        eval_dict = {
            "student_id": submission.student_id,
            "submission_id": str(submission_id),
            "results": [
                r.model_dump() for r in results
            ],
            "total": total,
            "max_total": max_total,
        }

        output_json_path.write_text(
            json.dumps(eval_dict, indent=2),
            encoding="utf-8",
        )

        annotated_path = (
            self.settings.output_dir
            / str(submission_id)
            / f"{submission.student_id}_annotated.pdf"
        )

        try:

            self.annotator.annotate(
                Path(submission.file_path),
                results,
                answers,
                annotated_path,
                submission.student_id,
            )

            annotated_pdf = str(annotated_path)

        except Exception as exc:

            logger.error(
                "PDF annotation failed: %s",
                exc,
            )

            annotated_pdf = None

        # FIXED HERE
        await crud.update_submission(
            session,
            submission,
            status=SubmissionStatus.EVALUATED,
            evaluation_result=eval_dict,
            total_marks=total,
            annotated_pdf_path=annotated_pdf,
        )

        await crud.add_evaluation_log(
            session,
            submission_id,
            "evaluate",
            f"Evaluation complete: {total}/{max_total}",
        )

        submission = await crud.get_submission(session, submission_id)
        return EvaluationResponse(
            submission_id=submission_id,
            student_id=submission.student_id,
            results=results,
            total=total,
            max_total=max_total,
            annotated_pdf_url=(
                f"/api/v1/results/{submission_id}/annotated-pdf"
                if annotated_pdf
                else None
            ),
            review_status=submission.review_status.value if submission else "pending",
        )

    async def run_plagiarism_check(
        self,
        session: AsyncSession,
        submission_ids: list[uuid.UUID],
    ) -> list[PlagiarismFlag]:

        batch = []

        for sid in submission_ids:

            sub = await crud.get_submission(
                session,
                sid,
            )

            if sub and sub.extracted_text:

                batch.append(
                    {
                        "student_id": sub.student_id,
                        "answers": sub.extracted_text.get(
                            "answers",
                            [],
                        ),
                    }
                )

        return self.plagiarism.detect(batch)