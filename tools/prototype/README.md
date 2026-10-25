# tools/prototype — Python 試作・実験環境（EXP-2 / EXP-3 前段）

BrowserMoji の文字選択方式（architecture.md §3）と文字セット（§10 EXP-3）を
PC 上の Python で比較するための基準実装。ここで作った出力
（グリフアトラス + 特徴量テーブル + 変換例）は、後の週で Web 側のダミー資産と
差し替える本物の資産になる（architecture.md §4）。

- Python 3.12 系 / uv で環境を固定（`uv sync`）
- Web カメラは使わない（静止画のみ）。実機写真は `data/` 配下に置く想定で、
  CLI の `--input` で差し替えられる
- 参照ドキュメント: docs/architecture.md §3・§4・§10、docs/requirements.md §8

## 構成

```
tools/prototype/
  pyproject.toml      # 依存: numpy / Pillow / opencv-python-headless / fonttools
  charset.py          # 文字セット候補の定義（4 群 + 実験用プリセット）
  glyphfeat.py        # 特徴量計算（アトラス生成と実行時で共有する基準実装）
  atlas.py            # グリフアトラス PNG + 特徴量テーブル JSON の生成
  synth.py            # 合成入力画像の生成（実機写真が用意されるまでの代用）
  selector.py         # 方式 A / 方式 B の文字選択（基準実装）
  render.py           # 選択結果 → 画像の描画（アトラスからタイル転写）
  convert.py          # 静止画 → ASCII 変換（A/B の比較 PNG を出力）
  bench.py            # 1 フレーム処理時間の計測（EXP-2 の数値）
  sheet.py            # 群ごとの文字シート画像（EXP-3 の資料）
  fonts/              # Noto Sans JP（コミットしない・後述）
  out/                # 生成物（すべて再生成可能）
    assets/           #   atlas.png / features.json
    synth/            #   合成入力画像
    compare/          #   入力 + A + B を縦に並べた比較 PNG
    ascii/            #   方式ごとの単体出力
    charset/          #   群ごとの文字シート
    bench*.json       #   計測値
```

## セットアップと実行

```sh
cd tools/prototype
uv sync                                        # 環境を構築（Python 3.12）
uv run python atlas.py                         # 1. アトラス + 特徴量テーブル生成
uv run python synth.py                         # 2. 合成入力画像を生成
uv run python convert.py --synth --cols 80     # 3. 全合成画像を A/B 変換
uv run python convert.py --input path/to.png --cols 80   # 実機写真など任意の 1 枚
uv run python bench.py                         # 4. 処理時間の計測
uv run python sheet.py                         # 5. 群ごとの文字シート
```

主なオプション:

| スクリプト | オプション |
|---|---|
| `atlas.py` | `--cell 64`（セル px）, `--fs 16`（特徴量計算用のセル内部解像度）, `--charset all`, `--font` |
| `convert.py` | `--input`（複数回指定可）または `--synth`, `--cols 80`, `--charset all`, `--edge-thr 0.14` |
| `bench.py` | `--input`, `--cols 48,80,120`, `--trials 7` |

注意: `convert.py` / `bench.py` / `sheet.py` は `out/assets/features.json` の
`charsetPreset` と `--charset` の一致を確認する。文字セットを変えて実験するときは
先に `atlas.py --charset <preset>` を再実行する。

## 文字セット候補（charset.py）

4 群・合計 212 文字（Noto Sans JP Regular にすべて収録されていることを確認済み）。

| 群 | 文字数 | 濃度の計測値（16×16 換算） | 役割 |
|---|---|---|---|
| density 濃度記号 | 16 | 0.000（全角スペース）〜 0.640（■） | 方式 A の輝度 → 濃度対応。`　・：∴◇○□△☆◎※▲◆★●■` |
| line 線記号 | 35 | 0.029 ─ 〜 0.219 ╋ | エッジの向き・太さ。`─━│┃┌…╋═║╭…╳／＼｜` |
| hiragana かな | 71 | 0.099 〜 0.261 | 五十音＋濁点・半濁点 |
| katakana かな | 71 | 0.084 〜 0.209 | 同上（カタカナ） |
| kanji 漢字 | 19 | 0.075（一）〜 0.331（黒・森） | 濃度の異なる少数の漢字 |

実験用プリセット: `density` / `line` / `symbols`(1+2) / `hiragana` / `kana`(かな全部) /
`all`（既定）。方式 A のエッジ置換は、向きが一意でない角・T 字を除いた
「まっすぐな線」サブセット（`STRAIGHT_LINE_CHARS`）を使う（T-5 の調整に相当）。

## 特徴量テーブル（out/assets/features.json）

2 トラック契約①のスキーマ。文字 1 件 = 25 次元の特徴量 + メタ情報。

```jsonc
{
  "meta": {
    "schemaVersion": 1,
    "featureVersion": 1,
    "font": "NotoSansJP-Regular.otf",
    "fontLicense": "OFL-1.1",
    "charsetPreset": "all",
    "cellPx": 64,            // アトラス 1 セルのpx（正方形）
    "featurePx": 16,         // 特徴量計算に使うセル内部の解像度
    "atlasCols": 16,         // アトラス PNG の列数
    "atlasRows": 14,
    "charCount": 212,
    "directionsDeg": [0, 22.5, 45, 67.5, 90, 112.5, 135, 157.5],
    "regionGrid": [4, 4],
    "counts": { "density": 16, "line": 35, "hiragana": 71, "katakana": 71, "kanji": 19 },
    "note": "id はアトラス内の位置（行優先）と一致する。density/dir8/region4 は 0..1。"
  },
  "chars": [
    {
      "id": 30,              // charID。アトラス PNG のタイル位置（行優先）と一致
      "char": "┃",
      "group": "line",       // density | line | hiragana | katakana | kanji
      "subgroup": null,      // かなのみ: gojuon | dakuten | handakuten
      "density": 0.163,      // 平均インク率 0..1（1 = 黒一様）
      "dir8": [0.11, 0.17, 0.27, 0.54, 1.0, 0.54, 0.27, 0.17],  // 8 方向の線分強度
      "region4": [ ... ]     // 4×4 領域の濃淡パターン（行優先で 16 個、0..1）
    }
  ]
}
```

### 特徴量の定義（glyphfeat.py）

- **density**: セル（featurePx=16 換算）の平均インク率。インク = 1 − 輝度
- **dir8（8 方向の線分強度）**: 「線検出フィルタ（DoL: 中心線 − 両隣のフランク線）」
  を 8 方向（0°, 22.5°, …, 157.5°、画像座標・y 下方向）に適用し、**セル内の最大応答**
  を取る。正規化は「カーネル自身の中心リッジ（ピーク 1.0 のガウス細線）」への
  最大応答 = 1 となるマッチドフィルタ基準。つまり dir8 ≈「その方向に、カーネルの
  横断面プロファイルに一致する線がどれだけ濃く通っているか」
  - 一様塗りつぶし → 0（フランク減算で打ち消される）
  - 単調なグラデーション（エッジの面）→ 0 に近い（一次変化も打ち消される）
    ……エッジの向きは方式 A では Sobel 勾配から取る（後述）
  - 細い線（┃ など）→ 1 に近い
- **region4**: セルを 4×4 領域に分けた各領域の平均インク率（行優先 16 個）

セル特徴量もまったく同じ関数で計算する（入力画像を cols×fs, rows×fs に縮小して
同じ 16×16 換算で求める）。これが「アトラス生成と実行時で同じコードを共有」の実装。

## 文字選択方式（selector.py）

### 方式 A（SelectorA）— 輝度 → 濃度文字、エッジは線文字へ

1. セルの平均輝度 → インク率 → 濃度記号群の中で最も近い濃度の文字
2. セル内最大 |Sobel 勾配| が `EDGE_THRESHOLD`(0.14) 以上のセルは、勾配の向きに
   最も近い線記号へ置換する。向き = 平均勾配ベクトルから `atan2(−gx, gy)`
   （画像座標。線の向き = 勾配と直交）、太さは勾配強度で段階選び
   （線記号ごとの向きは、アトラスの dir8 から 2 倍角の円周平均で求める）
3. 整合性（|平均勾配ベクトル| / 平均 |勾配|）が低いセル（細い線など、向きが
   打ち消し合う場合）は置換しない。境界を含まない隣接セル（max だけ高い）も除外

### 方式 B（SelectorB）— 重み付き最近傍

セル特徴量 [density, dir8, region4] と全文字の特徴量の重み付き二乗距離:

```
D² = W_DENSITY·(Δdensity)² + W_DIR8·mean(Δdir8²) + W_REGION4·mean(Δregion4²)
   = 1.0·(Δd)²     + 1.0·(Δdir8 の平均) + 0.7·(Δregion4 の平均)
```

- 線分が検出できない平滑セル（dir8 最大値 < `LINENESS_MIN`(0.15)）では
  dir8 ブロックを比較せず、線文字も候補から外す
  （薄い線文字が平滑な中間調に吸われて「すじ状ノイズ」になるのを防ぐ）
- 距離計算は `||a||² + ||b||² − 2a·b` の形で BLAS に渡す（セル数 × 文字数 × 25 次元）

調整パラメータは config.py に集約（EDGE_THRESHOLD / COHERENCE_MIN /
W_DENSITY / W_DIR8 / W_REGION4 / LINENESS_MIN）。

## 実機写真の扱い

実機写真はリポジトリの `data/` 配下に置く想定（別契機で追加される）。
`uv run python convert.py --input ../../data/photo.jpg --cols 80` のように
パスを渡すだけで差し替わる。合成画像（synth.py）はコードで生成するため
リポジトリに画像をコミットする必要がない。

## フォントとライセンス

- 使用フォント: **Noto Sans JP Regular**（`fonts/NotoSansJP-Regular.otf`、4.5MB）
- 取得元: notofonts/noto-cjk の公式 GitHub リリース
  `Sans2.004` タグの `16_NotoSansJP.zip`（Region Specific Subset OTFs Japanese）
  <https://github.com/notofonts/noto-cjk/releases/tag/Sans2.004>
- ライセンス: **SIL Open Font License Version 1.1（OFL-1.1）**
  - 確認: 同リポジトリ `Sans/LICENSE`（2026-10-25 参照）に
    「This Font Software is licensed under the SIL Open Font License, Version 1.1」
    と明記されているのを確認。OFL-1.1 はフォント単体の販売禁止・同梱可・
    修正版の名前扱いに条件があるが、Web アプリへの同梱（アトラス化を含む）は
    許可される。リポジトリのライセンスとの矛盾はない（N-7）
- **`fonts/` はコミットしない**。取得は上記リリースから行う（.gitignore の担当は
  別ワーカーのため、ここでは本 README での取り決めのみ記す）
- `out/` 配下はすべてスクリプトで再生成できる（生成物のコミット要否は別途判断）

## 既知の限界・次の週以降

- アトラス生成は `tools/atlas/` への分離が計画通りなら後の週（architecture.md §9）
- 計測は PC の CPU（Python/numpy/OpenCV）による基準実装の相対比較。実機 fps は
  Web 側（GPU 描画）の EXP-1・実機計測で別途確認する
- 方式 B の平滑領域で同一文字が反復しやすい（田 の連続など）→ 時間・空間方向の
  変化項（F-14 のちらつき抑制と共通）や文字の多様化が候補
- 実機写真での再評価（合成画像は極端にきれいなエッジ・グラデーションを持つ）
