"""Optional dense retrieval with a small sentence-embedding model.

Enable with ``pip install "timecapsule[dense]"``. Embeddings are cached next to
the corpus so they are computed once. Dense search catches paraphrases
("ship went down" vs "foundered"); BM25 catches names and rare words. The two
rankings are fused with reciprocal-rank fusion in ``retrieval.search``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class DenseIndex:
    def __init__(self, docs: list[str], cache_dir: Path, model_name: str = DEFAULT_MODEL):
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer
        except ImportError as e:  # pragma: no cover - optional extra
            raise SystemExit('Dense retrieval needs: pip install "timecapsule[dense]"') from e
        self.np = np
        self.model = SentenceTransformer(model_name)
        digest = hashlib.sha1(("\x00".join(docs) + model_name).encode()).hexdigest()[:12]
        path = Path(cache_dir) / f"embeddings-{digest}.npy"
        if path.exists():
            self.matrix = np.load(path)
        else:
            self.matrix = self.model.encode(docs, batch_size=64, normalize_embeddings=True,
                                            show_progress_bar=True).astype("float32")
            np.save(path, self.matrix)

    def search(self, query: str, k: int = 50, allowed: set[int] | None = None) -> list[tuple[int, float]]:
        q = self.model.encode([query], normalize_embeddings=True)[0]
        sims = self.matrix @ q
        order = self.np.argsort(-sims)
        out = []
        for i in order:
            if allowed is not None and int(i) not in allowed:
                continue
            out.append((int(i), float(sims[i])))
            if len(out) == k:
                break
        return out
