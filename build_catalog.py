#!/usr/bin/env python3
"""
GPT Archive — Catalog Builder

Parses OpenAI export conversations-*.json files and produces:
1. catalog.json — structured index of all conversations
2. conversations/ — individual markdown files per conversation

Usage: python3 build_catalog.py
Place your exported conversations-*.json files in an extracted/ directory,
then run this script from the parent directory.
"""

import json
import glob
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def timestamp_to_date(ts):
    """Convert Unix timestamp to readable date string."""
    if not ts:
        return "unknown"
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return "unknown"


def timestamp_to_datetime(ts):
    """Convert Unix timestamp to full datetime string."""
    if not ts:
        return "unknown"
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return "unknown"


def extract_text_from_parts(parts):
    """Extract text content from message parts, skipping images/files."""
    texts = []
    for part in parts:
        if isinstance(part, str):
            texts.append(part)
        elif isinstance(part, dict):
            # Skip image/file references
            if part.get("content_type") in ("image_asset_pointer",):
                texts.append("[image]")
            elif "text" in part:
                texts.append(part["text"])
    return "\n".join(texts)


def linearize_conversation(mapping, current_node):
    """
    Walk the conversation tree from root to current_node,
    producing a linear list of messages in order.
    
    The mapping is a tree — we need to find the path from root to current_node.
    Strategy: walk backwards from current_node to root, then reverse.
    """
    if not mapping or not current_node:
        return []
    
    # Build path from current_node back to root
    path = []
    node_id = current_node
    visited = set()
    
    while node_id and node_id in mapping and node_id not in visited:
        visited.add(node_id)
        node = mapping[node_id]
        if node.get("message"):
            path.append(node["message"])
        node_id = node.get("parent")
    
    path.reverse()
    return path


def extract_messages(conversation):
    """Extract ordered messages from a conversation."""
    mapping = conversation.get("mapping", {})
    current_node = conversation.get("current_node")
    
    messages = linearize_conversation(mapping, current_node)
    
    result = []
    for msg in messages:
        author = msg.get("author", {})
        role = author.get("role", "unknown")
        name = author.get("name")
        
        content = msg.get("content", {})
        content_type = content.get("content_type", "")
        parts = content.get("parts", [])
        
        text = ""
        if parts:
            text = extract_text_from_parts(parts)
        elif content.get("text"):
            text = content["text"]
        
        # Skip empty system messages and tool internals
        if not text or not text.strip():
            continue
        if role == "system" and len(text.strip()) < 5:
            continue
            
        display_role = role
        if name:
            display_role = f"{role} ({name})"
        
        result.append({
            "role": display_role,
            "text": text.strip(),
            "timestamp": msg.get("create_time"),
            "model": msg.get("metadata", {}).get("model_slug", ""),
        })
    
    return result


def get_first_user_message(messages):
    """Get the first substantive user message for topic detection."""
    for msg in messages:
        if msg["role"] == "user" and len(msg["text"]) > 5:
            return msg["text"][:500]  # First 500 chars
    return ""


def get_model_used(conversation, messages):
    """Determine the primary model used."""
    # Check conversation-level default
    model = conversation.get("default_model_slug", "")
    if model:
        return model
    
    # Fall back to first assistant message model
    for msg in messages:
        if "assistant" in msg["role"] and msg.get("model"):
            return msg["model"]
    
    return "unknown"


def message_count_by_role(messages):
    """Count messages by role."""
    counts = {"user": 0, "assistant": 0, "other": 0}
    for msg in messages:
        if msg["role"] == "user":
            counts["user"] += 1
        elif "assistant" in msg["role"]:
            counts["assistant"] += 1
        else:
            counts["other"] += 1
    return counts


def conversation_to_markdown(conv_meta, messages):
    """Convert a conversation to readable markdown."""
    lines = []
    lines.append(f"# {conv_meta['title']}")
    lines.append(f"")
    lines.append(f"**Date:** {conv_meta['date']}")
    lines.append(f"**Model:** {conv_meta['model']}")
    lines.append(f"**Messages:** {conv_meta['message_count']} ({conv_meta['user_messages']} user, {conv_meta['assistant_messages']} assistant)")
    lines.append(f"**ID:** {conv_meta['id']}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    
    for msg in messages:
        role_label = msg["role"].upper()
        ts = timestamp_to_datetime(msg["timestamp"]) if msg["timestamp"] else ""
        
        lines.append(f"## {role_label}")
        if ts:
            lines.append(f"*{ts}*")
        lines.append(f"")
        lines.append(msg["text"])
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")
    
    return "\n".join(lines)


def process_export(export_dir):
    """Main processing function."""
    export_path = Path(export_dir)
    
    # Find all conversation JSON files
    json_files = sorted(export_path.glob("conversations-*.json"))
    
    if not json_files:
        print(f"No conversations-*.json files found in {export_dir}")
        sys.exit(1)
    
    print(f"Found {len(json_files)} JSON files")
    
    # Output directories
    catalog_path = export_path.parent / "catalog.json"
    convos_dir = export_path.parent / "conversations"
    convos_dir.mkdir(exist_ok=True)
    
    catalog = []
    total = 0
    errors = 0
    
    for json_file in json_files:
        print(f"Processing {json_file.name}...")
        
        with open(json_file, "r", encoding="utf-8") as f:
            try:
                conversations = json.load(f)
            except json.JSONDecodeError as e:
                print(f"  ERROR reading {json_file.name}: {e}")
                continue
        
        for conv in conversations:
            total += 1
            try:
                conv_id = conv.get("id", conv.get("conversation_id", f"unknown-{total}"))
                title = conv.get("title", "Untitled")
                create_time = conv.get("create_time")
                
                messages = extract_messages(conv)
                counts = message_count_by_role(messages)
                model = get_model_used(conv, messages)
                first_msg = get_first_user_message(messages)
                
                meta = {
                    "id": conv_id,
                    "title": title,
                    "date": timestamp_to_date(create_time),
                    "datetime": timestamp_to_datetime(create_time),
                    "create_time": create_time,
                    "model": model,
                    "message_count": len(messages),
                    "user_messages": counts["user"],
                    "assistant_messages": counts["assistant"],
                    "first_user_message": first_msg,
                    "is_archived": conv.get("is_archived", False),
                    "gizmo_id": conv.get("gizmo_id"),  # Custom GPT if any
                }
                
                catalog.append(meta)
                
                # Write individual conversation markdown
                date_prefix = timestamp_to_date(create_time).replace("-", "")
                safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title)[:80].strip()
                filename = f"{date_prefix}_{safe_title}.md"
                
                md_content = conversation_to_markdown(meta, messages)
                
                conv_file = convos_dir / filename
                # Handle duplicate filenames
                counter = 1
                while conv_file.exists():
                    conv_file = convos_dir / f"{date_prefix}_{safe_title}_{counter}.md"
                    counter += 1
                
                with open(conv_file, "w", encoding="utf-8") as f:
                    f.write(md_content)
                    
            except Exception as e:
                errors += 1
                print(f"  ERROR on conversation {total}: {e}")
                continue
    
    # Sort catalog by date (newest first)
    catalog.sort(key=lambda x: x.get("create_time") or 0, reverse=True)
    
    # Write catalog
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    
    # Write summary stats
    dates = [c["date"] for c in catalog if c["date"] != "unknown"]
    models = {}
    for c in catalog:
        m = c["model"] or "unknown"
        models[m] = models.get(m, 0) + 1
    
    print(f"\n{'='*50}")
    print(f"DONE!")
    print(f"{'='*50}")
    print(f"Total conversations: {total}")
    print(f"Errors: {errors}")
    print(f"Date range: {min(dates) if dates else '?'} to {max(dates) if dates else '?'}")
    print(f"Models used: {json.dumps(models, indent=2)}")
    print(f"\nOutput:")
    print(f"  Catalog: {catalog_path}")
    print(f"  Conversations: {convos_dir}/ ({len(list(convos_dir.glob('*.md')))} files)")


if __name__ == "__main__":
    # Default to ./extracted if no arg given
    if len(sys.argv) > 1:
        export_dir = sys.argv[1]
    else:
        # Try current dir, then ./extracted
        if list(Path(".").glob("conversations-*.json")):
            export_dir = "."
        elif (Path(".") / "extracted").exists():
            export_dir = "./extracted"
        else:
            print("Usage: python3 build_catalog.py [path_to_extracted_dir]")
            print("Run from the ChatGPT Export directory, or pass the path to the extracted/ folder.")
            sys.exit(1)
    
    process_export(export_dir)
