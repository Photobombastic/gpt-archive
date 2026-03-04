#!/usr/bin/env python3
"""
GPT Archive — Shared Utilities

Common functions used across the archive pipeline scripts.
"""

import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CATALOG_PATH = SCRIPT_DIR / "catalog.json"
CONVERSATIONS_DIR = SCRIPT_DIR / "conversations"


def load_config(filename, default=None):
    """Load a JSON config file from the script directory.

    Returns the parsed dict, or *default* (empty dict if not specified)
    when the file is missing.
    """
    config_path = SCRIPT_DIR / filename
    if not config_path.exists():
        if default is not None:
            return default
        print(f"Note: {filename} not found — using empty defaults.")
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_title(title):
    """Strip special chars to match filesystem-sanitized filenames."""
    return re.sub(r"['\"\?\!/\\\.\u00b7:;]", "", title)


def build_file_index(conversations_dir=None):
    """Build a lookup from (date_prefix, normalized_title) -> filepath.

    Returns (index_dict, date_buckets_dict).
    """
    cdir = conversations_dir or CONVERSATIONS_DIR
    index = {}
    date_buckets = {}
    if not cdir.exists():
        return index, date_buckets
    for p in cdir.iterdir():
        if p.suffix == ".md" and len(p.name) > 9 and p.name[8] == "_":
            date8 = p.name[:8]
            raw_title = p.stem[9:]
            norm = normalize_title(raw_title)
            index[(date8, norm)] = p
            index[(date8, raw_title)] = p
            date_buckets.setdefault(date8, []).append(p)
    return index, date_buckets


# Module-level cache, populated on first use
_FILE_INDEX = None
_DATE_BUCKETS = None


def find_conversation_file(entry, conversations_dir=None):
    """Resolve the markdown file path for a catalog entry."""
    global _FILE_INDEX, _DATE_BUCKETS
    if _FILE_INDEX is None:
        _FILE_INDEX, _DATE_BUCKETS = build_file_index(conversations_dir)

    date_str = (entry.get("date") or "").replace("-", "")[:8]
    title = entry.get("title") or ""

    result = _FILE_INDEX.get((date_str, title))
    if result:
        return result

    norm = normalize_title(title)
    result = _FILE_INDEX.get((date_str, norm))
    if result:
        return result

    bucket = _DATE_BUCKETS.get(date_str, [])
    if len(bucket) == 1:
        return bucket[0]

    return None
