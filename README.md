# HSK Graded Sentences

Ranks Mandarin sentences from easiest → hardest.  
Source: [Tatoeba](https://tatoeba.org) Chinese corpus.
Output: SQLite DB ready to query.

## Pipeline

```
cmn_sentences.tsv  →  clean.ipynb  →  cmn_sentences_clean.tsv
                                              ↓
                                         main.ipynb
                                              ↓
                              cmn_sentences_graded.tsv  +  hsk_word_coverage.tsv
                                              ↓
                                         tsv_to_db.py
                                              ↓
                                         hsk_sentences.db
```

### 1. `clean.ipynb` — profanity filter

- Converts all text to **Simplified Chinese** (opencc `t2s`)
- Loads profanity lists (see `profanity-list/`), then **purges**:
  - single-char terms (多/忙/干 etc. = false positives)
  - any term that is an HSK vocabulary word
- **Token-based matching** via jieba — drops a sentence only if a whole segmented token is profane (not substring)

### 2. `main.ipynb` — grading pipeline

**Cleaning** (in-notebook):
- Drop sentences containing Latin letters (English contamination)
- Length band: 2–30 Han characters
- Deduplicate

**Segmentation**: jieba seeded with all HSK words + top 100k frequency words

**Per-sentence features**:

| feature | meaning |
|---|---|
| `max_hsk` | highest HSK level among all tokens (8 = beyond-HSK) |
| `mean_hsk` | average HSK level |
| `hsk_coverage` | fraction of tokens within HSK 1–7 |
| `frac_oov` | fraction of tokens not in any HSK list |
| `mean_log_freq` | mean log₁₀(frequency rank) across tokens |
| `n_chars` | Han character count |

**Hybrid difficulty score** (each feature min-max normalised, 0–1):

```
difficulty = 0.45 × max_hsk  +  0.25 × mean_log_freq  +  0.15 × n_chars  +  0.15 × frac_oov
```

Sentences sorted easy → hard. Grade band (`max_hsk`) kept as a separate column for level filtering.

**Pinyin** added via `pypinyin`.

**Output**: `data/cmn_sentences_graded.tsv` — sentences with columns:
`rank, id, sentence, pinyin, n_chars, n_words, max_hsk, mean_hsk, hsk_coverage, rarest_rank, mean_log_freq, difficulty`

Also writes `data/hsk_word_coverage.tsv` — every HSK word with its sentence count.

### 3. `tsv_to_db.py` — SQLite export

```
python tsv_to_db.py
```

Produces `data/hsk_sentences.db` (~11 MB) with:

**`sentences`** table:

| column | type | notes |
|---|---|---|
| `rank` | INTEGER PK | 1 = easiest |
| `sentence` | TEXT | Simplified Chinese |
| `tokens` | TEXT | space-separated jieba tokens (powers FTS5) |
| `n_chars` | INTEGER | Han character count |
| `max_hsk` | INTEGER | 1–7, or 8 = beyond-HSK |
| `difficulty` | REAL | 0–1 composite score |

**`sentences_fts`** virtual table (FTS5 over `tokens`):
- unicode61 tokenizer
- content table — no data duplication

**Indexes**: composite `(max_hsk, difficulty)` for fast level-filtered pagination.

#### Example queries

```sql
-- HSK 1 sentences, easiest first
SELECT * FROM sentences WHERE max_hsk = 1 ORDER BY difficulty LIMIT 20;

-- Up to HSK 3, paginated
SELECT * FROM sentences WHERE max_hsk <= 3 ORDER BY difficulty LIMIT 20 OFFSET 40;

-- All sentences containing 比如, up to HSK 3
SELECT s.* FROM sentences_fts f
JOIN sentences s ON s.rank = f.rowid
WHERE f.sentences_fts MATCH '比如' AND s.max_hsk <= 3
ORDER BY s.difficulty;
```

## Requirements

```
opencc
jieba
pypinyin
```

## Licenses
- Tatoeba: CC BY 2.0 FR, attribution required
- BCC frequency list: no explicit license, free/academic use
- SUBTLEX-CH: CC BY-SA 4.0
- Profanity lists: various open-source (links kept in directory)
