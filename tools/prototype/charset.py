"""文字セット候補の定義（EXP-3 の比較対象）。

4 群で構成し、合計は数百文字以内に収める:
  1. density  : 濃度記号（輝度 → 濃淡の段階に使う。全角スペース含む）
  2. line     : 線記号（エッジの向きに合わせる線分）
  3. hiragana / katakana : かな（五十音＋濁点・半濁点）
  4. kanji    : 少数の漢字（濃度の異なるもの）

ここで挙げる文字は Noto Sans JP に収録されていることを前提とする
（未収録文字は atlas.py が検出して除外し、警告を出す）。
"""

from __future__ import annotations

# --- 1. 濃度記号（薄 → 濃 の並び。インデックス順は参照用で、実際の濃度は計測値を使う） ---
DENSITY_CHARS = [
    "　",  # 全角スペース（背景 = T-3）
    "・",  # 中黒
    "：",  # 全角コロン
    "∴",  #ゆえに
    "◇",  # 白ダイヤ
    "○",  # 白丸
    "□",  # 白四角
    "△",  # 白三角
    "☆",  # 白星
    "◎",  # 二重丸
    "※",  # こめじるし
    "▲",  # 黒三角
    "◆",  # 黒ダイヤ
    "★",  # 黒星
    "●",  # 黒丸
    "■",  # 黒四角
]

# --- 2. 線記号（向き / 太さのバリエーション） ---
LINE_CHARS = [
    "―",  # 水平バー
    "─", "━",  # 細線 / 太線（横）
    "│", "┃",  # 細線 / 太線（縦）
    "┌", "┐", "└", "┘",  # 細い角
    "├", "┤", "┬", "┴", "┼",  # 細いT字・十字
    "┏", "┓", "┗", "┛",  # 太い角
    "┣", "┫", "┳", "┻", "╋",  # 太いT字・十字
    "═", "║",  # 二重線
    "╭", "╮", "╯", "╰",  # 丸角
    "╱", "╲", "╳",  # 斜線
    "／", "＼",  # 全角斜線
    "｜",  # 全角縦棒
]

# --- 3. かな（五十音＋濁点・半濁点） ---
HIRAGANA_BASE = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
HIRAGANA_DAKU = "がぎぐげござじずぜぞだぢづでどばびぶべぼ"
HIRAGANA_HANDAKU = "ぱぴぷぺぽ"
KATAKANA_BASE = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
KATAKANA_DAKU = "ガギグゲゴザジズゼゾダヂヅデドバビブベボ"
KATAKANA_HANDAKU = "パピプペポ"

# --- 4. 漢字（少数・濃度の異なるもの） ---
KANJI_CHARS = [
    "一",  # 極薄
    "二", "三", "十", "口",
    "人", "大", "小", "中", "山", "川", "田", "日", "白",
    "木", "本", "林", "黒", "森",  # 濃い
]

SUBGROUP_HIRA_BASE = "gojuon"
SUBGROUP_HIRA_DAKU = "dakuten"
SUBGROUP_HIRA_HANDAKU = "handakuten"


def groups() -> dict[str, list[str]]:
    """群名 → 文字リスト。サブグループは返さない（atlas 側で扱う）。"""
    return {
        "density": list(DENSITY_CHARS),
        "line": list(LINE_CHARS),
        "hiragana": list(HIRAGANA_BASE) + list(HIRAGANA_DAKU) + list(HIRAGANA_HANDAKU),
        "katakana": list(KATAKANA_BASE) + list(KATAKANA_DAKU) + list(KATAKANA_HANDAKU),
        "kanji": list(KANJI_CHARS),
    }


def hiragana_subgroups() -> list[tuple[str, str]]:
    """(subgroup名, 文字リスト) のリスト。"""
    return [
        (SUBGROUP_HIRA_BASE, list(HIRAGANA_BASE)),
        (SUBGROUP_HIRA_DAKU, list(HIRAGANA_DAKU)),
        (SUBGROUP_HIRA_HANDAKU, list(HIRAGANA_HANDAKU)),
    ]


def katakana_subgroups() -> list[tuple[str, str]]:
    return [
        (SUBGROUP_HIRA_BASE, list(KATAKANA_BASE)),
        (SUBGROUP_HIRA_DAKU, list(KATAKANA_DAKU)),
        (SUBGROUP_HIRA_HANDAKU, list(KATAKANA_HANDAKU)),
    ]


# 方式 A のエッジ置換で使う「まっすぐな線」だけのサブセット
# （角・T 字・十字は向きが一意でないため候補から外す。T-5 の調整に相当）
STRAIGHT_LINE_CHARS = frozenset("―─━│┃═║╱╲／＼｜")


# 実験用の文字セット名 → 使用する群のリスト
CHARSET_PRESETS: dict[str, tuple[str, ...]] = {
    "density": ("density",),
    "line": ("line",),
    "symbols": ("density", "line"),
    "hiragana": ("density", "hiragana"),
    "kana": ("density", "hiragana", "katakana"),
    "all": ("density", "line", "hiragana", "katakana", "kanji"),
}


def preset_chars(preset: str) -> list[tuple[str, str, str | None]]:
    """プリセット名 → [(群名, 文字, サブグループ or None)] のリスト（id 順 = この順）。"""
    if preset not in CHARSET_PRESETS:
        raise KeyError(f"unknown charset preset: {preset}")
    out: list[tuple[str, str, str | None]] = []
    for g in CHARSET_PRESETS[preset]:
        if g == "hiragana":
            for sub, chars in hiragana_subgroups():
                out.extend((g, c, sub) for c in chars)
        elif g == "katakana":
            for sub, chars in katakana_subgroups():
                out.extend((g, c, sub) for c in chars)
        else:
            out.extend((g, c, None) for c in groups()[g])
    return out


if __name__ == "__main__":
    total = 0
    for name, chars in groups().items():
        print(f"{name:10s}: {len(chars):4d} chars")
        total += len(chars)
    print(f"{'total':10s}: {total:4d} chars")
