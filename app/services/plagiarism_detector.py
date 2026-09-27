"""Cross-student answer similarity detection (integrity flags).

A flag means two answers to the same question are unusually similar. It is
evidence for a professor to review, never a finding of misconduct.
"""

import logging
import re
from itertools import combinations

import numpy as np

from app.config import get_settings
from app.schemas.evaluation import PlagiarismFlag
from app.services.embeddings import encode_normalized

logger = logging.getLogger(__name__)

MIN_ANSWER_CHARS = 20
EXCERPT_CHARS = 280
# Two answers that both closely restate the rubric's reference answer are
# expected to resemble each other; that is not evidence of copying.
REFERENCE_SIMILARITY = 0.75


def _token_set(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z0-9]{2,}", text)}


def _lexical_similarity_matrix(texts: list[str]) -> np.ndarray:
    """Jaccard similarity of word sets (used when no embedding model is loaded)."""
    sets = [_token_set(t) for t in texts]
    n = len(texts)
    matrix = np.eye(n, dtype=np.float32)
    for i, j in combinations(range(n), 2):
        union = sets[i] | sets[j]
        score = len(sets[i] & sets[j]) / len(union) if union else 0.0
        matrix[i, j] = matrix[j, i] = score
    return matrix


class PlagiarismDetector:
    """Detect highly similar answers across students for the same question."""

    def __init__(self):
        self.threshold = get_settings().plagiarism_similarity_threshold

    @staticmethod
    def _similarity_matrix(texts: list[str]) -> np.ndarray:
        vectors = encode_normalized(texts)
        if vectors is None:
            return _lexical_similarity_matrix(texts)
        return vectors @ vectors.T

    def detect(
        self,
        submissions: list[dict],
        references: dict[str, str] | None = None,
    ) -> list[PlagiarismFlag]:
        """
        submissions: list of {
            student_id, answers: [{question_number, extracted_text}]
        }
        references: optional {question: reference/model answer text}. Pairs in
        which both answers closely match the reference are not flagged.
        """
        references = {k.upper(): v for k, v in (references or {}).items() if v}
        flags: list[PlagiarismFlag] = []

        question_groups: dict[str, list[tuple[str, str]]] = {}
        for sub in submissions:
            sid = sub["student_id"]
            for ans in sub.get("answers", []):
                text = (ans.get("extracted_text") or "").strip()
                if len(text) < MIN_ANSWER_CHARS:
                    continue
                q = ans["question_number"].upper()
                question_groups.setdefault(q, []).append((sid, text))

        for question, pairs_data in question_groups.items():
            if len(pairs_data) < 2:
                continue
            texts = [t for _, t in pairs_data]
            student_ids = [s for s, _ in pairs_data]
            reference = references.get(question)
            matrix = self._similarity_matrix(texts + ([reference] if reference else []))
            follows_reference = [
                bool(reference) and float(matrix[i, len(texts)]) >= REFERENCE_SIMILARITY
                for i in range(len(texts))
            ]

            for i, j in combinations(range(len(texts)), 2):
                if student_ids[i] == student_ids[j]:
                    continue
                if follows_reference[i] and follows_reference[j]:
                    continue
                sim = float(matrix[i, j])
                if sim >= self.threshold:
                    flags.append(
                        PlagiarismFlag(
                            question=question,
                            student_id_a=student_ids[i],
                            student_id_b=student_ids[j],
                            similarity=round(sim, 4),
                            note=(
                                f"Similarity flag: answers for {question} are {sim * 100:.1f}% "
                                "similar. Potential match — review required."
                            ),
                            excerpt_a=texts[i][:EXCERPT_CHARS],
                            excerpt_b=texts[j][:EXCERPT_CHARS],
                        )
                    )

        logger.info("Similarity scan found %d flags", len(flags))
        return flags
