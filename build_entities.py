#!/usr/bin/env python3
"""
GPT Archive — Entity Extractor

Extracts company names, people, and key terms from conversation files.
Enriches catalog.json with an "entities" field per conversation.

Customize entities.json to seed your own companies and people for
higher-confidence matching.

Usage: python3 build_entities.py
"""

import json
import re
from pathlib import Path
from collections import Counter

from archive_utils import (
    CATALOG_PATH, load_config, find_conversation_file,
)

# ── Load entity config ────────────────────────────────────────────────────────

_entities_config = load_config("entities.json", default={})
KNOWN_COMPANIES = _entities_config.get("companies", {})
KNOWN_PEOPLE = _entities_config.get("people", {})

# ── Extraction heuristics ─────────────────────────────────────────────────────


def extract_user_text(full_text):
    """Extract only USER message blocks from a conversation file."""
    blocks = re.split(r'^## (USER|ASSISTANT|TOOL[^\n]*)\s*$', full_text, flags=re.MULTILINE)
    user_parts = []
    i = 1
    while i < len(blocks) - 1:
        role = blocks[i].strip()
        content = blocks[i + 1]
        if role == "USER":
            user_parts.append(content)
        i += 2
    return "\n".join(user_parts)


def extract_known_entities(text):
    """Find known companies and people in text."""
    text_lower = text.lower()
    companies = set()
    people = set()

    for pattern, canonical in KNOWN_COMPANIES.items():
        if pattern in text_lower:
            companies.add(canonical)

    for pattern, canonical in KNOWN_PEOPLE.items():
        if pattern in text_lower:
            people.add(canonical)

    return sorted(companies), sorted(people)


def extract_capitalized_phrases(text, min_count=2):
    """Find frequently-occurring capitalized multi-word phrases.

    These are candidate company/product/org names not in the known list.
    Returns phrases that appear at least min_count times.
    """
    pattern = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b')
    matches = pattern.findall(text)

    stopwords = {
        "The", "This", "That", "What", "When", "Where", "Which", "How",
        "Here", "There", "About", "After", "Before", "Would", "Could",
        "Should", "Does", "User", "Assistant", "January", "February",
        "March", "April", "May", "June", "July", "August", "September",
        "October", "November", "December", "Monday", "Tuesday",
        "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
        "New York", "San Francisco", "Los Angeles", "North America",
        "United States", "Executive Summary", "Key Features",
        "Let Me", "Can You", "I Am", "I Have", "Thank You",
        "Please Note", "For Example", "In Addition",
    }

    counter = Counter()
    for phrase in matches:
        first_word = phrase.split()[0]
        if first_word in {"The", "This", "That", "What", "When", "Where",
                         "Which", "How", "Here", "There", "About", "After",
                         "Before", "Would", "Could", "Should", "Does", "Let",
                         "Can", "Please", "For", "In", "At", "On", "I"}:
            continue
        if phrase in stopwords:
            continue
        counter[phrase] += 1

    return [phrase for phrase, count in counter.most_common(20)
            if count >= min_count]


def extract_domains(text):
    """Extract domain names mentioned in text (potential company refs)."""
    pattern = re.compile(r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+)\.(com|io|ai|co|org|dev|app|xyz|tech)')
    matches = pattern.findall(text)
    skip = {"github", "google", "linkedin", "twitter", "youtube", "reddit",
            "medium", "substack", "notion", "slack", "gmail", "outlook",
            "crunchbase", "pitchbook", "wikipedia", "arxiv", "stackoverflow",
            "amazonaws", "cloudfront", "vercel", "netlify", "herokuapp",
            "openai", "anthropic", "microsoft"}
    domains = set()
    for name, tld in matches:
        if name.lower() not in skip and len(name) > 2:
            domains.add(f"{name}.{tld}")
    return sorted(domains)


def classify_work_type(entry, text):
    """Classify the conversation's work context.

    Categories: consulting-engagement, resume-prep, interview-prep,
    investment-memo, event, general.
    """
    title = (entry.get("title") or "").lower()
    first_msg = (entry.get("first_user_message") or "").lower()
    combined = f"{title} {first_msg}"
    text_lower = text.lower()

    user_text = extract_user_text(text)

    types = []

    consulting_strong = ["data room", "market sizing", "canvas", "investment memo",
                        "pitch deck", "competitive positioning", "go-to-market",
                        "tam/sam/som", "bottoms-up", "ic memo", "due diligence"]
    consulting_weak = ["client", "engagement", "deliverable", "founder",
                      "fundrais", "valuation", "investor"]
    score = sum(3 for s in consulting_strong if s in text_lower[:2000])
    score += sum(1 for s in consulting_weak if s in combined)
    if score >= 3:
        types.append("consulting-engagement")

    resume_signals = ["resume", "cover letter", "job description", "interview prep",
                     "application", "hiring manager"]
    if any(s in combined for s in resume_signals):
        types.append("resume-prep")

    interview_signals = ["interview", "par story", "star story", "tell me about",
                        "behavioral", "recruiter call"]
    if any(s in combined for s in interview_signals):
        types.append("interview-prep")

    invest_signals = ["spv", "investment memo", "ic memo", "investment committee"]
    if any(s in text_lower[:1000] for s in invest_signals):
        types.append("investment-memo")

    event_signals = ["event", "transcript", "takeaways", "use of funds",
                    "webinar", "workshop"]
    if any(s in combined for s in event_signals):
        types.append("event")

    if not types:
        types.append("general")

    return types


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    if not CATALOG_PATH.exists():
        print("Error: catalog.json not found. Run build_catalog.py first.")
        return

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    print(f"Loaded {len(catalog)} conversations from catalog")

    enriched = 0
    skipped = 0
    all_companies = Counter()
    all_people = Counter()
    all_work_types = Counter()

    for i, entry in enumerate(catalog):
        filepath = find_conversation_file(entry)
        if filepath is None or not filepath.exists():
            skipped += 1
            entry["entities"] = {
                "companies": [],
                "people": [],
                "domains": [],
                "work_type": ["general"],
            }
            continue

        try:
            text = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped += 1
            entry["entities"] = {
                "companies": [],
                "people": [],
                "domains": [],
                "work_type": ["general"],
            }
            continue

        companies, people = extract_known_entities(text)
        domains = extract_domains(text)
        work_type = classify_work_type(entry, text)

        entry["entities"] = {
            "companies": companies,
            "people": people,
            "domains": domains,
            "work_type": work_type,
        }

        for c in companies:
            all_companies[c] += 1
        for p in people:
            all_people[p] += 1
        for wt in work_type:
            all_work_types[wt] += 1

        enriched += 1

        if (i + 1) % 200 == 0:
            print(f"  Processed {i + 1}/{len(catalog)}...")

    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    print(f"\nDone! Enriched {enriched} conversations ({skipped} skipped)")
    print(f"\nTop companies mentioned:")
    for company, count in all_companies.most_common(25):
        print(f"  {company}: {count}")

    print(f"\nWork types:")
    for wt, count in all_work_types.most_common():
        print(f"  {wt}: {count}")

    if all_people:
        print(f"\nPeople found:")
        for person, count in all_people.most_common(15):
            print(f"  {person}: {count}")


if __name__ == "__main__":
    main()
