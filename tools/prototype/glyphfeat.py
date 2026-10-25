"""特徴量計算（アトラス生成と実行時の両方で共有する基準実装）。

特徴量（2 トラック契約①のスキーマ）:
  - density   : 平均インク率 0..1（1 = 黒一様 / 0 = 白）
  - dir8      : 8 方向（0,22.5,...,157.5°）の線分強度 0..1
  - region4   : 4×4 領域の濃淡パターン 0..1（16 個、行優先）

線分強度は「線検出フィルタ（中心線 − 両隣のフランク線）」で求め、
セル内の最大応答で集約する。一定塗りつぶしは 0 に、中心付近を通る
細い線は 1 に近づく。単調なグラデーション（エッジの面）には 0 に近い
値を返す（一次変化はフランク減算で打ち消される）。

座標系: 画像座標（x 右、y 下）。角度はこの座標系での線の向き。
"""

from __future__ import annotations

import cv2
import numpy as np

DIRECTIONS_DEG: tuple[float, ...] = (0.0, 22.5, 45.0, 67.5, 90.0, 112.5, 135.0, 157.5)
N_DIR = len(DIRECTIONS_DEG)
REGION = 4  # 4×4 領域パターン


# --- 基本変換 ---------------------------------------------------------------

def ink_from_gray(gray01: np.ndarray) -> np.ndarray:
    """輝度 0..1（1=白）→ インク 0..1（1=黒）。"""
    return 1.0 - gray01


def block_mean(img: np.ndarray, rows: int, cols: int, fs: int) -> np.ndarray:
    """(rows*fs, cols*fs) の画像を rows×cols ブロックに分けて平均。"""
    h, w = img.shape
    assert h == rows * fs and w == cols * fs, f"size mismatch: {img.shape} vs {rows}x{cols}@{fs}"
    return img.reshape(rows, fs, cols, fs).mean(axis=(1, 3))


def block_max(img: np.ndarray, rows: int, cols: int, fs: int) -> np.ndarray:
    """(rows*fs, cols*fs) の画像を rows×cols ブロックに分けて最大値。

    線分強度はセル内の「最大応答」で見る。DoL フィルタはカーネル総和が 0
    なので、セル平均は線の応答とフランクの負応答で打ち消し合って ~0 になる。
    """
    h, w = img.shape
    assert h == rows * fs and w == cols * fs, f"size mismatch: {img.shape} vs {rows}x{cols}@{fs}"
    return img.reshape(rows, fs, cols, fs).max(axis=(1, 3))


# --- Sobel 勾配（方式 A 用） -------------------------------------------------

def sobel_grads(gray01: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """0..1 輝度画像から Sobel 勾配 (gx, gy) を返す。単位ステップで |g|≈1 に正規化。"""
    gx = cv2.Sobel(gray01, cv2.CV_32F, 1, 0, ksize=3) * 0.25
    gy = cv2.Sobel(gray01, cv2.CV_32F, 0, 1, ksize=3) * 0.25
    return gx, gy


# --- 8 方向線分強度（DoL: Difference of Lines） ------------------------------

def dol_kernel(fs: int, theta_deg: float, length_ratio: float = 0.7) -> np.ndarray:
    """方向 theta_deg（画像座標）の線検出カーネルを生成する。

    K = P − 0.5·F⁺ − 0.5·F⁻
      P : 中心線（長さ length_ratio·fs、横断方向はガウス σ）
      F±: 中心線から ±flank 離れた平行線
    各成分の総和を 1 に揃えるので、一様画像への応答は 0 になる。
    """
    k, _ = _dol_parts(fs, theta_deg, length_ratio)
    return k


def _dol_parts(fs: int, theta_deg: float, length_ratio: float = 0.7) -> tuple[np.ndarray, np.ndarray]:
    """カーネル K と、正規化用の基準線リッジを返す。

    基準リッジは「ピーク値 1.0 のガウス細線（σ はカーネルと同じ、
    長さも同じ）」＝未正規化の P。インクのピーク値スケールで比較するため。
    """
    sigma = max(0.75, fs / 20.0)
    flank = fs / 6.0
    half_len = length_ratio * fs / 2.0

    t = np.arange(fs, dtype=np.float32) - (fs - 1) / 2.0
    x, y = np.meshgrid(t, t)  # x: 横オフセット, y: 縦オフセット（下方向が正）
    th = np.deg2rad(theta_deg)
    ux, uy = np.cos(th), np.sin(th)
    along = x * ux + y * uy
    perp = -x * uy + y * ux

    def ridge(d: np.ndarray) -> np.ndarray:
        g = np.exp(-0.5 * (d / sigma) ** 2)
        taper = np.clip((half_len + 1.5 * sigma - np.abs(along)) / (3.0 * sigma), 0.0, 1.0)
        return g * taper

    p_raw = ridge(perp)
    fp = ridge(perp - flank)
    fm = ridge(perp + flank)
    fp /= fp.sum()
    fm /= fm.sum()
    p = p_raw / p_raw.sum()
    return (p - 0.5 * fp - 0.5 * fm).astype(np.float32), p_raw.astype(np.float32)


def dol_normalizations(fs: int) -> np.ndarray:
    """各方向の正規化定数（マッチドフィルタ基準）。

    「カーネル自身の中心リッジ P（ピーク値 1 のガウス細線）」への最大応答を
    1.0 とみなす。すなわち dir8 ≈ 「その方向に、カーネルの横断面プロファイル
    （σ のガウス）に一致する線がどれだけ濃く通っているか」を表す。
    カーネルと基準線が同じ形なので、方向による条件の差（離散化の偏り）が
    自動的に相殺され、ほぼ等方性になる。
    """
    norms = np.zeros(N_DIR, dtype=np.float32)
    for k, deg in enumerate(DIRECTIONS_DEG):
        ker, p = _dol_parts(fs, deg)
        resp = cv2.filter2D(p, -1, ker, borderType=cv2.BORDER_REPLICATE)
        norms[k] = max(float(resp.max()), 1e-6)
    return norms


def dir8_map(ink: np.ndarray, fs: int, norms: np.ndarray | None = None) -> np.ndarray:
    """インク画像全体に 8 方向の DoL フィルタを適用し、(8, H, W) の応答マップを返す。

    各画素値は「理想的な細線」の最大応答で正規化し 0..1 にクリップする。
    セルごとの強度はこのマップのセル内最大値（block_max）で集約する。
    """
    if norms is None:
        norms = dol_normalizations(fs)
    out = np.empty((N_DIR, ink.shape[0], ink.shape[1]), dtype=np.float32)
    for k, deg in enumerate(DIRECTIONS_DEG):
        ker = dol_kernel(fs, deg)
        resp = cv2.filter2D(ink, -1, ker, borderType=cv2.BORDER_REPLICATE)
        out[k] = np.clip(resp / norms[k], 0.0, 1.0)
    return out


# --- セル特徴量（実行時 / アトラス共通） --------------------------------------

def cell_density(ink: np.ndarray, rows: int, cols: int, fs: int) -> np.ndarray:
    """セルごとの平均インク率 → (rows, cols)。"""
    return block_mean(ink, rows, cols, fs)


def cell_dir8(ink: np.ndarray, rows: int, cols: int, fs: int, norms: np.ndarray | None = None) -> np.ndarray:
    """セルごとの 8 方向線分強度 → (8, rows, cols)。セル内は最大応答で集約。"""
    resp = dir8_map(ink, fs, norms)
    return np.stack([block_max(resp[k], rows, cols, fs) for k in range(N_DIR)])


def cell_region4(ink: np.ndarray, rows: int, cols: int, fs: int) -> np.ndarray:
    """セルごとの 4×4 領域パターン → (rows, cols, 4, 4)。"""
    q = fs // REGION
    assert q * REGION == fs, "feature size must be a multiple of 4"
    v = ink.reshape(rows, fs, cols, fs).transpose(0, 2, 1, 3)  # (rows, cols, fs, fs)
    v = v.reshape(rows, cols, REGION, q, REGION, q)
    return v.mean(axis=(3, 5))


def cell_features_b(ink: np.ndarray, rows: int, cols: int, fs: int, norms=None):
    """方式 B 用のセル特徴量一式を返す。"""
    return (
        cell_density(ink, rows, cols, fs),
        cell_dir8(ink, rows, cols, fs, norms),
        cell_region4(ink, rows, cols, fs),
    )
