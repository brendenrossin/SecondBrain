"""Conversation management API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from secondbrain.api.dependencies import get_conversation_store
from secondbrain.models import Conversation, ConversationSummary
from secondbrain.stores.conversation import ConversationStore

router = APIRouter(prefix="/api/v1", tags=["conversations"])


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    conversation_store: Annotated[ConversationStore, Depends(get_conversation_store)],
    limit: int = 50,
) -> list[ConversationSummary]:
    """List recent conversations."""
    rows = conversation_store.list_conversations(limit=limit)
    return [
        ConversationSummary(
            conversation_id=r["conversation_id"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            message_count=r["message_count"],
            preview=r["preview"],
        )
        for r in rows
    ]


@router.get("/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(
    conversation_id: str,
    conversation_store: Annotated[ConversationStore, Depends(get_conversation_store)],
) -> Conversation:
    """Get a conversation with its messages."""
    convo = conversation_store.get_conversation(conversation_id)
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return convo


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    conversation_store: Annotated[ConversationStore, Depends(get_conversation_store)],
) -> dict[str, str]:
    """Delete a conversation."""
    conversation_store.delete_conversation(conversation_id)
    return {"status": "deleted"}
