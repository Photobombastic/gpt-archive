#!/usr/bin/env python3
"""
GPT Archive — Search

Full-text search across ChatGPT conversation history.
Usage: python3 search.py "query" [options]
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from archive_utils import CATALOG_PATH, find_conversation_file

# ── ANSI escape codes ──────────────────────────────────────────────────────────

BOLD      = "\033[1m"
DIM       = "\033[2m"
RESET     = "\033[0m"
RED       = "\033[31m"
GREEN     = "\033[32m"
YELLOW    = "\033[33m"
CYAN      = "\033[36m"
WHITE     = "\033[37m"

MATCH_STYLE  = f"{BOLD}{YELLOW}"
TITLE_STYLE  = f"{BOLD}{WHITE}"
META_STYLE   = f"{DIM}"
HEADER_STYLE = f"{BOLD}{CYAN}"
COUNT_STYLE  = f"{BOLD}{GREEN}"
DIVIDER_CHAR = "\u2500"

# ── Helpers ────────────────────────────────────────────────────────────────────


def term_width():
    """Get terminal width, falling back to 90 if not a TTY."""
    try:
        return min(os.get_terminal_size().columns, 90)
    except (OSError, ValueError):
        return 90


def load_catalog():
    """Load catalog.json and return list of conversation metadata dicts."""
    if not CATALOG_PATH.exists():
        print(f"{RED}Error:{RESET} catalog.json not found at {CATALOG_PATH}")
        print(f"Run build_catalog.py first to generate it.")
        sys.exit(1)
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def highlight_match(text, pattern):
    """Replace matches in text with ANSI-highlighted versions."""
    def replacer(m):
        return f"{MATCH_STYLE}{m.group()}{RESET}"
    return pattern.sub(replacer, text)


def extract_snippets(text, pattern, max_snippets=3, context_chars=100):
    """Extract up to max_snippets context windows around matches."""
    matches = list(pattern.finditer(text))
    if not matches:
        return []

    snippets = []
    used_ranges = []

    for m in matches:
        if len(snippets) >= max_snippets:
            break

        start = max(0, m.start() - context_chars)
        end = min(len(text), m.end() + context_chars)

        # Skip if this range overlaps heavily with one already used
        overlaps = False
        for us, ue in used_ranges:
            if min(end, ue) - max(start, us) > context_chars:
                overlaps = True
                break
        if overlaps:
            continue

        used_ranges.append((start, end))

        snippet = text[start:end]
        # Collapse whitespace runs
        snippet = re.sub(r'\s+', ' ', snippet)

        # Trim to word boundaries at edges
        if start > 0:
            idx = snippet.find(' ')
            if idx != -1 and idx < 30:
                snippet = snippet[idx + 1:]
            snippet = "..." + snippet
        if end < len(text):
            idx = snippet.rfind(' ')
            if idx != -1 and idx > len(snippet) - 30:
                snippet = snippet[:idx]
            snippet = snippet + "..."

        snippet = highlight_match(snippet, pattern)
        snippets.append(snippet)

    return snippets


def filter_user_messages(text):
    """Extract only USER message blocks from a conversation file."""
    blocks = re.split(r'^## (USER|ASSISTANT|TOOL|SYSTEM)(?:\s*\([^)]*\))?\s*$', text, flags=re.MULTILINE)
    user_parts = []
    i = 1
    while i < len(blocks) - 1:
        role = blocks[i].strip()
        content = blocks[i + 1]
        if role == "USER":
            user_parts.append(content)
        i += 2
    return "\n".join(user_parts)


def format_date(date_str):
    """Format YYYY-MM-DD into a readable date."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.strftime('%b')} {dt.day}, {dt.strftime('%Y')}"
    except (ValueError, TypeError):
        return date_str or "unknown"


def print_header():
    """Print the search tool banner."""
    w = term_width()
    print()
    print(f"{HEADER_STYLE}{DIVIDER_CHAR * w}{RESET}")
    print(f"{HEADER_STYLE}  GPT Archive Search{RESET}")
    print(f"{HEADER_STYLE}{DIVIDER_CHAR * w}{RESET}")
    print()


def print_result(rank, entry, match_count, snippets, show_full=False, full_text=None):
    """Print a single search result."""
    w = term_width()
    model = entry.get("model", "unknown")
    msg_count = entry.get("message_count", "?")
    date_display = format_date(entry.get("date", ""))

    count_word = "match" if match_count == 1 else "matches"

    print(f"  {TITLE_STYLE}{rank}. {entry['title']}{RESET}")
    print(f"     {META_STYLE}{date_display}  \u00b7  {model}  \u00b7  {msg_count} messages  \u00b7  {RESET}{COUNT_STYLE}{match_count} {count_word}{RESET}")

    if show_full and full_text:
        print(f"     {META_STYLE}{DIVIDER_CHAR * (w - 5)}{RESET}")
        for line in full_text.split('\n'):
            print(f"     {line}")
        print(f"     {META_STYLE}{DIVIDER_CHAR * (w - 5)}{RESET}")
    elif snippets:
        for snippet in snippets:
            print(f"     {META_STYLE}\u2502{RESET} {snippet}")

    print()


# ── Main ───────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Search across ChatGPT conversation history.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  python3 search.py "python"
  python3 search.py "kubernetes" --after 2024-01-01 --model gpt-4
  python3 search.py "resume" -t
  python3 search.py "TODO|FIXME" -r --user-only
  python3 search.py "startup" --full -n 5
  python3 search.py "api" --export api_results.md""",
    )
    parser.add_argument("query", help="Search query (text or regex with -r)")
    parser.add_argument("-t", "--title-only", action="store_true",
                        help="Only search conversation titles (fast)")
    parser.add_argument("-u", "--user-only", action="store_true",
                        help="Only search user messages")
    parser.add_argument("--after", metavar="YYYY-MM-DD",
                        help="Only conversations after this date")
    parser.add_argument("--before", metavar="YYYY-MM-DD",
                        help="Only conversations before this date")
    parser.add_argument("--model", metavar="MODEL",
                        help="Filter by model name (partial match)")
    parser.add_argument("-n", "--limit", type=int, default=20,
                        help="Max results to show (default: 20)")
    parser.add_argument("-f", "--full", action="store_true",
                        help="Print full conversation text instead of snippets")
    parser.add_argument("-r", "--regex", action="store_true",
                        help="Treat query as a regular expression")
    parser.add_argument("--export", metavar="FILE",
                        help="Export full matching conversations to a single file")
    args = parser.parse_args()

    # Compile the search pattern
    try:
        if args.regex:
            pattern = re.compile(args.query, re.IGNORECASE)
        else:
            pattern = re.compile(re.escape(args.query), re.IGNORECASE)
    except re.error as e:
        print(f"{RED}Error:{RESET} Invalid regex: {e}")
        sys.exit(1)

    # ── Banner ─────────────────────────────────────────────────────────────

    print_header()

    flags_parts = []
    if args.title_only:   flags_parts.append("title-only")
    if args.user_only:    flags_parts.append("user-only")
    if args.regex:        flags_parts.append("regex")
    if args.after:        flags_parts.append(f"after {args.after}")
    if args.before:       flags_parts.append(f"before {args.before}")
    if args.model:        flags_parts.append(f"model={args.model}")
    if args.full:         flags_parts.append("full output")
    if args.export:       flags_parts.append(f"export → {args.export}")
    flags_str = f"  {META_STYLE}[{', '.join(flags_parts)}]{RESET}" if flags_parts else ""
    print(f"  Searching for: {MATCH_STYLE}{args.query}{RESET}{flags_str}")
    print()

    # ── Load catalog ───────────────────────────────────────────────────────

    catalog = load_catalog()
    total_conversations = len(catalog)

    # ── Phase 1: Metadata filters ──────────────────────────────────────────

    filtered = catalog

    if args.after:
        filtered = [e for e in filtered
                    if e.get("date", "") >= args.after and e.get("date", "") != "unknown"]

    if args.before:
        filtered = [e for e in filtered
                    if e.get("date", "") <= args.before and e.get("date", "") != "unknown"]

    if args.model:
        model_lower = args.model.lower()
        filtered = [e for e in filtered if model_lower in e.get("model", "").lower()]

    filtered_count = len(filtered)

    # ── Phase 2: Search ────────────────────────────────────────────────────

    results = []  # list of (entry, match_count, snippets, full_text|None)

    if args.title_only:
        # Fast path: only search title + first_user_message from catalog
        for entry in filtered:
            title = entry.get("title") or ""
            first_msg = entry.get("first_user_message") or ""
            search_blob = title + " " + first_msg
            matches = list(pattern.finditer(search_blob))
            if matches:
                highlighted = highlight_match(title, pattern)
                results.append((entry, len(matches), [highlighted], None))

        print(f"  {META_STYLE}Searched {filtered_count} titles.{RESET}")
        print()
    else:
        # Full-text search: read conversation files
        scanned = 0
        skipped = 0
        for entry in filtered:
            filepath = find_conversation_file(entry)
            if filepath is None or not filepath.exists():
                skipped += 1
                continue

            try:
                text = filepath.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                skipped += 1
                continue

            scanned += 1

            search_text = text
            if args.user_only:
                search_text = filter_user_messages(text)

            matches = list(pattern.finditer(search_text))
            if not matches:
                continue

            match_count = len(matches)

            if args.full:
                full_highlighted = highlight_match(search_text, pattern)
                results.append((entry, match_count, [], full_highlighted))
            else:
                snippets = extract_snippets(search_text, pattern,
                                            max_snippets=3, context_chars=100)
                results.append((entry, match_count, snippets, None))

        parts = [f"Scanned {scanned} files"]
        if skipped:
            parts.append(f"{skipped} not found")
        print(f"  {META_STYLE}{', '.join(parts)}.{RESET}")
        print()

    # ── Phase 3: Sort and display ──────────────────────────────────────────

    # Most matches first, then newest date first as tiebreaker.
    results.sort(key=lambda r: (-r[1], tuple(-ord(c) for c in r[0].get("date", ""))))

    total_matches = sum(r[1] for r in results)
    total_convos = len(results)

    # ── Export mode ─────────────────────────────────────────────────────
    if args.export and results:
        export_path = Path(args.export)
        export_entries = results[:args.limit]
        with open(export_path, "w", encoding="utf-8") as ef:
            ef.write(f"# GPT Archive Export: \"{args.query}\"\n")
            ef.write(f"# {len(export_entries)} conversations, {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            for i, (entry, mc, _, _) in enumerate(export_entries, 1):
                filepath = find_conversation_file(entry)
                if filepath is None or not filepath.exists():
                    continue
                try:
                    text = filepath.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                ef.write(f"{'=' * 80}\n")
                ef.write(f"## [{i}] {entry.get('title', 'Untitled')} "
                         f"({entry.get('date', '?')}, {mc} matches)\n")
                ef.write(f"{'=' * 80}\n\n")
                ef.write(text)
                ef.write(f"\n\n")
        print(f"  {COUNT_STYLE}Exported {len(export_entries)} conversations → {export_path}{RESET}")
        print()

    display = results[:args.limit]

    if not results:
        print(f"  {DIM}No matches found.{RESET}")
    else:
        for i, (entry, mc, snips, full) in enumerate(display, 1):
            print_result(i, entry, mc, snips, show_full=args.full, full_text=full)

        if total_convos > args.limit:
            extra = total_convos - args.limit
            print(f"  {META_STYLE}... and {extra} more result{'s' if extra != 1 else ''} (use -n to show more){RESET}")
            print()

    # ── Summary line ───────────────────────────────────────────────────────

    w = term_width()
    match_word = "match" if total_matches == 1 else "matches"
    convo_word = "conversation" if total_convos == 1 else "conversations"

    print(f"  {META_STYLE}{DIVIDER_CHAR * (w - 2)}{RESET}")

    filter_note = ""
    if filtered_count < total_conversations:
        filter_note = f" ({filtered_count} of {total_conversations} passed filters)"

    print(f"  {COUNT_STYLE}{total_matches} {match_word}{RESET}"
          f" across {COUNT_STYLE}{total_convos} {convo_word}{RESET}"
          f"{filter_note}")
    print()


if __name__ == "__main__":
    main()
