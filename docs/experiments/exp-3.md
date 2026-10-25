# EXP-3: 文字セット候補の比較（T-4 / Q-7）

状態: **草稿（シート生成済み）**。濃淡の階調の幅とエッジ表現の質の評価はユーザーが行う。
- 関連: architecture.md §10（EXP-3）、requirements.md §8（T-4, T-5）、docs/decisions/D-002（契約①）
- 実装: `tools/prototype/charset.py`（候補定義）、`sheet.py`（シート生成）

## 目的

文字セット候補（4 群）を Noto Sans JP Regular で描画したシートを確認し、

- 濃淡の階調の幅が十分か（density 群の段階が視覚的に均等か）
- エッジ表現の質（line 群の向きのバリエーションが十分か）
- かな・漢字を混ぜたときの質感と濃度の隙間（階調の谷）の有無

を見て、採用する文字セットの範囲を打ち切り決定する。

## 文字セット候補（tools/prototype/charset.py）

| 群 | 文字数 | 内容 |
|---|---|---|
| density | 16 | 全角スペース〜■ の濃度段階 |
| line | 35 | ―─｜│／＼╱╲ などの線・枠記号（向きのバリエーション） |
| hiragana | 71 | 五十音＋濁点・半濁点 |
| katakana | 71 | カタカナ＋濁点・半濁点 |
| kanji | 19 | 濃度の異なる少数の漢字 |

合計 212 文字。Noto Sans JP Regular（OFL-1.1）にすべて収録されることを生成時に確認済み。
フォント実体はリポジトリにコミットしない（`.gitignore` で `tools/prototype/fonts/` を除外。ライセンスは tools/prototype/README.md に記録）。

## 生成コマンドと出力

```sh
cd tools/prototype
uv run python sheet.py   # → out/charset/{density,line,hiragana,katakana,kanji}.png
```

シートは群ごとに、測定した濃度（density: 0..1）の順に並べてある。
特徴量テーブル `out/assets/features.json`（schemaVersion 1、charCount 212、cellPx 64、featurePx 16、dir8 = 8 方向、region4 = 4×4）の `chars[]` は `id / char / group / subgroup / density / dir8 / region4` のキーを持ち、契約①（D-002）と一致する。

## 確認項目（評価用チェックリスト）

- [ ] density 群の 16 段階が視覚的に均等に並ぶか
- [ ] line 群に、水平・垂直・斜め（45° / 135°）の線が揃っているか
- [ ] かな・漢字を混ぜたとき、濃度の谷（段階間の隙間）ができないか
- [ ] 不要な群はないか（例: ひらがなとカタカナのどちらか一方で足りるか）
- [ ] 漢字群の 19 文字が濃い領域の質感として適切か

## 決定事項

（未決定 — ユーザーの評価待ち。評価結果はここに追記する）
