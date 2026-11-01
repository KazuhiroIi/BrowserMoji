# D-008: 描画方式は WebGL2 を既定とする（Canvas 2D は基準実装・フォールバック）

- 状態: 🔒（確定）
- 関連: architecture.md §5, EXP-1, D-004, N-4

## 背景

architecture.md §5 は描画方式の候補として DOM / Canvas 2D / WebGL2 の 3 方式を挙げていた（当初は「基準は WebGL2」が推測ベースの順序。D-004）。D-004 により Canvas 2D 版（CPU パイプライン + アトラス転写）を先行実装し、CPU の基準実装（N-4）を兼ねさせた上で、実機計測（EXP-1）で比較して決定することとしていた。その後 WebGL2 版をグリッドシェーダ・1 draw call 方式で追加実装し、context lost 検知・生成失敗時には Canvas 2D へフォールバックする作りにした。

## 選択肢

1. **WebGL2 を既定とする**
2. Canvas 2D を既定とする（現状のまま）
3. DOM（`<pre>`）方式（全角グリッドが端末依存で崩れるため N-5 を満たさず、比較対象から外れている）

## 決定

- 描画方式は **WebGL2** を採用し、AppConfig の `renderer` の既定値を **`'webgl2'`** とする
- **Canvas2DRenderer は CPU の基準実装（N-4）およびフォールバックとして保持する**。WebGL2 のコンテキスト生成失敗・context lost 検知時には自動で Canvas 2D に切り替える
- 設定パネルの「描画方式」選択 UI も残す（`'canvas2d'` / `'webgl2'` を利用者が切り替えられる）
- 計測の詳細は docs/experiments/exp-1.md を参照

## 理由

EXP-1 の実機計測（列数 48・明るめ屋内・各 30 秒以上）より:

- Canvas 2D はアトラスキャッシュ最適化後も draw が moto 27.5 ms / OPPO 19.0 ms に加え、OPPO では計測外の約 31 ms のオーバーヘッドがあり、P-1（30fps）に届かない（avg 20.6 / 16.2 fps）
- WebGL2（グリッドシェーダ・1 draw call）は draw 0.1〜0.3 ms で、両端末ともカメラの実効 fps（moto 29.9 / OPPO 25.0）の上限まで到達した（avg 30.8 / 29.2 fps）
- P-1 は moto で達成（カメラ上限で頭打ち）、P-2 は OPPO で大余裕で達成

残るボトルネック（特徴量計算の GPU 移行・前処理 blit の軽減など）は docs/experiments/exp-1.md の持ち越し事項に記録する。
