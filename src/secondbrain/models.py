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
