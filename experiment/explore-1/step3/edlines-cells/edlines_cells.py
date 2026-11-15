# -*- coding: utf-8 -*-
"""EDLines: rasterize edge segments (chains) onto the 16px cell grid."""
import sys
from pathlib import Path

import cv2
import numpy as np

DATA_DIR = Path(r"C:\Users\kazuh\orca\workspaces\BrowserMoji\main\data")
HERE = Path(__file__).resolve().parent
OUT_BASE = HERE / "out"
MAX_SIDE = 1280
CELL = 16
JPEG_QUALITY = 90
MIN_SEG_POINTS = 5  # ignore too-short segments


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


def get_segments(gray: np.ndarray, pre_filtered: bool) -> list:
    src = gray
    if pre_filtered:
        src = cv2.bilateralFilter(gray, d=7, sigmaColor=30, sigmaSpace=7)
    ed = cv2.ximgproc.createEdgeDrawing()
    params = ed.Params()
    params.GradientThresholdValue = 32
    params.AnchorThresholdValue = 8
    ed.setParams(params)
    ed.detectEdges(src)
    # EDLines: chain point lists of edge segments
    segments = ed.getSegments()
    return [s for s in segments if len(s) >= MIN_SEG_POINTS]


def render_cells(gray: np.ndarray, segments: list) -> np.ndarray:
    h, w = gray.shape
    gh = (h + CELL - 1) // CELL
    gw = (w + CELL - 1) // CELL
    # filler = per-cell mean luminance (block mean via block-reduce on padded image)
    ph, pw = gh * CELL, gw * CELL
    padded = np.full((ph, pw), int(gray.mean()), np.uint8)
    padded[:h, :w] = gray
    cells = padded.reshape(gh, CELL, gw, CELL).mean(axis=(1, 3)).astype(np.uint8)
    # rasterize chains into the cell grid (coords / CELL)
    # getSegments() returns points as (x, y); polylines expects (x, y)
    pts = [np.rint(s / CELL).astype(np.int32) for s in segments]
    cv2.polylines(cells, pts, isClosed=False, color=255, thickness=1, lineType=cv2.LINE_8)
    return cells


def main() -> None:
    variants = {
        "edp-raw": False,
        "edp-bilateral": True,
    }
    files = sorted(p for p in DATA_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    for name, filtered in variants.items():
        outdir = OUT_BASE / name
        outdir.mkdir(parents=True, exist_ok=True)
        for p in files:
            gray = load_gray(p)
            segs = get_segments(gray, filtered)
            cells = render_cells(gray, segs)
            ok, buf = cv2.imencode(".jpg", cells, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            outpath = outdir / (p.stem + ".jpg")
            buf.tofile(str(outpath))
            npx = int((cells == 255).sum())
            print(f"{name}: {p.name} -> {outpath.name} segs={len(segs)} edge_cells={npx}")
    print("done")


if __name__ == "__main__":
    sys.exit(main())
