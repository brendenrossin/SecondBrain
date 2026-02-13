"""Pydantic models for the SecondBrain API."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class RetrievalLabel(StrEnum):
    """Labels for retrieval evaluation."""

    PASS = "PASS"
    NO_RESULTS = "NO_RESULTS"
    IRRELEVANT = "IRRELEVANT"
    HALLUCINATION_RISK = "HALLUCINATION_RISK"


class Citation(BaseModel):
    """A citation to a chunk in the vault."""

    note_path: str
    note_title: str
    heading_path: list[str]
    chunk_id: str
    snippet: str
    similarity_score: float
    rerank_score: float


class AskRequest(BaseModel):
    """Request body for the /ask endpoint."""

    query: str
    conversation_id: str | None = None
    top_n: int = Field(default=5, ge=1, le=20)
    provider: str = "anthropic"  # "anthropic", "openai", or "local"


class AskResponse(BaseModel):
    """Response body for the /ask endpoint."""

    answer: str
    conversation_id: str
    citations: list[Citation]
    retrieval_label: RetrievalLabel


class Chunk(BaseModel):
    """A chunk of text from a note."""

    chunk_id: str
    note_path: str
    note_title: str
    heading_path: list[str]
    chunk_index: int
    chunk_text: str
    checksum: str
    token_count: int | None = None
    note_folder: str | None = None
    note_date: str | None = None


class Note(BaseModel):
    """A parsed note from the vault."""

    path: str
    title: str
    content: str
    frontmatter: dict[str, object]


class ConversationMessage(BaseModel):
    """A message in a conversation."""

    role: str  # "user" or "assistant"
    content: str


class Conversation(BaseModel):
    """A conversation with history."""

    conversation_id: str
    messages: list[ConversationMessage]


class TaskResponse(BaseModel):
    """A task from the aggregated task view."""

    text: str
    category: str
    sub_project: str
    due_date: str
    completed: bool
    status: str = "open"  # "open", "in_progress", "done"
    days_open: int
    first_date: str
    latest_date: str
    appearance_count: int


class TaskUpdateRequest(BaseModel):
    """Request body for updating a task."""

    text: str
    category: str
    sub_project: str
    status: Literal["open", "in_progress", "done"] | None = None
    due_date: str | None = None  # YYYY-MM-DD, "" to remove, None = no change
    new_category: str | None = None  # Move to different category
    new_sub_project: str | None = None  # Move to different sub-project


class ConversationSummary(BaseModel):
    """Summary of a conversation for listing."""

    conversation_id: str
    created_at: str
    updated_at: str
    message_count: int
    preview: str


# --- Phase 5: Morning Briefing ---


class BriefingTask(BaseModel):
    """A task subset for the morning briefing (omits completed/latest_date/appearance_count)."""

    text: str
    category: str
    sub_project: str
    due_date: str
    days_open: int
    first_date: str


class DailyContext(BaseModel):
    """Focus and Notes sections from a recent daily note."""

    date: str
    focus_items: list[str]
    notes_items: list[str]


class BriefingResponse(BaseModel):
    """Morning briefing data assembled from tasks and daily notes."""

    today: str
    today_display: str
    overdue_tasks: list[BriefingTask]
    due_today_tasks: list[BriefingTask]
    aging_followups: list[BriefingTask]
    yesterday_context: DailyContext | None
    today_context: DailyContext | None
    today_events: list["EventResponse"]
    total_open: int


# --- Phase 3: Metadata Extraction + Suggestions ---


class Entity(BaseModel):
    """An entity extracted from a note."""

    text: str
    entity_type: str  # "person", "org", "product", "place"
    confidence: float


class DateMention(BaseModel):
    """A date mention extracted from a note."""

    text: str
    normalized_date: str | None  # YYYY-MM-DD
    date_type: str  # "deadline", "event", "reference"
    confidence: float


class ActionItem(BaseModel):
    """An action item extracted from a note."""

    text: str
    confidence: float
    priority: str | None  # "high", "medium", "low"


class NoteMetadata(BaseModel):
    """Extracted metadata for a vault note."""

    note_path: str
    summary: str
    key_phrases: list[str]
    entities: list[Entity]
    dates: list[DateMention]
    action_items: list[ActionItem]
    extracted_at: str  # ISO timestamp
    content_hash: str  # to detect staleness
    model_used: str  # provenance


class RelatedNote(BaseModel):
    """A note related to a source note."""

    note_path: str
    note_title: str
    similarity_score: float
    shared_entities: list[str]


class LinkSuggestion(BaseModel):
    """A suggested wiki-link to add to a note."""

    target_note_path: str
    target_note_title: str
    anchor_text: str  # text in source that should become [[link]]
    confidence: float
    reason: str


class TagSuggestion(BaseModel):
    """A suggested tag for a note."""

    tag: str
    confidence: float
    source_notes: list[str]  # similar notes that have this tag


class NoteSuggestions(BaseModel):
    """Suggestions for a note: related notes, links, tags."""

    note_path: str
    note_title: str
    related_notes: list[RelatedNote]
    suggested_links: list[LinkSuggestion]
    suggested_tags: list[TagSuggestion]
    generated_at: str


# --- Phase 6: LLM Cost Tracking + Admin ---


class UsageCostBreakdown(BaseModel):
    """Cost breakdown for a provider or usage type."""

    cost: float
    calls: int
    input_tokens: int
    output_tokens: int


class CostSummaryResponse(BaseModel):
    """Aggregated cost summary response."""

    total_cost: float
    total_calls: int
    by_provider: dict[str, UsageCostBreakdown]
    by_usage_type: dict[str, UsageCostBreakdown]
    period: str


class DailyCost(BaseModel):
    """Cost data for a single day."""

    date: str
    cost_usd: float
    calls: int
    by_provider: dict[str, float]


class DailyCostsResponse(BaseModel):
    """Daily cost time series response."""

    days: int
    daily: list[DailyCost]


class AdminStatsResponse(BaseModel):
    """System-wide admin statistics."""

    total_queries: int
    avg_latency_ms: float
    total_conversations: int
    index_file_count: int
    total_llm_calls: int
    total_llm_cost: float


# --- Phase 6.5: Quick Capture ---


class EventResponse(BaseModel):
    """A calendar event from a daily note."""

    title: str
    date: str  # YYYY-MM-DD
    time: str  # "HH:MM" or ""
    end_date: str  # "YYYY-MM-DD" or ""
    source_file: str


class CaptureRequest(BaseModel):
    """Request body for the /capture endpoint."""

    text: str = Field(min_length=1, max_length=10000)


class CaptureResponse(BaseModel):
    """Response body for the /capture endpoint."""

    filename: str
    message: str
