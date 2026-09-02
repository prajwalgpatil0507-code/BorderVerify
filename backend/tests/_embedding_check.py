"""Verification probe for the ArcFace embedding pipeline.

The demo data ships no real, YuNet-detectable face (uploads are document scans),
so we exercise the model components directly: alignment, embedding extraction,
L2 normalisation, and cosine similarity on identical vs. different crops.
"""
import sys, os, cv2, numpy as np
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.services.embeddings import (
    available, norm_crop, get_embedding, model_path,
)
from app.services.face import detect_faces


def log(*a):
    sys.stdout.write(' '.join(str(x) for x in a) + '\n'); sys.stdout.flush()


def main():
    log("embedding model available:", available())
    log("model path:", model_path())

    # 1) norm_crop returns a 112x112 aligned crop
    img = np.random.randint(0, 255, (180, 140, 3), dtype=np.uint8)
    lmks = [[60, 70], [80, 68], [70, 90], [62, 105], [78, 104]]
    crop = norm_crop(img, lmks)
    log("norm_crop shape:", crop.shape)
    assert crop.shape == (112, 112, 3), crop.shape

    # 2) get_embedding -> 512-d, L2-normalised (unit norm)
    e1 = get_embedding(crop)
    e2 = get_embedding(crop)                      # same crop -> same embedding
    log("embedding dim:", e1.shape, "norm:", round(float(np.linalg.norm(e1)), 5))
    assert e1.shape == (512,), e1.shape
    assert abs(float(np.linalg.norm(e1)) - 1.0) < 1e-3

    # 3) identical crops -> cosine ~ 1.0 (score ~ 1.0, status 'match')
    same_cos = float(np.dot(e1, e2))
    same_score = (same_cos + 1.0) / 2.0
    log("same-crop cosine:", round(same_cos, 5), "score:", round(same_score, 5))
    assert same_cos > 0.999, same_cos

    # 4) differing crops -> lower cosine (not guaranteed <, but the embedding path runs)
    other = np.random.randint(0, 255, (112, 112, 3), dtype=np.uint8)
    e3 = get_embedding(other)
    diff_cos = float(np.dot(e1, e3))
    log("diff-crop cosine:", round(diff_cos, 5), "score:", round((diff_cos + 1.0) / 2.0, 5))

    # 5) no-face path via embedding_match (blank images -> no face detected)
    from app.services.embeddings import embedding_match
    blank = np.zeros((100, 100, 3), dtype=np.uint8)
    m = embedding_match(blank, blank)
    log("blank->blank status:", m.status, "score:", m.score)
    assert m.status == "no_face"

    log("EMBEDDING CHECK OK")


if __name__ == "__main__":
    main()
