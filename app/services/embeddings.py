"""Shared sentence-embedding model loader.

The model is loaded lazily (first evaluation), shared by the evaluation engine and
the plagiarism detector, and never imported at module import time so the API can
serve dashboards without torch being loaded.

If the model cannot be loaded (e.g. an offline host that cannot reach the model
hub) and ``EMBEDDING_FALLBACK=lexical`` (default), callers get ``None`` and must
fall back to lexical matching. Results produced that way are marked as such and
carry reduced confidence so reviewers know the semantic model was unavailable.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Protocol

import numpy as np

from app.config import get_settings
from app.core.exceptions import EvaluationError

logger = logging.getLogger(__name__)


class Encoder(Protocol):
    def encode(self, sentences: list[str], **kwargs: Any) -> Any: ...


_model: Encoder | None = None
_load_failed = False
_lock = threading.Lock()


def set_embedding_model(model: Encoder | None) -> None:
    """Inject a model (tests, warm-up hooks). ``None`` resets to lazy loading."""
    global _model, _load_failed
    with _lock:
        _model = model
        _load_failed = False


def get_embedding_model() -> Encoder | None:
    global _model, _load_failed
    if _model is not None:
        return _model
    settings = get_settings()
    with _lock:
        if _model is not None:
            return _model
        if not _load_failed:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading embedding model: %s", settings.embedding_model_id)
                _model = SentenceTransformer(settings.embedding_model_id)
                return _model
            except Exception as exc:  # ImportError, network/hub errors, …
                _load_failed = True
                logger.warning("Embedding model unavailable: %s", exc)
    if settings.embedding_fallback == "lexical":
        return None
    raise EvaluationError(
        "Embedding model could not be loaded and EMBEDDING_FALLBACK=error",
        details={"model": settings.embedding_model_id},
    )


def embedding_backend() -> str:
    """'semantic' when a sentence-embedding model is loaded, else 'lexical'."""
    return "semantic" if get_embedding_model() is not None else "lexical"


def encode_normalized(texts: list[str]) -> np.ndarray | None:
    """Encode texts to L2-normalised vectors, or ``None`` when no model is available."""
    model = get_embedding_model()
    if model is None or not texts:
        return None
    vectors = np.asarray(model.encode(texts), dtype=np.float32)
    if vectors.ndim == 1:
        vectors = vectors.reshape(1, -1)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms
