# GPT Archive

Turn your ChatGPT export into readable Markdown files you can search, browse, and feed to an LLM.

OpenAI's data export gives you a JSON file where conversations are stored as nested DAGs — not something you can read or search. GPT Archive parses that into individual Markdown files (one per conversation) and a metadata catalog, so you can actually use your history.

## Quick Start

1. **Export your data** from ChatGPT: Settings > Data Controls > Export Data
2. **Unzip** the export and place the `conversations-*.json` files in an `extracted/` directory
3. **Run the parser:**
   ```bash
   python3 build_catalog.py
   ```
4. **Search your archive:**
   ```bash
   python3 search.py "kubernetes"
   ```
5. **Point an LLM at the results.** The real power is that `conversations/` now contains clean Markdown files you can drop into Claude, ChatGPT, or any LLM for deeper analysis — "find every conversation where I discussed X", "summarize my coding questions from 2024", etc.

## Requirements

- Python 3.8+
- Zero external dependencies (stdlib only)

## What It Does

### `build_catalog.py`

Parses OpenAI's nested JSON export format and produces:
- **`catalog.json`** — metadata index (title, date, model, message counts, first user message per conversation)
- **`conversations/`** — individual Markdown files named `YYYYMMDD_Title.md`

```bash
python3 build_catalog.py
```

### `search.py`

Full-text CLI search with highlighted results and snippets.

```bash
# Basic search
python3 search.py "python"

# Date and model filters
python3 search.py "api" --after 2024-01-01 --model gpt-4

# Title-only search (fast, no file I/O)
python3 search.py "resume" -t

# Regex, user messages only
python3 search.py "TODO|FIXME" -r --user-only

# Full conversation output
python3 search.py "startup" --full -n 5

# Export matches to a file
python3 search.py "api" --export api_results.md
```

| Flag | Description |
|------|-------------|
| `-t`, `--title-only` | Search titles and first messages only (fast) |
| `-u`, `--user-only` | Search user messages only |
| `--after YYYY-MM-DD` | Conversations after this date |
| `--before YYYY-MM-DD` | Conversations before this date |
| `--model MODEL` | Filter by model (partial match) |
| `-n`, `--limit N` | Max results (default: 20) |
| `-f`, `--full` | Print full conversation text |
| `-r`, `--regex` | Treat query as regex |
| `--export FILE` | Export matching conversations to file |

## Using With an LLM

Once you've run `build_catalog.py`, the `conversations/` directory contains clean Markdown files. You can:

- Drop individual files into Claude or ChatGPT for analysis
- Use `search.py --export` to bundle relevant conversations into a single file, then feed that to an LLM
- Point Claude Code or Cursor at the whole `conversations/` directory and ask questions across your history

The search tool is useful for narrowing down which conversations to look at. The LLM is better at understanding what's in them.

## Directory Structure

```
your-archive/
├── extracted/                  # Your raw ChatGPT export files
│   └── conversations-*.json
├── conversations/              # Generated — one markdown file per conversation
│   ├── 20231220_Some_Title.md
│   └── ...
├── catalog.json                # Generated — metadata index
├── build_catalog.py
├── search.py
└── archive_utils.py
```

## License

MIT
