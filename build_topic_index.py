#!/usr/bin/env python3
"""
GPT Archive — Topic Indexer

Reads catalog.json and classifies conversations into topic categories
using a configurable weighted-scoring system.

Customize topics.json to define your own categories with strong/weak
signal keywords.

Usage: python3 build_topic_index.py
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

from archive_utils import load_config

SCRIPT_DIR = Path(__file__).resolve().parent


def load_topic_categories():
    """Load topic categories from topics.json config."""
    config = load_config("topics.json", default={})
    threshold = config.get("threshold", 3)
    categories = config.get("categories", {})
    return categories, threshold


def classify_conversation(entry, categories_spec, threshold=3):
    """Classify a conversation into topic categories using weighted scoring.

    Each category defines strong signals (3 points) and weak signals (1 point).
    A conversation must reach the threshold score to be classified into a
    category.
    """
    title = (entry.get("title") or "").lower()
    first_msg = (entry.get("first_user_message") or "").lower()
    combined = f"{title} {first_msg}"

    categories = []
    for cat_name, signals in categories_spec.items():
        score = 0
        for term in signals.get("strong", []):
            if term in combined:
                score += 3
        for term in signals.get("weak", []):
            if term in combined:
                score += 1
        if score >= threshold:
            categories.append(cat_name)

    if not categories:
        categories.append("Uncategorized")

    return categories


def build_topic_index(export_dir):
    """Build the topic index from catalog.json."""
    export_path = Path(export_dir)
    catalog_path = export_path / "catalog.json"

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    print(f"Loaded {len(catalog)} conversations from catalog")

    categories_spec, threshold = load_topic_categories()

    if not categories_spec:
        print("Warning: No topic categories defined in topics.json.")
        print("Create topics.json with your categories to enable classification.")
        return

    topic_map = defaultdict(list)

    for entry in catalog:
        categories = classify_conversation(entry, categories_spec, threshold)
        for cat in categories:
            topic_map[cat].append(entry)

    sorted_topics = sorted(topic_map.items(), key=lambda x: len(x[1]), reverse=True)

    # Build markdown output
    lines = []
    lines.append("# GPT Archive — Topic Index")
    lines.append(f"")
    lines.append(f"**Total conversations:** {len(catalog)}")

    dates = [e["date"] for e in catalog if e.get("date") and e["date"] != "unknown"]
    if dates:
        lines.append(f"**Date range:** {min(dates)} to {max(dates)}")
    lines.append(f"**Categories:** {len(sorted_topics)}")
    lines.append(f"")
    lines.append(f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} by GPT Archive*")
    lines.append(f"")

    # Table of contents
    lines.append("---")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    for topic, entries in sorted_topics:
        date_range = ""
        topic_dates = [e["date"] for e in entries if e.get("date") and e["date"] != "unknown"]
        if topic_dates:
            date_range = f" ({min(topic_dates)} \u2192 {max(topic_dates)})"
        lines.append(f"- **{topic}** \u2014 {len(entries)} conversations{date_range}")
    lines.append("")

    # Detailed sections
    for topic, entries in sorted_topics:
        lines.append("---")
        lines.append(f"")
        lines.append(f"## {topic}")
        lines.append(f"*{len(entries)} conversations*")
        lines.append(f"")

        entries_sorted = sorted(entries, key=lambda x: x.get("create_time") or 0, reverse=True)

        for e in entries_sorted:
            title = e.get("title") or "Untitled"
            date = e.get("date", "unknown")
            model = e.get("model", "")
            msg_count = e.get("message_count", 0)
            first_msg = e.get("first_user_message", "")

            preview = first_msg[:120].replace("\n", " ").strip()
            if len(first_msg) > 120:
                preview += "..."

            lines.append(f"### {title}")
            lines.append(f"**{date}** \u00b7 {msg_count} messages \u00b7 {model}")
            if preview:
                lines.append(f"> {preview}")
            lines.append(f"")

    output_path = export_path / "topic-index.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nTopic index written to: {output_path}")
    print(f"\nBreakdown:")
    for topic, entries in sorted_topics:
        print(f"  {topic}: {len(entries)}")

    uncat = sum(1 for e in catalog if classify_conversation(e, categories_spec, threshold) == ["Uncategorized"])
    print(f"\n  Uncategorized: {uncat} ({uncat/len(catalog)*100:.1f}%)")


if __name__ == "__main__":
    if Path("catalog.json").exists():
        build_topic_index(".")
    elif Path("ChatGPT Export/catalog.json").exists():
        build_topic_index("ChatGPT Export")
    else:
        print("Run from the directory containing catalog.json, or its parent.")
