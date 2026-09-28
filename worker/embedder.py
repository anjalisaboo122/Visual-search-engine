"""
Turns an image into an embedding: 512 numbers describing what it looks like.

Two versions with the same interface:
- ClipEmbedder: the real thing (OpenCLIP ViT-B-32). Downloads ~600 MB of
  model weights on first run, cached in the `model-cache` Docker volume.
- FakeEmbedder: deterministic numbers from the file's hash. For tests,
  so the pipeline can be checked without the big model.

Both return a unit-length vector (length 1). That makes "cosine similarity"
equal to a plain dot product, which is what the search index uses in Phase 3.
"""
import hashlib
import io

import numpy as np
from PIL import Image as PILImage

DIM = 512


def _normalize(vec: np.ndarray) -> np.ndarray:
    vec = vec.astype(np.float32).reshape(-1)
    norm = np.linalg.norm(vec)
    if norm == 0:
        raise ValueError("zero vector")
    return vec / norm


class FakeEmbedder:
    name = "fake-sha256"

    def embed(self, image_bytes: bytes) -> np.ndarray:
        seed = int.from_bytes(hashlib.sha256(image_bytes).digest()[:8], "big")
        return _normalize(np.random.default_rng(seed).standard_normal(DIM))


class ClipEmbedder:
    def __init__(self, model_name: str, pretrained: str):
        # Imported here so the fake embedder works without torch installed.
        import open_clip
        import torch

        self._torch = torch
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained
        )
        self.model.eval()  # inference mode: no training behaviour
        self.name = f"open_clip/{model_name}/{pretrained}"

    def embed(self, image_bytes: bytes) -> np.ndarray:
        with PILImage.open(io.BytesIO(image_bytes)) as img:
            # resize + crop to 224x224 + convert to the numbers CLIP expects
            tensor = self.preprocess(img.convert("RGB")).unsqueeze(0)
        with self._torch.no_grad():  # we're not training, skip gradient bookkeeping
            features = self.model.encode_image(tensor)
        return _normalize(features[0].cpu().numpy())


def load_embedder(kind: str, model_name: str, pretrained: str):
    if kind == "fake":
        return FakeEmbedder()
    if kind == "clip":
        return ClipEmbedder(model_name, pretrained)
    raise ValueError(f"Unknown EMBEDDER={kind!r} (use 'clip' or 'fake')")
