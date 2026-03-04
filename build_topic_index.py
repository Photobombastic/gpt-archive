#!/usr/bin/env python3
"""
GPT Archive — Topic Indexer

Reads catalog.json and classifies conversations into topic categories
using a configurable weighted-scoring system. Reads conversation files
for deeper signal when title + first message aren't enough.

Customize topics.json to define your own categories with strong/weak
signal keywords.

Usage: python3 build_topic_index.py
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime

from archive_utils import load_config, find_conversation_file


SCRIPT_DIR = Path(__file__).resolve().parent


def _extract_user_text(full_text):
    """Extract only USER message blocks from a conversation markdown file."""
    blocks = re.split(
        r'^## (USER|ASSISTANT|TOOL|SYSTEM)(?:\s*\([^)]*\))?\s*$',
        full_text, flags=re.MULTILINE,
    )
    parts = []
    i = 1
    while i < len(blocks) - 1:
        if blocks[i].strip() == "USER":
            parts.append(blocks[i + 1])
        i += 2
    return "\n".join(parts)


# Intent patterns: structural patterns in the first user message that
# indicate what KIND of task the conversation is, regardless of topic.
# Each pattern maps to a category. Checked as a final fallback when
# keyword matching fails.
INTENT_PATTERNS = [
    # Questions / explanations → Learning
    (r"^(what is|what are|what was|what does|what do|who is|who are|who was)\b", "Learning & Education"),
    (r"^(how does|how do|how is|how are|how did|how can|how would)\b", "Learning & Education"),
    (r"^(why does|why do|why is|why are|why did|why would)\b", "Learning & Education"),
    (r"^(explain|tell me about|describe|define|what('s| is) the difference)\b", "Learning & Education"),
    (r"^(is it true|is there|are there|does it|do they|can you explain)\b", "Learning & Education"),

    # Image/content generation → Creative
    (r"(generate|create|make|draw|design|imagine)\s+(a |an |me |some )?(image|photo|picture|illustration|logo|caricature|portrait)", "Creative & Brainstorming"),
    (r"(generate|create|make)\s+(a |an |me |some )?(photorealistic|abstract|cartoon|realistic)", "Creative & Brainstorming"),

    # Fixing / troubleshooting → Practical
    (r"(help me (fix|repair|troubleshoot|reset|set up|install|configure))\b", "Practical & Everyday"),
    (r"^(fix|repair|troubleshoot)\b", "Practical & Everyday"),
    (r"(not working|doesn't work|won't work|broken|stuck)\b", "Practical & Everyday"),

    # Translation / language → Language
    (r"(translate|traduci|traduce|how do you say|como se dice|cómo se dice)\b", "Language & Translation"),
    (r'(meaning of|what does .{1,30} mean|qué significa|qué quiere decir)\b', "Language & Translation"),

    # Advice / decisions → Relationships (when about people)
    (r"(should i|what should i|what would you|help me decide|advice on)\b", "Learning & Education"),

    # Math / calculation → Math
    (r"^(solve|calculate|compute|isolate|simplify|convert)\b", "Math & Science"),
    (r"^(how much|how many) (does|do|is|are|would|will)\b", "Math & Science"),
]


def load_topic_categories():
    """Load topic categories from topics.json config."""
    config = load_config("topics.json", default={})
    threshold = config.get("threshold", 3)
    categories = config.get("categories", {})
    return categories, threshold


def classify_conversation(entry, categories_spec, threshold=3, full_text=None):
    """Classify a conversation into topic categories using weighted scoring.

    Each category defines strong signals (3 points) and weak signals (1 point).
    A conversation must reach the threshold score to be classified into a
    category.

    First checks title + first message. If nothing matches and full_text
    is available, scans the full conversation for signals (with reduced
    weight to avoid false positives from passing mentions).
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

    # If nothing matched from title + first message, try user messages
    # in the full text. Only user messages are scanned to avoid false
    # positives from assistant responses (which contain AI/code terms
    # in virtually every conversation).
    if not categories and full_text:
        user_text = _extract_user_text(full_text)
        text_lower = user_text[:8000].lower()
        for cat_name, signals in categories_spec.items():
            score = 0
            strong_hits = sum(1 for term in signals.get("strong", []) if term in text_lower)
            weak_hits = sum(1 for term in signals.get("weak", []) if term in text_lower)
            score = strong_hits * 3 + weak_hits
            if score >= threshold:
                categories.append(cat_name)

    # Third pass: intent detection from first user message structure.
    # Catches "what is X", "generate an image of X", "fix my X" etc.
    # regardless of what X is.
    if not categories and first_msg:
        for pattern, cat in INTENT_PATTERNS:
            if re.search(pattern, first_msg, re.IGNORECASE):
                if cat not in categories:
                    categories.append(cat)
                break  # one intent match is enough

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

    for i, entry in enumerate(catalog):
        # Try title + first message first (fast path)
        categories = classify_conversation(entry, categories_spec, threshold)

        # If uncategorized, try reading the full conversation file
        if categories == ["Uncategorized"]:
            filepath = find_conversation_file(entry)
            if filepath and filepath.exists():
                try:
                    full_text = filepath.read_text(encoding="utf-8")
                    categories = classify_conversation(
                        entry, categories_spec, threshold, full_text=full_text
                    )
                except (OSError, UnicodeDecodeError):
                    pass

        for cat in categories:
            topic_map[cat].append(entry)

        if (i + 1) % 200 == 0:
            print(f"  Processed {i + 1}/{len(catalog)}...")

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

    uncat = len(topic_map.get("Uncategorized", []))
    if catalog:
        print(f"\n  Uncategorized: {uncat} ({uncat / len(catalog) * 100:.1f}%)")


if __name__ == "__main__":
    if Path("catalog.json").exists():
        build_topic_index(".")
    elif Path("ChatGPT Export/catalog.json").exists():
        build_topic_index("ChatGPT Export")
    else:
        print("Run from the directory containing catalog.json, or its parent.")
