"""Pydantic models for the SecondBrain API."""

from enum import StrEnum

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
    provider: str = "openai"  # "openai" or "local"


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
    days_open: int
    first_date: str
    latest_date: str
    appearance_count: int


class ConversationSummary(BaseModel):
    """Summary of a conversation for listing."""

    conversation_id: str
    created_at: str
    updated_at: str
    message_count: int
    preview: str


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
