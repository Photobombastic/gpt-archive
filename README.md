# GPT Archive

Turn your ChatGPT export into a searchable, indexed, local archive.

GPT Archive is a zero-dependency Python pipeline that parses OpenAI's data export format, converts conversations to readable Markdown, extracts entities, classifies topics, and gives you a fast full-text search CLI across your entire conversation history.

## Quick Start

1. **Export your data** from ChatGPT: Settings > Data Controls > Export Data
2. **Unzip** the export and place the `conversations-*.json` files in an `extracted/` directory
3. **Run the pipeline:**
   ```bash
   python3 build_catalog.py        # Parse conversations into catalog + markdown
   python3 build_entities.py       # (optional) Extract companies, people, domains
   python3 build_topic_index.py    # (optional) Classify into topic categories
   ```
4. **Search your archive:**
   ```bash
   python3 search.py "kubernetes"
   ```

## Requirements

- Python 3.8+
- Zero external dependencies (stdlib only)

## Pipeline

### Step 1: Build Catalog (`build_catalog.py`)

Parses OpenAI's nested JSON export format (which stores messages as a DAG) and produces:
- **`catalog.json`** — structured metadata index with title, date, model, message counts, and first user message for each conversation
- **`conversations/`** — individual Markdown files (one per conversation), named `YYYYMMDD_Title.md`

```bash
python3 build_catalog.py
```

### Step 2: Extract Entities (`build_entities.py`) — optional

Enriches `catalog.json` with entity data extracted from conversation text:
- **Companies** — matched against your seeded list in `entities.json`, plus auto-discovered domains
- **People** — matched against your seeded list in `entities.json`
- **Work type** — auto-classified as consulting-engagement, resume-prep, interview-prep, investment-memo, event, or general

```bash
python3 build_entities.py
```

### Step 3: Build Topic Index (`build_topic_index.py`) — optional

Classifies conversations into topic categories defined in `topics.json` using a weighted scoring system. Outputs `topic-index.md` — a browsable, categorized map of your archive.

```bash
python3 build_topic_index.py
```

### Search (`search.py`)

Full-text CLI search with ANSI-highlighted results, snippets, and multiple filter modes.

```bash
# Basic search
python3 search.py "python"

# Search with filters
python3 search.py "api" --after 2024-01-01 --model gpt-4

# Title-only search (fast)
python3 search.py "resume" -t

# Regex search, user messages only
python3 search.py "TODO|FIXME" -r --user-only

# Full conversation output
python3 search.py "startup" --full -n 5

# Filter by entity and export results
python3 search.py "market" --company stripe --export stripe_market.md

# Filter by work type
python3 search.py "resume" --work-type resume-prep
```

**All flags:**

| Flag | Description |
|------|-------------|
| `-t`, `--title-only` | Only search titles and first messages (fast) |
| `-u`, `--user-only` | Only search user messages |
| `--after YYYY-MM-DD` | Filter by date range |
| `--before YYYY-MM-DD` | Filter by date range |
| `--model MODEL` | Filter by model name (partial match) |
| `-n`, `--limit N` | Max results to show (default: 20) |
| `-f`, `--full` | Print full conversation text |
| `-r`, `--regex` | Treat query as regex |
| `--export FILE` | Export full matching conversations to file |
| `--company NAME` | Filter by company (from entities) |
| `--work-type TYPE` | Filter by work type (from entities) |

## Customization

### Entities (`entities.json`)

Seed your own companies and people for higher-confidence entity extraction. Keys are lowercase match patterns, values are canonical display names:

```json
{
  "companies": {
    "acme corp": "Acme Corporation",
    "openai": "OpenAI"
  },
  "people": {
    "jane doe": "Jane Doe (CTO)"
  }
}
```

The entity extractor also auto-discovers companies via capitalized phrase detection and domain extraction, so the seeded list is a starting point, not a ceiling.

### Topics (`topics.json`)

Define your own topic categories with strong and weak signal keywords:

```json
{
  "threshold": 3,
  "categories": {
    "My Category": {
      "strong": ["exact phrase match worth 3 points"],
      "weak": ["broad term worth 1 point"]
    }
  }
}
```

**How scoring works:** Each strong signal match adds 3 points, each weak signal adds 1 point. A conversation must reach the threshold score to be classified into a category. This prevents false positives from generic keywords.

The default `topics.json` ships with 10 generic categories. Customize them to match your interests.

## Directory Structure After Running

```
your-archive/
├── extracted/                  # Your raw ChatGPT export files
│   └── conversations-*.json
├── conversations/              # Generated markdown files
│   ├── 20231220_Some_Title.md
│   └── ...
├── catalog.json                # Generated metadata index
├── topic-index.md              # Generated topic classification
├── build_catalog.py
├── build_entities.py
├── build_topic_index.py
├── search.py
├── archive_utils.py
├── entities.json               # Your entity config
└── topics.json                 # Your topic config
```

## License

MIT
