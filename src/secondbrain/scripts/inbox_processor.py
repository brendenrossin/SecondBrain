"""Inbox processor: classifies dictated notes and routes to proper vault folders."""

import logging
from datetime import datetime
from pathlib import Path

import frontmatter

from secondbrain.scripts.llm_client import LLMClient

logger = logging.getLogger(__name__)

CLASSIFICATION_PROMPT = """You are an Obsidian vault organizer. Given a raw dictated note, classify it and extract structured data.

Return ONLY valid JSON with these fields:
{
  "note_type": "daily_note" | "note" | "project" | "concept",
  "suggested_title": "Short descriptive title",
  "date": "YYYY-MM-DD (the date the note is about, or today if unclear)",
  "category": "AT&T" | "PwC" | "Personal" | null,
  "sub_project": "sub-project name or null",
  "tags": ["tag1", "tag2"],
  "focus_items": ["focus item 1"],
  "notes_items": ["note 1", "note 2"],
  "tasks": [
    {"text": "task description", "category": "AT&T", "sub_project": "AI Receptionist", "due_date": "YYYY-MM-DD or null"}
  ],
  "content": "cleaned up body text for non-daily notes",
  "links": ["related topic 1"]
}

Classification rules:
- "daily_note": Contains a mix of tasks, notes, and focus items for a specific day
- "note": A standalone piece of information, observation, or reference
- "project": Describes a project with objectives, milestones, or deliverables
- "concept": An idea, definition, or knowledge topic

IMPORTANT task vs focus rules:
- ANY actionable item (something the user needs to DO) MUST go in "tasks", NOT "focus_items".
- "focus_items" are ONLY for high-level themes or areas of attention for the day (e.g. "Azure certification prep").
- When in doubt, put it in "tasks". Err heavily toward tasks over focus items.
- Examples that are TASKS: "update resume", "send email to X", "finish taxes", "get W2", "complete course"
- Examples that are FOCUS: "Azure certification", "Q2 planning", "career development"

IMPORTANT due_date rules:
- If the user mentions ANY deadline, compute the actual YYYY-MM-DD date for "due_date".
- "tomorrow" = the day after today's date.
- "Monday", "Tuesday", etc. = the NEXT occurrence of that weekday from today.
- "end of February" = last day of February (e.g. 2026-02-28).
- "early April" = 2026-04-07 (use ~first week).
- "in two days" = today + 2 days.
- "next week" = the Monday of the following week.
- If no deadline is mentioned, set due_date to null.

For daily_note: extract focus_items, notes_items, and tasks with categories.
For other types: put the main content in "content" field.
Always provide a date (use today if not mentioned).
Categories are typically: AT&T, PwC, or Personal."""


def process_inbox(vault_path: Path) -> list[str]:
    """Process all markdown files in the Inbox folder.

    Returns list of actions taken (for logging/display).
    """
    inbox_dir = vault_path / "Inbox"
    if not inbox_dir.exists():
        logger.info("No Inbox directory found at %s", inbox_dir)
        return []

    md_files = sorted(inbox_dir.glob("*.md"))
    if not md_files:
        logger.info("Inbox is empty")
        return []

    llm = LLMClient()
    actions = []

    for md_file in md_files:
        try:
            action = _process_single_file(md_file, vault_path, llm)
            actions.append(action)
            logger.info("Processed: %s -> %s", md_file.name, action)
        except Exception:
            logger.error("Failed to process %s", md_file.name, exc_info=True)
            actions.append(f"FAILED: {md_file.name}")

    return actions


def _process_single_file(md_file: Path, vault_path: Path, llm: LLMClient) -> str:
    """Process a single inbox file: classify and route."""
    raw_text = md_file.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")

    user_prompt = f"Today's date: {today}\n\nRaw note:\n{raw_text}"
    classification = llm.chat_json(CLASSIFICATION_PROMPT, user_prompt)

    note_type = classification.get("note_type", "note")

    if note_type == "daily_note":
        action = _route_daily_note(classification, vault_path)
    elif note_type == "project":
        action = _route_to_folder(classification, vault_path, "20_Projects", "project")
    elif note_type == "concept":
        action = _route_to_folder(classification, vault_path, "30_Concepts", "concept")
    else:
        action = _route_to_folder(classification, vault_path, "10_Notes", "note")

    # Remove processed inbox file
    md_file.unlink()
    return action


def _route_daily_note(classification: dict, vault_path: Path) -> str:
    """Route a daily_note classification to the daily notes folder."""
    date_str = classification.get("date", datetime.now().strftime("%Y-%m-%d"))
    daily_dir = vault_path / "00_Daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    daily_file = daily_dir / f"{date_str}.md"

    if daily_file.exists():
        # Append to existing daily note
        _append_to_daily(daily_file, classification)
        return f"Appended to 00_Daily/{date_str}.md"
    else:
        # Create new daily note
        _create_daily_note(daily_file, classification, date_str)
        return f"Created 00_Daily/{date_str}.md"


def _append_to_daily(daily_file: Path, classification: dict) -> None:
    """Append classified items to an existing daily note."""
    content = daily_file.read_text(encoding="utf-8")

    # Append focus items
    for item in classification.get("focus_items", []):
        if item and item not in content:
            content = _append_under_heading(content, "## Focus", f"- {item}")

    # Append notes items
    for item in classification.get("notes_items", []):
        if item and item not in content:
            content = _append_under_heading(content, "## Notes", f"- {item}")

    # Append tasks under proper category/sub-project headings
    for task in classification.get("tasks", []):
        task_text = task.get("text", "")
        if not task_text or task_text in content:
            continue
        category = task.get("category")
        sub_project = task.get("sub_project")
        due_date = task.get("due_date")
        due_suffix = f" (due: {due_date})" if due_date else ""
        task_line = f"- [ ] {task_text}{due_suffix}"

        if category and sub_project:
            # Ensure category heading exists under ## Tasks, then sub-project under that
            content = _ensure_task_hierarchy(content, category, sub_project, task_line)
        elif category:
            content = _ensure_task_category(content, category, task_line)
        else:
            content = _append_under_heading(content, "## Tasks", task_line)

    daily_file.write_text(content, encoding="utf-8")


def _create_daily_note(daily_file: Path, classification: dict, date_str: str) -> None:
    """Create a new daily note from classification data."""
    tags = classification.get("tags", [])

    lines = [
        "---",
        "type: daily",
        f"date: {date_str}",
        "tags:",
    ]
    for tag in tags:
        lines.append(f"  - {tag}")
    lines.append("---")
    lines.append("")
    lines.append("## Focus")
    for item in classification.get("focus_items", []):
        lines.append(f"- {item}")
    if not classification.get("focus_items"):
        lines.append("- ")
    lines.append("")

    lines.append("## Notes")
    for item in classification.get("notes_items", []):
        lines.append(f"- {item}")
    if not classification.get("notes_items"):
        lines.append("- ")
    lines.append("")

    lines.append("## Tasks")
    # Group tasks by category and sub_project
    tasks = classification.get("tasks", [])
    tasks_by_cat: dict[str, dict[str, list[dict]]] = {}
    for task in tasks:
        cat = task.get("category", "Uncategorized")
        sub = task.get("sub_project", "")
        tasks_by_cat.setdefault(cat, {}).setdefault(sub, []).append(task)

    for cat, subs in tasks_by_cat.items():
        lines.append(f"### {cat}")
        for sub, task_items in subs.items():
            if sub:
                lines.append(f"#### {sub}")
            for t in task_items:
                due = t.get("due_date")
                due_suffix = f" (due: {due})" if due else ""
                lines.append(f"- [ ] {t.get('text', '')}{due_suffix}")
    if not tasks:
        lines.append("- [ ] ")
    lines.append("")

    lines.append("## Links surfaced today")
    lines.append("- ")

    daily_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _route_to_folder(
    classification: dict, vault_path: Path, folder: str, note_type: str
) -> str:
    """Route a note/project/concept to its target folder."""
    title = classification.get("suggested_title", "Untitled")
    # Sanitize title for filename
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
    if not safe_title:
        safe_title = "Untitled"

    target_dir = vault_path / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{safe_title}.md"

    # Avoid overwriting existing files
    if target_file.exists():
        counter = 1
        while target_file.exists():
            target_file = target_dir / f"{safe_title} {counter}.md"
            counter += 1

    today = datetime.now().strftime("%Y-%m-%d")
    tags = classification.get("tags", [])
    content_body = classification.get("content", "")

    post = frontmatter.Post(content_body)
    post.metadata["type"] = note_type
    post.metadata["tags"] = tags
    post.metadata["created"] = today
    post.metadata["updated"] = today

    if note_type == "project":
        post.metadata["status"] = "active"

    target_file.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    return f"Created {folder}/{target_file.name}"


def _append_under_heading(content: str, heading: str, line: str) -> str:
    """Append a line under a specific heading in markdown content."""
    lines = content.split("\n")
    insert_idx = None

    for i, ln in enumerate(lines):
        if ln.strip() == heading:
            # Find the end of this section (next heading of same or higher level)
            heading_level = len(heading) - len(heading.lstrip("#"))
            insert_idx = i + 1
            for j in range(i + 1, len(lines)):
                stripped = lines[j].strip()
                if stripped.startswith("#") and not stripped.startswith("#" * (heading_level + 1)):
                    # Hit a same-level or higher heading
                    break
                insert_idx = j + 1
            break

    if insert_idx is not None:
        lines.insert(insert_idx, line)
    else:
        # Heading not found, append at end
        lines.append("")
        lines.append(heading)
        lines.append(line)

    return "\n".join(lines)


def _ensure_task_hierarchy(
    content: str, category: str, sub_project: str, task_line: str
) -> str:
    """Ensure ### category and #### sub_project exist under ## Tasks, then append task."""
    lines = content.split("\n")
    tasks_idx = None
    cat_idx = None
    sub_idx = None
    tasks_end = len(lines)

    # Find ## Tasks section
    for i, ln in enumerate(lines):
        if ln.strip() == "## Tasks":
            tasks_idx = i
            for j in range(i + 1, len(lines)):
                if lines[j].strip().startswith("## ") and not lines[j].strip().startswith("### "):
                    tasks_end = j
                    break
            break

    if tasks_idx is None:
        lines.append("")
        lines.append("## Tasks")
        lines.append(f"### {category}")
        lines.append(f"#### {sub_project}")
        lines.append(task_line)
        return "\n".join(lines)

    # Find ### category within Tasks section
    for i in range(tasks_idx + 1, tasks_end):
        if lines[i].strip() == f"### {category}":
            cat_idx = i
            break

    if cat_idx is None:
        # Insert category at end of Tasks section
        lines.insert(tasks_end, f"### {category}")
        lines.insert(tasks_end + 1, f"#### {sub_project}")
        lines.insert(tasks_end + 2, task_line)
        return "\n".join(lines)

    # Find #### sub_project under this category
    cat_end = tasks_end
    for i in range(cat_idx + 1, tasks_end):
        if lines[i].strip().startswith("### "):
            cat_end = i
            break

    for i in range(cat_idx + 1, cat_end):
        if lines[i].strip() == f"#### {sub_project}":
            sub_idx = i
            break

    if sub_idx is None:
        lines.insert(cat_end, f"#### {sub_project}")
        lines.insert(cat_end + 1, task_line)
        return "\n".join(lines)

    # Find end of sub_project section
    sub_end = cat_end
    for i in range(sub_idx + 1, cat_end):
        if lines[i].strip().startswith("#### ") or lines[i].strip().startswith("### "):
            sub_end = i
            break

    lines.insert(sub_end, task_line)
    return "\n".join(lines)


def _ensure_task_category(content: str, category: str, task_line: str) -> str:
    """Ensure ### category exists under ## Tasks, then append task."""
    lines = content.split("\n")
    tasks_idx = None
    cat_idx = None
    tasks_end = len(lines)

    for i, ln in enumerate(lines):
        if ln.strip() == "## Tasks":
            tasks_idx = i
            for j in range(i + 1, len(lines)):
                if lines[j].strip().startswith("## ") and not lines[j].strip().startswith("### "):
                    tasks_end = j
                    break
            break

    if tasks_idx is None:
        lines.append("")
        lines.append("## Tasks")
        lines.append(f"### {category}")
        lines.append(task_line)
        return "\n".join(lines)

    for i in range(tasks_idx + 1, tasks_end):
        if lines[i].strip() == f"### {category}":
            cat_idx = i
            break

    if cat_idx is None:
        lines.insert(tasks_end, f"### {category}")
        lines.insert(tasks_end + 1, task_line)
        return "\n".join(lines)

    # Find end of category section
    cat_end = tasks_end
    for i in range(cat_idx + 1, tasks_end):
        if lines[i].strip().startswith("### "):
            cat_end = i
            break

    lines.insert(cat_end, task_line)
    return "\n".join(lines)
