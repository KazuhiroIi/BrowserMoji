# e2e テスト（実機テストの自動化）

実機での撮影テストを毎回行わなくて済むようにする自動テスト。`data/sample.mp4`（実機で撮影した映像）を入力に、Playwright + Chromium でアプリを動かして計測する。

## 目的と限界

- **目的**: 相対値のリグレッション検知（変更前後で同一条件なら何倍遅くなったか）と、出力の正しさの確認（黒画面・白画面・出力崩れの検出）
- **限界**: GPU は実機スマホのものではない（デスクトップ GPU またはヘッドレスの SwiftShader）。**「低スペック実機で何 fps 出るか」という絶対値は取れない**。絶対値は引き続き実機テストで確認する
- **入力側の上限**: テストでは video 要素 + `captureStream()` でカメラを代用する。開発機のように CPU がパイプラインで飽和すると、映像のプレゼンテーション（camFps）自体が数 fps に落ちる。パイプラインをそこまで高速化した場合はこの上限が計測値を打ち消すようになるので、入力側の負荷（クリップの解像度など）を見直す

## 準備

```sh
npm install
npx playwright install chromium   # 初回のみ
npm run test:media                # data/sample30.webm / data/still30.webm / data/test-frame.png を生成（ffmpeg が必要）
```

- テスト用クリップは 30fps に間引いている（実機カメラの実効 fps に合わせる。元の sample.mp4 は 120fps 撮影）
- Playwright 同梱の Chromium は H.264 を再生できないため VP9/WebM でエンコードする
- `still30.webm` は 1 フレームから作った **lossless** VP9 動画（全フレームが pixel 等価）。正しさの pixel 比較の入力に使う
- 注意: ヘッドレス Chromium では `canvas.captureStream()` 由来の MediaStream で `requestVideoFrameCallback` が発火しない（実測）。そのため入力はすべて video 要素 + `video.captureStream()` に統一している
- 生成物は `data/` 配下（.gitignore 済み）。pixel 比較の基準画像も `data/baselines/` に自動保存される（環境依存のため git 管理しない）

## 実行

```sh
npm run test:e2e    # 正しさの確認（ヘッドレス）
npm run test:perf   # 性能計測（headed。CPU スロットリング 1x / 4x / 20x）
```

どちらも対象は**本番ビルド**（`npm run build && npm run preview` を webServer 設定が自動実行する）。dev server は最適化前コードで数値が変わるため使わない。

## 正しさの確認（test:e2e）

1. **動画ストリームモード**: `getUserMedia` をスタブし、`sample30.webm` を再生する video 要素をカメラの代わりに渡す。アプリは通常どおり開始ボタンから起動し、描画が継続・画面が一色でない・時間変化することを確認する
2. **固定フレームモード**: 全フレーム同一の動画（`still30.webm`）を入力にして、WebGL2 と Canvas 2D の出力をそれぞれ基準画像と pixel 比較する（pixelmatch、許容 < 1%）。実測では同一方式の再実行で差分 0.000% になる
3. **2 方式の比較**: WebGL2 と Canvas 2D（基準実装、N-4）の出力差分率を記録する

基準画像は初回実行時（またはサイズ変更時）に自動保存される。意図的な見た目の変更をしたら `data/baselines/*.png` を削除して再生成する。

### 既知の発見（2026-11-08 時点）

- **WebGL2 と Canvas 2D の出力は pixel レベルで大きく異なる**（同一入力・同一文字選択でも差分率 約 57%）。大構造（シルエット・濃淡）は一致するが、グリフの描かれ方が違う。差分率は毎回決定的に同じ値になるため、テストは固定の閾値ではなく**前回記録との一致**（ずれ < 0.5pt）を検査する。どちらかの描画方式に変更を入れたらこの値が動く
- スクリーンショットの前に fps 表示を OFF・設定パネルを閉じる（オーバーレイが canvas に写り込むため。fps の数字は実行ごとに変わるので基準比較のノイズになる）

## 性能計測（test:perf）

- CDP `Emulation.setCPUThrottlingRate` で CPU を 1x / 4x / 20x に遅くして計測する
- 1x が「同じマシンでの参照値」。4x / 20x は CPU が律速する状況の近似
- **fps は累積フレームカウンタ（`window.__bmTest.getFrameStats()`）の差分から出す**。FpsStats の 5 秒窓は 1 秒以上のフレーム間隔で窓を立て直すため、低 fps 条件では窓ベースの値が 0 になる（avgFps / minFps / camFps は参考値として記録）
- ステージ別 ms も累積値の差分から区間平均を出す
- 結果は `results/perf-latest.json` に保存され、**前回実行との差分が表で表示される**。履歴は `results/perf-history/` に残る
- 合否判定はしない。低 fps 環境では実行間の揺らぎが ±10% 程度あるので、傾向を見る
- WebGL2 がフォールバックしていたらテストを失敗させる（計測条件が変わるため）

### 開発機での参考値（2026-11-08、viewport 390x844 / dpr 2 / columns 100）

| CPU | fps | feat(ms) |
|---|---|---|
| 1x | 1.2〜1.4 | 650〜730 |
| 4x | 0.3 | 約 2700 |
| 20x | 0.04 | 約 21000 |

特徴量計算（feat）が支配的。1x の値は「このマシンの参照値」であり実機の速度とは無関係。

## アプリ側の変更点

- `src/ui/testHook.ts`: `window.__bmTest` を公開する小さなモジュール。本番ビルドにも含まれるが、影響は window へのオブジェクト登録のみ
  - `getFpsSnapshot()`: FpsStats の 5 秒窓の統計
  - `getFrameStats()`: 起動からの累積フレーム数とステージ別処理時間の合計（窓に依存しない計測用）
  - `getRenderer()` / `isRunning()`: 実効描画方式とフレームループの生存
