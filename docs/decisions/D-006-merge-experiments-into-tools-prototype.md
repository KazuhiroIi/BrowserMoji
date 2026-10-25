# D-006: Python 試作を experiments/ から tools/prototype/ へ統合する

- 状態: 🔒（確定）
- 関連: architecture.md §9

## 背景

試作を急いだ結果、リポジトリ直下に `experiments/`（pyproject.toml・uv.lock など）が作られた。architecture.md §9 のリポジトリ構成では、Python による試作・実験は `tools/prototype/` 配下に置くことになっている。置き場所が 2 つに分かれたままでは、生成ツール（tools/atlas/）とのコード共有（architecture.md §4）がしづらい。

## 選択肢

1. **`experiments/` を `tools/prototype/` に統合する**
2. `experiments/` のまま継続する（構成が 2 重になる）
3. `tools/` をやめて `experiments/` に統一する（architecture.md §9 を書き換える）

## 決定

`experiments/` の内容を **`tools/prototype/` へ統合し、`experiments/` は廃止する**。仮想環境・依存定義（README・pyproject.toml）は tools/prototype/ 側に置く。architecture.md §9 の構成に寄せる。

## 理由

- §9 の構成は「試作（prototype）」と「アトラス生成（atlas）」が同じ tools/ 配下に並ぶ設計で、アルゴリズム試作とアトラス生成のコード共有（§4）が自然にできる
- 構成案を先に決めてある以上、実装側を構成に寄せる方が、ドキュメントと実装の不一致を増やさない
