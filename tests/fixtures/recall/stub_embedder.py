"""Deterministic stub embedder with controllable cosines (spec 001 fixture kit).

Every query embeds to the unit vector ``e0``. A document embeds to
``sim * e0 + sqrt(1 - sim**2) * e_k``, so its cosine with any query is exactly ``sim``.
``sim`` comes from a ``<!-- sim:0.62 -->`` marker in the text; without one it is a
deterministic value in [0.50, 0.79] derived from the text's sha1. ``e_k`` is a
text-derived axis other than ``e0``. The suite never loads bge-base.
"""

import hashlib
import math
import re
import threading

import numpy as np
from numpy.typing import NDArray

from secondbrain.indexing.embedder import Embedder

DIM = 64
STUB_MODEL_NAME = "stub-embedder"
_SIM_MARKER = re.compile(r"<!--\s*sim:([0-9]*\.?[0-9]+)\s*-->")


def _text_hash(text: str) -> int:
    return int(hashlib.sha1(text.encode()).hexdigest(), 16)


def marker_similarity(text: str) -> float:
    """The cosine this text will have with every query."""
    match = _SIM_MARKER.search(text)
    if match:
        return float(match.group(1))
    return 0.50 + (_text_hash(text) % 30) / 100


def _doc_vector(text: str) -> NDArray[np.float32]:
    sim = marker_similarity(text)
    axis = 1 + _text_hash(text) % (DIM - 1)
    vec = np.zeros(DIM, dtype=np.float64)
    vec[0] = sim
    vec[axis] = math.sqrt(max(0.0, 1.0 - sim * sim))
    return vec.astype(np.float32)


class StubProvider:
    """EmbeddingProvider with controllable cosines; counts query embeddings."""

    def __init__(self) -> None:
        self.query_calls: list[str] = []
        self._lock = threading.Lock()

    def embed(self, texts: list[str]) -> NDArray[np.float32]:
        if not texts:
            return np.array([], dtype=np.float32)
        return np.stack([_doc_vector(t) for t in texts])

    def embed_query(self, text: str) -> NDArray[np.float32]:
        with self._lock:
            self.query_calls.append(text)
        vec = np.zeros(DIM, dtype=np.float32)
        vec[0] = 1.0
        return vec

    @property
    def dimension(self) -> int:
        return DIM

    @property
    def model_name(self) -> str:
        return STUB_MODEL_NAME


def make_stub_embedder() -> Embedder:
    """An Embedder wrapping a fresh StubProvider."""
    return Embedder(provider=StubProvider())
