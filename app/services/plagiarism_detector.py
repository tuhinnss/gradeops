"""Cross-student answer similarity detection for plagiarism flags."""

import logging
from itertools import combinations

import numpy as np
from sentence_transformers import SentenceTransformer, util

from app.config import get_settings
from app.schemas.evaluation import PlagiarismFlag

logger = logging.getLogger(__name__)


class PlagiarismDetector:
    """Detect highly similar answers across students for the same question."""

    def __init__(self):
        settings = get_settings()
        self.threshold = settings.plagiarism_similarity_threshold
        self._model_id = settings.embedding_model_id
        self._model: SentenceTransformer | None = None

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self._model_id)
        return self._model

    def detect(
        self,
        submissions: list[dict],
    ) -> list[PlagiarismFlag]:
        """
        submissions: list of {
            student_id, answers: [{question_number, extracted_text}]
        }
        """
        flags: list[PlagiarismFlag] = []
        model = self._get_model()

        question_groups: dict[str, list[tuple[str, str]]] = {}
        for sub in submissions:
            sid = sub["student_id"]
            for ans in sub.get("answers", []):
                text = (ans.get("extracted_text") or "").strip()
                if len(text) < 20:
                    continue
                q = ans["question_number"].upper()
                question_groups.setdefault(q, []).append((sid, text))

        for question, pairs_data in question_groups.items():
            if len(pairs_data) < 2:
                continue

            texts = [t for _, t in pairs_data]
            student_ids = [s for s, _ in pairs_data]
            embeddings = model.encode(texts, convert_to_tensor=True)

            for (i, j) in combinations(range(len(texts)), 2):
                sim = float(util.cos_sim(embeddings[i], embeddings[j])[0][0])
                if sim >= self.threshold:
                    flags.append(
                        PlagiarismFlag(
                            question=question,
                            student_id_a=student_ids[i],
                            student_id_b=student_ids[j],
                            similarity=round(sim, 4),
                            note=(
                                f"Answers for {question} are {sim * 100:.1f}% similar. "
                                "Manual review recommended for potential plagiarism."
                            ),
                        )
                    )

        logger.info("Plagiarism scan found %d flags", len(flags))
        return flags
