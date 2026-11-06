"""Small computer-vision helpers shared by stages."""
from __future__ import annotations

from pathlib import Path

from .util import log


def face_box(video: Path, samples: int = 24) -> dict | None:
    """Median face box over the clip as fractions of the frame {top, bottom, left, right, cx}, or None.
    Used to keep captions and graphics off the speaker's face, whatever the reference does."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    model = Path(__file__).resolve().parent.parent / "assets" / "models" / "face_detection_yunet_2023mar.onnx"
    if not model.exists() or not hasattr(cv2, "FaceDetectorYN"):
        return None
    cap = cv2.VideoCapture(str(video))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if n <= 0:
        cap.release()
        return None
    det = None
    boxes = []
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((i + 0.5) * n / samples))
        ok, f = cap.read()
        if not ok:
            continue
        h, w = f.shape[:2]
        scale = 480 / max(h, w)
        W, H = int(w * scale), int(h * scale)
        small = cv2.resize(f, (W, H))
        if det is None:
            det = cv2.FaceDetectorYN.create(str(model), "", (W, H), 0.6)   # YuNet (OpenCV model zoo, MIT)
        _, faces = det.detect(small)
        if faces is not None and len(faces):
            x, y, fw, fh = max(faces[:, :4].tolist(), key=lambda r: r[2] * r[3])
            boxes.append((y / H, (y + fh) / H, x / W, (x + fw) / W))
    cap.release()
    if len(boxes) < max(3, samples // 4):
        return None
    a = np.array(boxes)
    top, bottom, left, right = np.median(a, axis=0)
    # a face box covers forehead-to-chin; extend for hair above and the chin/neck below
    hgt = bottom - top
    out = {"top": round(float(max(0.0, top - 0.25 * hgt)), 3), "bottom": round(float(min(1.0, bottom + 0.12 * hgt)), 3),
           "left": round(float(left), 3), "right": round(float(right), 3), "cx": round(float((left + right) / 2), 3),
           "detected_in": round(len(boxes) / samples, 2)}
    log.debug("face box %s", out)
    return out
