# -*- coding: utf-8 -*-
"""Build labelled montages: original + EDPF variants per input image."""
from pathlib import Path

import cv2
import numpy as np

DATA_DIR = Path(r"C:\Users\kazuh\orca\workspaces\BrowserMoji\main\data")
HERE = Path(__file__).resolve().parent
OUT_BASE = HERE / "out"
MONTAGE_DIR = HERE / "montage"
VARIANTS = ["edp-default", "edp-noise-filtered"]
TILE_H = 480
LABEL_H = 28


def load_img(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    scale = TILE_H / h
    return cv2.resize(img, (int(w * scale), TILE_H), interpolation=cv2.INTER_AREA)


def label(img: np.ndarray, text: str) -> np.ndarray:
    bar = np.zeros((LABEL_H, img.shape[1], 3), np.uint8)
    cv2.putText(bar, text, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    return np.vstack([bar, img])


def main() -> None:
    MONTAGE_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in DATA_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    for p in files:
        tiles = [label(load_img(p), f"original: {p.name}")]
        for v in VARIANTS:
            ep = OUT_BASE / v / (p.stem + ".jpg")
            tiles.append(label(load_img(ep), v))
        hmax = max(t.shape[0] for t in tiles)
        tiles = [cv2.copyMakeBorder(t, 0, hmax - t.shape[0], 0, 0, cv2.BORDER_CONSTANT) for t in tiles]
        montage = np.hstack(tiles)
        ok, buf = cv2.imencode(".jpg", montage, [cv2.IMWRITE_JPEG_QUALITY, 90])
        buf.tofile(str(MONTAGE_DIR / f"{p.stem}.jpg"))
        print("montage:", p.stem)
    print("done")


if __name__ == "__main__":
    main()
