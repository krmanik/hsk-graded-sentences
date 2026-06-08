import re, sqlite3, opencc
from pathlib import Path

t2s = opencc.OpenCC("t2s")
TRAIL_DIGS = re.compile(r"[0-9]+$")
PAREN_PAT  = re.compile(r"（([^）]*)）")
HSK_DIR = Path("New HSK (2025)")
HSK_FILES = [
    ("HSK_Level_1_words.txt", 1), ("HSK_Level_2_words.txt", 2),
    ("HSK_Level_3_words.txt", 3), ("HSK_Level_4_words.txt", 4),
    ("HSK_Level_5_words.txt", 5), ("HSK_Level_6_words.txt", 6),
    ("HSK_Level_7-9_words.txt", 7),
]

def expand(word):
    """没（有）→ [没, 没有]   差（一）点儿→ [差点儿, 差一点儿]"""
    m = PAREN_PAT.search(word)
    if not m:
        return [word]
    inner = m.group(1)
    without = PAREN_PAT.sub("", word)      # drop optional part
    with_   = PAREN_PAT.sub(inner, word)   # insert optional part
    return [without, with_]

con = sqlite3.connect("data/hsk_sentences.db")
all_sentences = [row[0] for row in con.execute("SELECT sentence FROM sentences")]

# build one big string for fast substring checking
big = "\n".join(all_sentences)

missing_by_level = {}
for fname, level in HSK_FILES:
    missing = []
    for line in open(HSK_DIR / fname, encoding="utf-8"):
        raw  = TRAIL_DIGS.sub("", line.strip())
        word = t2s.convert(raw)
        if not word:
            continue
        variants = expand(word)
        if not any(v in big for v in variants):
            missing.append(word)
    missing_by_level[level] = missing

total_missing = sum(len(v) for v in missing_by_level.values())
total_words   = 0
for fname, level in HSK_FILES:
    c = sum(1 for l in open(HSK_DIR / fname, encoding="utf-8") if l.strip())
    total_words += c
    n = len(missing_by_level[level])
    print(f"HSK{level}: {n} missing / {c} total  ({100*n/c:.1f}%)")
    for w in missing_by_level[level][:10]:
        print(f"    {w}")
    if len(missing_by_level[level]) > 10:
        print(f"    ... +{len(missing_by_level[level])-10} more")

print(f"\nTotal missing: {total_missing} / {total_words}")
