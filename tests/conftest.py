from __future__ import annotations

import sys
import types

# Globally mock sentence_transformers at the very beginning of test sessions
# to avoid importing PyTorch/CUDA which causes massive slowdowns and hangs in WSL.

class FakeSentenceTransformer:
    def __init__(self, *args, **kwargs) -> None:
        self.encode_calls = []

    def encode(self, texts, normalize_embeddings=True, batch_size=None):
        self.encode_calls.append(texts)
        # return dummy vectors matching dimensions
        return [[0.1] * 384 for _ in texts]


class FakeCrossEncoder:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def predict(self, pairs, **kwargs):
        return [0.5] * len(pairs)


fake_module = types.SimpleNamespace(
    SentenceTransformer=FakeSentenceTransformer,
    CrossEncoder=FakeCrossEncoder,
)
sys.modules["sentence_transformers"] = fake_module
