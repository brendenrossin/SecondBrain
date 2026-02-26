"""Inbox processor: classifies dictated notes and routes to proper vault folders."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import frontmatter

from secondbrain.scripts.llm_client import LLMClient
from secondbrain.settings import load_settings

logger = logging.getLogger(__name__)

# ============================================================
# USER CONFIGURATION — Customize these for your vault
# ============================================================

# Living documents: notes that get updated in-place instead
# of creating new files. Each entry maps a document name to
# (vault_path, semantics). "replace" overwrites content;
# "append" adds to the end.
LIVING_DOCUMENTS: dict[str, tuple[str, str]] = {
    "Grocery List": ("10_Notes/Grocery List.md", "replace"),
    "Recipe Ideas": ("10_Notes/Recipe Ideas.md", "append"),
}

# Vault folder structure. Change these if your Obsidian vault
# uses different folder names.
VAULT_FOLDERS = {
    "daily": "00_Daily",
    "notes": "10_Notes",
    "projects": "20_Projects",
    "concepts": "30_Concepts",
}

# ============================================================
# END USER CONFIGURATION
# ============================================================

SEGMENTATION_PROMPT = """You are a text segmentation assistant for a personal knowledge base. Given raw dictated text, decide whether to split it into separate segments.

The key question: "Would someone search for these topics separately?" If yes, split. If the topics provide useful context for a single search, keep them together.

Return ONLY valid JSON: an array of segment objects.
[
  {"segment_id": 1, "topic": "Short topic label", "content": "verbatim text for this segment"},
  {"segment_id": 2, "topic": "Another topic", "content": "verbatim text..."}
]

Rules:
- Preserve the original text VERBATIM in each segment's "content" field — do not summarize or rewrite.
- A single segment is the DEFAULT. Only split when topics are clearly unrelated.
- Dictated text often rambles — context switches mid-sentence are NOT reasons to split.
- Each segment must have all three fields: segment_id, topic, content.

Examples:

Input: "Had a call with Sarah about the Azure migration timeline. She's worried about the Q3 deadline. Also I need to pick up groceries — milk, eggs, and bread."
Output: 2 segments — Azure migration call (work topic) and grocery list (personal errand). These would never be searched together.

Input: "Thinking about career development. Talked to my manager about the promotion path. He suggested getting the AWS cert. I should also update my resume to reflect the recent project work."
Output: 1 segment — all of this is career planning context that supports one search.

Input: "The AI Receptionist demo went well today. Client loved the voice quality. Separately, I had an idea for a personal budgeting app — track spending by category with weekly summaries."
Output: 2 segments — work demo feedback and personal app idea are completely different domains."""


def _load_categories(data_path: Path) -> list[str]:
    """Load category names from settings file."""
    settings = load_settings(data_path)
    return [c["name"] for c in settings.get("categories", [])]


def _load_all_sub_projects(data_path: Path) -> dict[str, dict[str, str]]:
    """Return {category_name: {sub_project_name: description}} for all categories with sub_projects."""
    settings = load_settings(data_path)
    return {
        c["name"]: c["sub_projects"]
        for c in settings.get("categories", [])
        if c.get("sub_projects")
    }


def _build_classification_prompt(data_path: Path) -> str:
    """Build the classification prompt dynamically from settings."""
    categories = _load_categories(data_path)
    all_sub_projects = _load_all_sub_projects(data_path)

    category_options = " | ".join(f'"{c}"' for c in categories)
    category_list = ", ".join(categories)
    first_category = categories[0] if categories else "Work"

    # Build sub_project prompt for ALL categories that have them
    sub_project_lines: list[str] = []
    for cat_name, subs in all_sub_projects.items():
        sub_project_lines.append(
            f'\nFor category "{cat_name}", assign sub_project from these subcategories:'
        )
        for name, desc in subs.items():
            sub_project_lines.append(f'- "{name}": {desc}')
        sub_project_lines.append(
            'If unsure between subcategories, prefer "General" over guessing wrong.'
        )
    sub_project_prompt = "\n".join(sub_project_lines)

    living_docs_prompt = "\n".join(
        f'    - "{name}" ({sem} semantics) → {"replaces existing content" if sem == "replace" else "appends new entries"}'
        for name, (_, sem) in LIVING_DOCUMENTS.items()
    )

    return f"""You are an Obsidian vault organizer. Given a raw dictated note, classify it and extract structured data.

Return ONLY valid JSON with these fields:
{{
  "note_type": "daily_note" | "note" | "project" | "concept" | "living_document" | "event",
  "suggested_title": "Short descriptive title",
  "existing_note": "exact title of an existing note to append to, or null",
  "date": "YYYY-MM-DD (the date the note is about, or today if unclear)",
  "category": {category_options} | null,
  "sub_project": "sub-project name or null",
  "tags": ["tag1", "tag2"],
  "focus_items": ["focus item 1"],
  "notes_items": ["note 1", "note 2"],
  "tasks": [
    {{"text": "task description", "category": "{first_category}", "sub_project": "AI Receptionist", "due_date": "YYYY-MM-DD or null"}}
  ],
  "event_title": "short event title or null",
  "event_date": "YYYY-MM-DD or null",
  "event_time": "HH:MM or null",
  "event_end_date": "YYYY-MM-DD or null",
  "content": "cleaned up body text for non-daily notes",
  "links": ["related topic 1"],
  "living_doc_name": "matched document name or null"
}}

Note matching rules:
- If the user's message contains an existing note title from the list provided, set "existing_note" to that EXACT title.
- Only match when the new content is clearly about the same topic as the existing note.
- When "existing_note" is set, keep "note_type" as "note" or "concept" (whichever folder the note lives in).
- When in doubt, set "existing_note" to null and create a new note.

Classification rules:
- "daily_note": Contains a mix of tasks, notes, and focus items for a specific day
- "note": A standalone piece of information, observation, or reference
- "project": Describes a project with objectives, milestones, or deliverables
- "concept": An idea, definition, or knowledge topic
- "event": A specific occurrence at a date/time — appointments, visits, trips, meetings. NOT actionable tasks.
  Examples: "Mom visiting at 10:30" → event, "Dentist appointment Thursday 2pm" → event
  Counter-examples: "Follow up with recruiter" → task (actionable), "Prepare for demo" → task
  When classified as event, populate event_title, event_date, event_time (if known), event_end_date (if multi-day).
- "living_document": Content that updates a known persistent document.
  Known living documents:
{living_docs_prompt}
  Set "living_doc_name" to the matched document name.

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
{sub_project_prompt}

For daily_note: extract focus_items, notes_items, and tasks with categories.
For other types: put the main content in "content" field.
Always provide a date (use today if not mentioned).
Categories are typically: {category_list}."""


def _get_existing_titles(vault_path: Path, max_per_folder: int = 75) -> str:
    """Collect note titles from notes and concepts folders for matching.

    Returns a formatted string of titles grouped by folder.
    Projects are excluded to avoid corruption risk.
    """
    folders = [VAULT_FOLDERS["notes"], VAULT_FOLDERS["concepts"]]
    sections = []
    for folder in folders:
        folder_path = vault_path / folder
        if not folder_path.exists():
            continue
        titles = sorted(
            [f.stem for f in folder_path.glob("*.md")],
            key=str.lower,
        )[:max_per_folder]
        if titles:
            section = f"{folder}/:\n" + "\n".join(f"  - {t}" for t in titles)
            sections.append(section)
    return "\n\n".join(sections)


def _append_to_existing_note(classification: dict[str, Any], vault_path: Path, folder: str) -> str:
    """Append content to an existing note under a date heading."""
    existing_note = classification.get("existing_note", "")
    content_body = classification.get("content", "")
    today = datetime.now().strftime("%Y-%m-%d")

    target_file = vault_path / folder / f"{existing_note}.md"
    if not target_file.exists():
        # Fallback: create a new note instead
        return _route_to_folder(classification, vault_path, folder, "note")

    existing = target_file.read_text(encoding="utf-8")
    post = frontmatter.loads(existing)
    date_heading = f"### {today}"
    post.content = post.content.rstrip() + f"\n\n{date_heading}\n{content_body}"
    post.metadata["updated"] = today
    target_file.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    return f"Appended to {folder}/{existing_note}.md"


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

    # Create a UsageStore for standalone inbox runs
    from secondbrain.config import get_settings
    from secondbrain.stores.usage import UsageStore

    settings = get_settings()
    data_path = Path(settings.data_path) if settings.data_path else Path("data")
    usage_store = UsageStore(data_path / "usage.db")
    try:
        llm = LLMClient(usage_store=usage_store)
        actions = []
        inbox_start = time.time()

        for md_file in md_files:
            try:
                file_actions = _process_single_file(md_file, vault_path, llm, data_path)
                actions.extend(file_actions)
                for action in file_actions:
                    logger.info("Processed: %s -> %s", md_file.name, action)
                # Move to _processed/ on success
                _move_to_subfolder(md_file, "_processed")
            except Exception:
                logger.error("Failed to process %s", md_file.name, exc_info=True)
                actions.append(f"FAILED: {md_file.name}")
                _move_to_subfolder(md_file, "_failed")

        # Log batch summary for observability
        failed_count = sum(1 for a in actions if a.startswith("FAILED"))
        processed = len(actions) - failed_count
        usage_store.log_usage(
            provider="system",
            model="batch",
            usage_type="inbox_batch",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            metadata={
                "processed": processed,
                "failed": failed_count,
                "duration_ms": int((time.time() - inbox_start) * 1000),
            },
        )

        return actions
    finally:
        usage_store.close()


def _move_to_subfolder(md_file: Path, subfolder: str) -> None:
    """Move an inbox file to a subfolder (e.g. _processed, _failed)."""
    dest_dir = md_file.parent / subfolder
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / md_file.name
    # Avoid overwriting: add timestamp suffix if file exists
    if dest.exists():
        ts = datetime.now().strftime("%H%M%S")
        dest = dest_dir / f"{md_file.stem}_{ts}{md_file.suffix}"
    md_file.rename(dest)


def _is_duplicate(raw_text: str, vault_path: Path) -> bool:
    """Check if this content was already processed recently."""
    content_hash = hashlib.sha1(raw_text.strip().encode()).hexdigest()[:16]
    processed_dir = vault_path / "Inbox" / "_processed"
    if not processed_dir.exists():
        return False
    for f in processed_dir.glob("*.md"):
        try:
            existing_hash = hashlib.sha1(
                f.read_text(encoding="utf-8").strip().encode()
            ).hexdigest()[:16]
            if existing_hash == content_hash:
                return True
        except OSError:
            continue
    return False


def _validate_classification(data: Any) -> bool:
    """Validate that LLM classification output has the required structure."""
    if not isinstance(data, dict):
        return False
    note_type = data.get("note_type")
    if note_type not in ("daily_note", "note", "project", "concept", "living_document", "event"):
        return False
    # Tasks must be a list if present
    tasks = data.get("tasks")
    if tasks is not None and not isinstance(tasks, list):
        return False
    # existing_note must be a string or null/absent
    existing_note = data.get("existing_note")
    return existing_note is None or isinstance(existing_note, str)


def _remap_sub_project(record: dict[str, Any], all_sub_projects: dict[str, dict[str, str]]) -> None:
    """Remap an unrecognized sub_project value to a valid fallback for a single record."""
    cat = record.get("category")
    sub = record.get("sub_project")
    if not (cat and sub and cat in all_sub_projects):
        return
    valid_subs = all_sub_projects[cat]
    if sub not in valid_subs:
        fallback = "General" if "General" in valid_subs else sub
        logger.warning("Unknown %s sub_project '%s', remapping to '%s'", cat, sub, fallback)
        record["sub_project"] = fallback


def _normalize_subcategory(classification: dict[str, Any], data_path: Path) -> None:
    """Remap unrecognized sub_project values for any category with configured sub_projects."""
    all_sub_projects = _load_all_sub_projects(data_path)
    for task in classification.get("tasks", []):
        _remap_sub_project(task, all_sub_projects)
    _remap_sub_project(classification, all_sub_projects)


def _validate_segments(data: Any) -> bool:
    """Validate that LLM segmentation output is a list of segment objects."""
    if not isinstance(data, list):
        return False
    for item in data:
        if not isinstance(item, dict):
            return False
        if "content" not in item:
            return False
    return True


def _segment_content(
    raw_text: str, llm: LLMClient, trace_id: str | None = None
) -> list[dict[str, Any]]:
    """Split raw text into logical segments using LLM.

    Returns a list of segment dicts. Falls back to a single segment
    wrapping the original text if segmentation fails.
    """
    fallback = [{"segment_id": 1, "topic": "Full note", "content": raw_text}]

    # Short texts don't need segmentation
    if len(raw_text) < 300:
        return fallback

    today = datetime.now().strftime("%Y-%m-%d")
    user_prompt = f"Today's date: {today}\n\nRaw dictated text:\n{raw_text}"

    try:
        raw = llm.chat(SEGMENTATION_PROMPT, user_prompt, trace_id=trace_id)
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        segments = json.loads(cleaned)
        if not _validate_segments(segments):
            logger.warning("Segmentation output failed validation, using single segment")
            return fallback
        return list(segments)
    except (json.JSONDecodeError, RuntimeError):
        logger.warning("Segmentation LLM call failed, using single segment")
        return fallback


def _classify_with_retry(
    text: str,
    llm: LLMClient,
    data_path: Path,
    vault_path: Path | None = None,
    max_retries: int = 1,
    trace_id: str | None = None,
) -> dict[str, Any] | None:
    """Classify text with validation and retry on failure."""
    today = datetime.now().strftime("%Y-%m-%d")
    user_prompt = f"Today's date: {today}\n\nRaw note:\n{text}"

    # Inject existing note titles for matching
    if vault_path:
        titles = _get_existing_titles(vault_path)
        if titles:
            user_prompt += f"\n\nExisting notes in vault:\n{titles}"

    classification_prompt = _build_classification_prompt(data_path)

    for attempt in range(1 + max_retries):
        try:
            classification = llm.chat_json(classification_prompt, user_prompt, trace_id=trace_id)
            if _validate_classification(classification):
                _normalize_subcategory(classification, data_path)
                logger.debug("Classification result: %s", json.dumps(classification, indent=2))
                return classification
            logger.warning(
                "Classification validation failed (attempt %d): %s",
                attempt + 1,
                classification.get("note_type"),
            )
        except (json.JSONDecodeError, RuntimeError):
            logger.warning("Classification LLM call failed (attempt %d)", attempt + 1)

    return None


def _process_single_file(
    md_file: Path, vault_path: Path, llm: LLMClient, data_path: Path
) -> list[str]:
    """Process a single inbox file: segment, classify each segment, and route.

    Returns a list of action strings (one per segment routed).
    """
    raw_text = md_file.read_text(encoding="utf-8")

    # Duplicate detection
    if _is_duplicate(raw_text, vault_path):
        logger.info("Skipping duplicate: %s", md_file.name)
        return [f"SKIPPED (duplicate): {md_file.name}"]

    # Generate a trace_id for this file's LLM calls
    trace_id = uuid.uuid4().hex

    # Pass 1: Segmentation
    segments = _segment_content(raw_text, llm, trace_id=trace_id)

    # Pass 2: Classify and route each segment
    actions: list[str] = []
    for segment in segments:
        segment_text = segment.get("content", raw_text)
        classification = _classify_with_retry(
            segment_text, llm, data_path, vault_path=vault_path, trace_id=trace_id
        )
        if classification is None:
            topic = segment.get("topic", "unknown")
            raise ValueError(f"Classification failed for segment: {topic}")

        note_type = classification.get("note_type", "note")
        existing_note = classification.get("existing_note")

        # Check for existing note match before normal routing
        if existing_note and isinstance(existing_note, str):
            # Determine which folder the note lives in
            for folder in [VAULT_FOLDERS["notes"], VAULT_FOLDERS["concepts"]]:
                if (vault_path / folder / f"{existing_note}.md").exists():
                    action = _append_to_existing_note(classification, vault_path, folder)
                    break
            else:
                # File not found in expected folders, fall through to normal routing
                existing_note = None

        if not existing_note or not isinstance(existing_note, str):
            if note_type == "living_document":
                action = _route_living_document(classification, vault_path)
            elif note_type == "event":
                action = _route_event(classification, vault_path)
            elif note_type == "daily_note":
                action = _route_daily_note(classification, vault_path)
            elif note_type == "project":
                action = _route_to_folder(
                    classification, vault_path, VAULT_FOLDERS["projects"], "project"
                )
            elif note_type == "concept":
                action = _route_to_folder(
                    classification, vault_path, VAULT_FOLDERS["concepts"], "concept"
                )
            else:
                action = _route_to_folder(
                    classification, vault_path, VAULT_FOLDERS["notes"], "note"
                )

        # Write tasks to daily note for routes that don't handle tasks themselves.
        # daily_note writes tasks via _create/_append_to_daily; living_document and
        # event routes don't carry actionable tasks.
        if note_type not in ("daily_note", "living_document", "event"):
            _write_tasks_to_daily(classification, vault_path)

        actions.append(action)

    return actions


def _route_living_document(classification: dict[str, Any], vault_path: Path) -> str:
    """Route content to a living document with replace or append semantics."""
    doc_name = classification.get("living_doc_name", "")
    if doc_name not in LIVING_DOCUMENTS:
        # Fall back to regular note routing
        return _route_to_folder(classification, vault_path, VAULT_FOLDERS["notes"], "note")

    rel_path, semantics = LIVING_DOCUMENTS[doc_name]
    target_file = vault_path / rel_path
    target_file.parent.mkdir(parents=True, exist_ok=True)
    content_body = classification.get("content", "")
    today = datetime.now().strftime("%Y-%m-%d")

    if not target_file.exists():
        # Create new file with frontmatter
        post = frontmatter.Post(content_body)
        post.metadata["type"] = "living_document"
        post.metadata["created"] = today
        post.metadata["updated"] = today
        target_file.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
        return f"Created living doc {rel_path}"

    # File exists — apply semantics
    existing = target_file.read_text(encoding="utf-8")

    if semantics == "replace":
        # Archive current content under ## Archive > ### YYYY-MM-DD
        post = frontmatter.loads(existing)
        old_content = post.content.strip()

        # Build archive section
        archive_entry = f"### {today}\n{old_content}"
        if "## Archive" in post.content:
            # Insert new archive entry at the top of the Archive section
            new_content = content_body + "\n\n## Archive\n" + archive_entry
            # Preserve existing archive entries
            archive_start = post.content.index("## Archive")
            archive_rest = post.content[archive_start + len("## Archive") :].strip()
            if archive_rest:
                new_content += "\n\n" + archive_rest
        else:
            new_content = content_body + "\n\n## Archive\n" + archive_entry

        post.content = new_content
        post.metadata["updated"] = today
        target_file.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
        return f"Replaced living doc {rel_path} (archived previous)"

    else:  # append
        post = frontmatter.loads(existing)
        date_heading = f"### {today}"
        post.content = post.content.rstrip() + f"\n\n{date_heading}\n{content_body}"
        post.metadata["updated"] = today
        target_file.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
        return f"Appended to living doc {rel_path}"


def _route_event(classification: dict[str, Any], vault_path: Path) -> str:
    """Route an event classification to the appropriate daily note's ## Events section."""
    event_date = classification.get("event_date") or classification.get(
        "date", datetime.now().strftime("%Y-%m-%d")
    )
    event_title = classification.get("event_title") or classification.get(
        "suggested_title", "Event"
    )
    event_time = classification.get("event_time")
    event_end_date = classification.get("event_end_date")

    daily_dir = vault_path / VAULT_FOLDERS["daily"]
    daily_dir.mkdir(parents=True, exist_ok=True)
    daily_file = daily_dir / f"{event_date}.md"

    # Build the event bullet
    bullet = f"- {event_time} — {event_title}" if event_time else f"- {event_title}"
    if event_end_date:
        bullet += f" (through {event_end_date})"

    if daily_file.exists():
        content = daily_file.read_text(encoding="utf-8")
        # Duplicate detection: check against parsed event bullets only
        if _event_already_exists(content, event_title):
            return f"Event already in 00_Daily/{event_date}.md: {event_title}"
        content = _ensure_events_section(content, bullet)
        daily_file.write_text(content, encoding="utf-8")
        return f"Added event to 00_Daily/{event_date}.md: {event_title}"
    else:
        # Create new daily note with the event
        _create_daily_note(
            daily_file, {"focus_items": [], "notes_items": [], "tasks": [], "tags": []}, event_date
        )
        content = daily_file.read_text(encoding="utf-8")
        content = _ensure_events_section(content, bullet)
        daily_file.write_text(content, encoding="utf-8")
        return f"Created 00_Daily/{event_date}.md with event: {event_title}"


def _event_already_exists(content: str, event_title: str) -> bool:
    """Check if an event with this title already exists in the ## Events section."""
    in_events = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped == "## Events":
            in_events = True
            continue
        if in_events and stripped.startswith("## "):
            break
        if in_events and stripped.startswith("- "):
            # Extract title from bullet: "- HH:MM — title" or "- title"
            bullet_text = stripped[2:].strip()
            # Strip time prefix if present
            time_match = re.match(r"\d{1,2}:\d{2}\s*[—–-]\s*", bullet_text)
            if time_match:
                bullet_text = bullet_text[time_match.end() :]
            # Strip "(through ...)" suffix
            bullet_text = re.sub(r"\s*\(through\s+\d{4}-\d{2}-\d{2}\)\s*$", "", bullet_text)
            if bullet_text.strip() == event_title.strip():
                return True
    return False


def _ensure_events_section(content: str, bullet: str) -> str:
    """Ensure ## Events section exists in daily note and append bullet to it.

    The Events section is placed after frontmatter, before ## Focus.
    """
    lines = content.split("\n")

    # Find existing ## Events section
    events_idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == "## Events":
            events_idx = i
            break

    if events_idx is not None:
        # Find the last bullet line in the Events section
        insert_idx = events_idx + 1
        for j in range(events_idx + 1, len(lines)):
            if lines[j].strip().startswith("## "):
                break
            if lines[j].strip().startswith("- "):
                insert_idx = j + 1
        lines.insert(insert_idx, bullet)
    else:
        # Insert ## Events section before ## Focus (or at end of frontmatter)
        focus_idx = None
        frontmatter_end = 0
        in_frontmatter = False
        for i, ln in enumerate(lines):
            if ln.strip() == "---":
                if not in_frontmatter:
                    in_frontmatter = True
                else:
                    frontmatter_end = i + 1
                    in_frontmatter = False
            if ln.strip() == "## Focus":
                focus_idx = i
                break

        insert_at = focus_idx if focus_idx is not None else frontmatter_end
        # Build the Events block to insert
        block: list[str] = []
        if insert_at > 0 and lines[insert_at - 1].strip() != "":
            block.append("")
        block.extend(["## Events", bullet, ""])
        for j, item in enumerate(block):
            lines.insert(insert_at + j, item)

    return "\n".join(lines)


def _write_tasks_to_daily(classification: dict[str, Any], vault_path: Path) -> str | None:
    """Write tasks from any classification to the appropriate daily note.

    Called after non-daily routing paths (existing note, folder routing) to ensure
    tasks are always written to the daily note regardless of where content is routed.
    Returns a description of what was written, or None if no tasks.
    """
    tasks = classification.get("tasks", [])
    if not tasks:
        return None

    date_str = classification.get("date", datetime.now().strftime("%Y-%m-%d"))
    daily_dir = vault_path / VAULT_FOLDERS["daily"]
    daily_dir.mkdir(parents=True, exist_ok=True)
    daily_file = daily_dir / f"{date_str}.md"

    # Build a tasks-only classification to avoid duplicating focus/notes items
    tasks_only = {"tasks": tasks, "focus_items": [], "notes_items": [], "tags": []}

    if daily_file.exists():
        _append_to_daily(daily_file, tasks_only)
    else:
        _create_daily_note(daily_file, tasks_only, date_str)

    return f"Wrote {len(tasks)} task(s) to {VAULT_FOLDERS['daily']}/{date_str}.md"


def _route_daily_note(classification: dict[str, Any], vault_path: Path) -> str:
    """Route a daily_note classification to the daily notes folder."""
    date_str = classification.get("date", datetime.now().strftime("%Y-%m-%d"))
    daily_dir = vault_path / VAULT_FOLDERS["daily"]
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


def _append_to_daily(daily_file: Path, classification: dict[str, Any]) -> None:
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


def _create_daily_note(daily_file: Path, classification: dict[str, Any], date_str: str) -> None:
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
    tasks_by_cat: dict[str, dict[str, list[dict[str, Any]]]] = {}
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
    classification: dict[str, Any], vault_path: Path, folder: str, note_type: str
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


def _ensure_task_hierarchy(content: str, category: str, sub_project: str, task_line: str) -> str:
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
