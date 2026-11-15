# -*- coding: utf-8 -*-
"""step4 案E: EDPF improved variants (clahe / grad20 / coherent)."""
import sys
from pathlib import Path

import cv2
import numpy as np

DATA_DIR = Path(r"C:\Users\kazuh\orca\workspaces\BrowserMoji\main\data")
STEP3_DIR = Path(r"C:\Users\kazuh\orca\workspaces\BrowserMoji\main\experiment\explore-1\step3\edlines-cells\out\edp-bilateral")
HERE = Path(__file__).resolve().parent
OUT_BASE = HERE / "out"
MONTAGE_DIR = HERE / "montage"
MAX_SIDE = 1280
CELL = 16
JPEG_QUALITY = 90

MIN_SEG_POINTS = 5        # baseline (step3)
MIN_SEG_POINTS_COHERENT = 15
GRADIENT_THRESHOLD = 32
GRADIENT_THRESHOLD_GRAD20 = 20
COHERENT_MAX_RATIO = 0.5  # perp_var / par_var above this => discard (curvy segment)


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


def bilateral(gray: np.ndarray) -> np.ndarray:
    return cv2.bilateralFilter(gray, d=7, sigmaColor=30, sigmaSpace=7)


def _detect(gray: np.ndarray, grad: int) -> list:
    ed = cv2.ximgproc.createEdgeDrawing()
    params = ed.Params()
    params.GradientThresholdValue = grad
    params.AnchorThresholdValue = 8
    ed.setParams(params)
    ed.detectEdges(gray)
    return ed.getSegments()  # point lists as (x, y)


def _is_straight(pts: np.ndarray) -> bool:
    """True if the segment is straight enough (low perpendicular spread)."""
    if len(pts) < 3:
        return True
    c = pts - pts.mean(axis=0)
    cov = c.T @ c / len(c)
    vals, vecs = np.linalg.eigh(cov)  # ascending eigenvalues
    par_var, perp_var = vals[1], vals[0]
    if par_var <= 0:
        return perp_var <= 0
    return perp_var / par_var <= COHERENT_MAX_RATIO


def get_segments(gray: np.ndarray, variant: str) -> list:
    if variant == "clahe":
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        src = bilateral(clahe.apply(gray))
        segs = _detect(src, GRADIENT_THRESHOLD)
        return [s for s in segs if len(s) >= MIN_SEG_POINTS]
    if variant == "grad20":
        src = bilateral(gray)
        segs = _detect(src, GRADIENT_THRESHOLD_GRAD20)
        return [s for s in segs if len(s) >= MIN_SEG_POINTS]
    if variant == "coherent":
        src = bilateral(gray)
        segs = _detect(src, GRADIENT_THRESHOLD)
        out = []
        for s in segs:
            if len(s) < MIN_SEG_POINTS_COHERENT:
                continue
            if not _is_straight(np.asarray(s, dtype=np.float64)):
                continue
            out.append(s)
        return out
    raise ValueError(variant)


def render_cells(gray: np.ndarray, segments: list) -> np.ndarray:
    h, w = gray.shape
    gh = (h + CELL - 1) // CELL
    gw = (w + CELL - 1) // CELL
    ph, pw = gh * CELL, gw * CELL
    padded = np.full((ph, pw), int(gray.mean()), np.uint8)
    padded[:h, :w] = gray
    cells = padded.reshape(gh, CELL, gw, CELL).mean(axis=(1, 3)).astype(np.uint8)
    # getSegments() returns points as (x, y); polylines expects (x, y) -> do NOT flip
    pts = [np.rint(s / CELL).astype(np.int32) for s in segments]
    cv2.polylines(cells, pts, isClosed=False, color=255, thickness=1, lineType=cv2.LINE_8)
    return cells


def montage(gray: np.ndarray, panels: list) -> np.ndarray:
    h, w = gray.shape
    gap, label_h = 4, 24
    total_w = len(panels) * w + (len(panels) - 1) * gap
    canvas = np.full((label_h + h, total_w, 3), 255, np.uint8)
    x = 0
    for name, img in panels:
        if img.shape != (h, w):
            # step3 outputs are cell grids (1/CELL size); upscale with NEAREST
            img = cv2.resize(img, (w, h), interpolation=cv2.INTER_NEAREST)
        bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        cv2.putText(canvas, name, (x + 4, label_h - 6), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, 0, 1, cv2.LINE_AA)
        canvas[label_h:, x:x + w] = bgr
        x += w + gap
    return canvas


def main() -> None:
    files = sorted(p for p in DATA_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    variants = ["clahe", "grad20", "coherent"]
    outdirs = {v: OUT_BASE / v for v in variants}
    for v in variants:
        outdirs[v].mkdir(parents=True, exist_ok=True)
    MONTAGE_DIR.mkdir(parents=True, exist_ok=True)

    for p in files:
        gray = load_gray(p)
        results = {}
        for v in variants:
            segs = get_segments(gray, v)
            cells = render_cells(gray, segs)
            ok, buf = cv2.imencode(".jpg", cells, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            outpath = outdirs[v] / (p.stem + ".jpg")
            buf.tofile(str(outpath))
            results[v] = cells
            npx = int((cells == 255).sum())
            print(f"{v}: {p.name} segs={len(segs)} edge_cells={npx}")

        # montage: original + step3 edp-bilateral + 3 variants
        step3_path = STEP3_DIR / (p.stem + ".jpg")
        data3 = np.fromfile(str(step3_path), dtype=np.uint8)
        step3_img = cv2.imdecode(data3, cv2.IMREAD_GRAYSCALE)
        if step3_img is None:
            step3_img = gray
        panels = [("original", gray), ("step3-bilat", step3_img)] + [(v, results[v]) for v in variants]
        m = montage(gray, panels)
        ok, mbuf = cv2.imencode(".jpg", m, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        mpath = MONTAGE_DIR / (p.stem + ".jpg")
        mbuf.tofile(str(mpath))
        print(f"montage: {mpath.name}")
    print("done")


if __name__ == "__main__":
    sys.exit(main())
