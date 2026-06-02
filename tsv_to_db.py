#!/usr/bin/env python3
"""Convert cmn_sentences_graded.tsv to SQLite.

Schema
------
sentences      : rank, sentence, tokens, n_chars, max_hsk, difficulty
sentences_fts  : FTS5 over tokens column — fast word search
                 e.g.  SELECT * FROM sentences_fts WHERE sentences_fts MATCH '比如'

Pinyin omitted; generate at query time with pypinyin if needed.
"""
import csv
import re
import sqlite3
from pathlib import Path

import jieba
import opencc

DATA          = Path("data")
TSV_SENTENCES = DATA / "cmn_sentences_graded.tsv"
HSK_DIR       = Path("New HSK (2025)")
DB_PATH       = DATA / "hsk_sentences.db"

HAN        = re.compile(r"[一-鿿]")
TRAIL_DIGS = re.compile(r"[0-9]+$")
t2s        = opencc.OpenCC("t2s")

# seed jieba with HSK words so multi-char vocab segments as one token
HSK_FILES = [
    "HSK_Level_1_words.txt", "HSK_Level_2_words.txt", "HSK_Level_3_words.txt",
    "HSK_Level_4_words.txt", "HSK_Level_5_words.txt", "HSK_Level_6_words.txt",
    "HSK_Level_7-9_words.txt",
]
for name in HSK_FILES:
    for line in open(HSK_DIR / name, encoding="utf-8"):
        w = t2s.convert(TRAIL_DIGS.sub("", line.strip()))
        if len(w) >= 2:
            jieba.add_word(w)

def tokenise(text):
    return " ".join(w for w in jieba.lcut(text) if HAN.search(w))

# ── build DB ──────────────────────────────────────────────────────────────
con = sqlite3.connect(DB_PATH)
con.execute("PRAGMA journal_mode=WAL")
con.execute("PRAGMA synchronous=NORMAL")
con.execute("PRAGMA page_size=8192")   # better packing for text blobs

con.executescript("""
DROP TABLE IF EXISTS sentences_fts;
DROP TABLE IF EXISTS sentences;
DROP TABLE IF EXISTS hsk_words;
CREATE TABLE sentences (
    rank       INTEGER PRIMARY KEY,
    sentence   TEXT    NOT NULL,
    tokens     TEXT    NOT NULL,
    n_chars    INTEGER,
    max_hsk    INTEGER,
    difficulty REAL
);
""")

rows = []
with open(TSV_SENTENCES, encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        rows.append((
            int(r["rank"]),
            r["sentence"],
            tokenise(r["sentence"]),
            int(r["n_chars"]),
            int(r["max_hsk"]),
            float(r["difficulty"]),
        ))

con.executemany("INSERT INTO sentences VALUES (?,?,?,?,?,?)", rows)
print(f"sentences: {len(rows):,} rows inserted")

# FTS5 content table (no data duplication — reads from sentences.tokens)
con.executescript("""
CREATE VIRTUAL TABLE sentences_fts USING fts5(
    tokens,
    content='sentences',
    content_rowid='rank',
    tokenize='unicode61'
);
INSERT INTO sentences_fts(sentences_fts) VALUES('rebuild');
""")
print("FTS5 index built")

con.executescript("""
CREATE INDEX IF NOT EXISTS idx_level_diff ON sentences(max_hsk, difficulty);
""")

con.commit()
con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
con.execute("VACUUM")
con.close()

print(f"saved → {DB_PATH}  ({DB_PATH.stat().st_size/1e6:.1f} MB)")

# ── sanity ────────────────────────────────────────────────────────────────
con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row

print("\n-- easiest 3 --")
for r in con.execute("SELECT rank, sentence, max_hsk, difficulty FROM sentences ORDER BY rank LIMIT 3"):
    print(f"  #{r['rank']} hsk{r['max_hsk']} d={r['difficulty']:.3f}  {r['sentence']}")

print("\n-- word search: 比如, level ≤ 3 --")
for r in con.execute("""
    SELECT s.rank, s.sentence, s.max_hsk
    FROM sentences_fts f
    JOIN sentences s ON s.rank = f.rowid
    WHERE f.sentences_fts MATCH '比如' AND s.max_hsk <= 3
    ORDER BY s.difficulty LIMIT 3
"""):
    print(f"  hsk{r['max_hsk']}  {r['sentence']}")

print("\n-- word search: 电影, up to level 5 --")
for r in con.execute("""
    SELECT s.rank, s.sentence, s.max_hsk
    FROM sentences_fts f
    JOIN sentences s ON s.rank = f.rowid
    WHERE f.sentences_fts MATCH '电影' AND s.max_hsk <= 5
    ORDER BY s.difficulty LIMIT 3
"""):
    print(f"  hsk{r['max_hsk']}  {r['sentence']}")

print("\n-- band counts --")
for r in con.execute("SELECT max_hsk, count(*) n FROM sentences GROUP BY max_hsk ORDER BY max_hsk"):
    print(f"  hsk{r['max_hsk']}: {r['n']:,}")

con.close()
