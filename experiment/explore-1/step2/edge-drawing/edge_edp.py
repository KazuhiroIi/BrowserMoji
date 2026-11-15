# -*- coding: utf-8 -*-
"""Edge Drawing (EDPF) edge detection variants for BrowserMoji exploration."""
import sys
from pathlib import Path

import cv2
import numpy as np

DATA_DIR = Path(r"C:\Users\kazuh\orca\workspaces\BrowserMoji\main\data")
OUT_BASE = Path(__file__).resolve().parent / "out"
MAX_SIDE = 1280
JPEG_QUALITY = 90


def load_gray(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)  # Windows-safe (non-ASCII paths)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"failed to read {path}")
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def run_edp(gray: np.ndarray, pre_filtered: bool) -> np.ndarray:
    src = gray
    if pre_filtered:
        src = cv2.bilateralFilter(gray, d=7, sigmaColor=30, sigmaSpace=7)
    ed = cv2.ximgproc.createEdgeDrawing()
    params = ed.Params()
    params.GradientThresholdValue = 32
    params.AnchorThresholdValue = 8
    ed.setParams(params)
    # OpenCV 5: detectEdges(src) runs detection; getEdgeImage() (no args) returns the map
    ed.detectEdges(src)
    edges = ed.getEdgeImage()
    return edges


def main() -> None:
    variants = {
        "edp-default": False,
        "edp-noise-filtered": True,
    }
    files = sorted(p for p in DATA_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    for name, filtered in variants.items():
        outdir = OUT_BASE / name
        outdir.mkdir(parents=True, exist_ok=True)
        for p in files:
            gray = load_gray(p)
            edges = run_edp(gray, filtered)
            ok, buf = cv2.imencode(".jpg", edges, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            outpath = outdir / (p.stem + ".jpg")
            buf.tofile(str(outpath))
            print(f"{name}: {p.name} -> {outpath.name} edges={int((edges>0).sum())}")
    print("done")


if __name__ == "__main__":
    sys.exit(main())
