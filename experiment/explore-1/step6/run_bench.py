# -*- coding: utf-8 -*-
"""step6: 全5手法 × 15画像のベンチマーク実行。

score.py (explore-2/step1) をモジュールとして読み込み、score_image で採点。
結果: step6/results.md (MEAN 表 + 画像別詳細) と step6/results.csv
"""
import csv
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SCORE_STEP = Path(r"C:\Users\kazuh\orca\workspaces\BrowserMoji\main\experiment\explore-2\step1")
sys.path.insert(0, str(SCORE_STEP))
sys.path.insert(0, str(HERE))

import score  # noqa: E402
import predictors  # noqa: E402

METHODS = {
    "baseline": predictors.predict_baseline,
    "canny": predictors.predict_canny,
    "pca": predictors.predict_pca,
    "nms": predictors.predict_nms,
    "b2": predictors.predict_b2,
}

KEYS = ["F1_cell", "P_cell", "R_cell", "skel_P", "skel_R", "skel_F1", "dist_decay"]


def main():
    names = [p.stem for p in sorted(score.WORK.glob("*.jpg"))]
    names = [n for n in names if (score.WORK / "orig" / f"{n}.jpg").exists()]
    print(f"images: {len(names)}")

    all_results = {}
    for mname, fn in METHODS.items():
        all_results[mname] = [score.score_image(n, fn) for n in names]
        r = all_results[mname][-1]
        print(f"  done: {mname} ({r['image']})")

    # --- CSV ---
    with open(HERE / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["method"] + KEYS)
        for mname in METHODS:
            w.writerow([mname] + [round(float(np.mean([r[k] for r in all_results[mname]])), 4) for k in KEYS])
        for mname in METHODS:
            for r in all_results[mname]:
                w.writerow([f"{mname}:{r['image']}"] + [r[k] for k in KEYS])

    # --- Markdown ---
    lines = []
    lines.append("# step6: セル単位エッジマス分類 ベンチマーク結果\n")
    lines.append(f"採点画像: {len(names)} 枚 ({', '.join(names)})  ")
    lines.append("グリッド: 幅1600px, cols=100, 16pxセル。主指標 = skel_F1。\n")
    lines.append("手法:\n")
    lines.append("- baseline: Sobel 勾配上位15%セル (score.py 標準)")
    lines.append("- canny: bilateral→Canny(50,150) セル内エッジ画素比率>0.1")
    lines.append("- pca: 同エッジマップで セル内エッジ画素≥15 & PCA σ2/σ1<0.25")
    lines.append("- nms: セル強度(エッジ画素数) 半径2局所最大 & 下限5px")
    lines.append("- b2: PCA判定→8近傍主軸差≤45°チェーン(長さ≥3)→孤立成分(<5セル)除去\n")
    lines.append("## MEAN\n")
    lines.append("| method | " + " | ".join(KEYS) + " |")
    lines.append("|---|" + "---|" * len(KEYS))
    for mname in METHODS:
        vals = [np.mean([r[k] for r in all_results[mname]]) for k in KEYS]
        lines.append(f"| {mname} | " + " | ".join(f"{v:.4f}" for v in vals) + " |")
    lines.append("")
    for mname in METHODS:
        lines.append(f"## 詳細: {mname}\n")
        lines.append("| image | pred_cells | gt_cells | " + " | ".join(KEYS) + " |")
        lines.append("|---|---|---|" + "---|" * len(KEYS))
        for r in all_results[mname]:
            lines.append(f"| {r['image']} | {r['edge_cells_pred']} | {r['edge_cells_gt']} | "
                         + " | ".join(f"{r[k]:.4f}" for k in KEYS) + " |")
        vals = [np.mean([r[k] for r in all_results[mname]]) for k in KEYS]
        lines.append(f"| **MEAN** | | | " + " | ".join(f"**{v:.4f}**" for v in vals) + " |")
        lines.append("")
    (HERE / "results.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote results.md / results.csv")


if __name__ == "__main__":
    main()
