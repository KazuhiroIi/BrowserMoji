# -*- coding: utf-8 -*-
"""XDoG / DoG line drawing variants for AA character selection exploration."""
import os
import glob
import numpy as np
import cv2

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = r"C:\Users\kazuh\orca\workspaces\BrowserMoji\main\data"
OUT = os.path.join(BASE, "out")
MONTAGE = os.path.join(BASE, "montage")

VARIANTS = ["xdog-soft", "xdog-standard", "dog-binary"]

PARAMS = {
    # sigma, k, p (sharpen), epsilon, phi, gamma  (eps: fraction of local contrast)
    "xdog-soft":     dict(sigma=1.0, k=1.6, p=20, eps=0.10, phi=10, gamma=0.98),
    "xdog-standard": dict(sigma=0.5, k=1.6, p=30, eps=0.06, phi=15, gamma=0.98),
    "dog-binary":    dict(sigma=0.7, k=1.6, p=None, eps=0.10, phi=None, gamma=1.0),
}


def to_gray_float(path, max_w=1280):
    img = cv2.imread(path)
    if img is None:
        raise IOError(path)
    h, w = img.shape[:2]
    if w > max_w:
        img = cv2.resize(img, (max_w, int(h * max_w / w)), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float64) / 255.0
    return img, g


def dog(gray, sigma, k):
    g1 = cv2.GaussianBlur(gray, (0, 0), sigma)
    g2 = cv2.GaussianBlur(gray, (0, 0), sigma * k)
    return g1 - g2  # positive where brighter than surround (edge-like)


def xdog(gray, sigma, k, p, eps, phi, gamma):
    """XDoG: white lines (255) on black background.
    Adaptive threshold: lines where u dips below the local mean (dark side of edges)."""
    d = dog(gray, sigma, k)
    u = gray + p * d  # sharpened image
    lmean = cv2.GaussianBlur(u, (0, 0), max(15, sigma * 10))  # local luminance
    diff = lmean - u  # positive where darker than local mean (edge dark side)
    diff = diff / max(diff.max(), 1e-6)
    # soft threshold: T = 1 (background) when diff <= eps, else tanh ramp
    T = np.where(diff <= eps, 1.0, 1.0 + np.tanh(phi * (eps - diff)))
    line = 1.0 - T  # high on line side
    line = np.clip(line * gamma, 0, 1)
    return (line * 255).astype(np.uint8)


def dog_binary(gray, sigma, k, eps, gamma):
    """DoG zero-crossing (Marr-Hildreth style) binarized: white lines on black."""
    d = dog(gray, sigma, k)
    zc = (d[:-1, :-1] * d[1:, :-1] < 0) | (d[:-1, :-1] * d[:-1, 1:] < 0)
    strength = np.abs(d)[:-1, :-1]
    thr = max(strength.max() * eps, 1e-6)
    sig = (strength > thr)
    mask = (zc & sig).astype(np.uint8)
    # pad back to original size
    full = np.zeros_like(d, dtype=np.uint8)
    full[:-1, :-1] = mask
    mask = full
    # dilate by 1 so lines stay connected
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
    return (mask * gamma).astype(np.uint8) * 255


def process():
    files = sorted(
        [f for f in glob.glob(os.path.join(DATA, "*.jpg")) + glob.glob(os.path.join(DATA, "*.png"))]
    )
    print(f"input files: {len(files)}")
    os.makedirs(MONTAGE, exist_ok=True)
    counts = {v: 0 for v in VARIANTS}
    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        src, gray = to_gray_float(path)
        results = {}
        for v in VARIANTS:
            prm = PARAMS[v]
            if v == "dog-binary":
                img = dog_binary(gray, prm["sigma"], prm["k"], prm["eps"], prm["gamma"])
            else:
                img = xdog(gray, prm["sigma"], prm["k"], prm["p"], prm["eps"], prm["phi"], prm["gamma"])
            outdir = os.path.join(OUT, v)
            os.makedirs(outdir, exist_ok=True)
            cv2.imwrite(os.path.join(outdir, name + ".jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            results[v] = img
            counts[v] += 1

        # montage: original + 3 variants, labeled
        h, w = gray.shape
        scale = 480.0 / h
        tw = max(1, int(w * scale))
        tiles = []
        for label, im in [("original", src)] + [(v, cv2.cvtColor(results[v], cv2.COLOR_GRAY2BGR)) for v in VARIANTS]:
            t = cv2.resize(im, (tw, 480), interpolation=cv2.INTER_AREA if im.shape[0] > 480 else cv2.INTER_CUBIC)
            tile = t.copy()
            cv2.rectangle(tile, (0, 0), (tw, 36), (0, 0, 0), -1)
            cv2.putText(tile, label, (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
            tiles.append(tile)
        montage = np.hstack(tiles)
        cv2.imwrite(os.path.join(MONTAGE, name + ".jpg"), montage, [cv2.IMWRITE_JPEG_QUALITY, 90])
        print("done:", name)
    print("counts:", counts)


if __name__ == "__main__":
    process()
