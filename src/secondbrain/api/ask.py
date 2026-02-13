"""Ask endpoint for conversational RAG."""

import json
import time
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from secondbrain.api.dependencies import (
    get_answerer,
    get_conversation_store,
    get_link_expander,
    get_local_answerer,
    get_local_reranker,
    get_openai_answerer,
    get_openai_reranker,
    get_query_logger,
    get_reranker,
    get_retriever,
)
from secondbrain.logging.query_logger import QueryLogger
from secondbrain.models import AskRequest, AskResponse, Citation
from secondbrain.retrieval.hybrid import HybridRetriever
from secondbrain.retrieval.link_expander import LinkExpander
from secondbrain.retrieval.reranker import RankedCandidate
from secondbrain.stores.conversation import ConversationStore

router = APIRouter(prefix="/api/v1", tags=["ask"])


def _build_citations(ranked_candidates: list[RankedCandidate]) -> list[Citation]:
    """Build citation list from ranked candidates."""
    return [
        Citation(
            note_path=rc.candidate.note_path,
            note_title=rc.candidate.note_title,
            heading_path=rc.candidate.heading_path,
            chunk_id=rc.candidate.chunk_id,
            snippet=rc.candidate.chunk_text[:200] + "..."
            if len(rc.candidate.chunk_text) > 200
            else rc.candidate.chunk_text,
            similarity_score=rc.candidate.similarity_score,
            rerank_score=rc.rerank_score,
        )
        for rc in ranked_candidates
    ]


@router.post("/ask", response_model=AskResponse)
async def ask(
    request: AskRequest,
    retriever: Annotated[HybridRetriever, Depends(get_retriever)],
    link_expander: Annotated[LinkExpander, Depends(get_link_expander)],
    conversation_store: Annotated[ConversationStore, Depends(get_conversation_store)],
    query_logger: Annotated[QueryLogger, Depends(get_query_logger)],
) -> AskResponse:
    """Ask a question and get an answer with citations."""
    start_time = time.time()

    # Select provider (3-way dispatch)
    if request.provider == "local":
        reranker = get_local_reranker()
        answerer = get_local_answerer()
    elif request.provider == "openai":
        reranker = get_openai_reranker()
        answerer = get_openai_answerer()
    else:
        reranker = get_reranker()
        answerer = get_answerer()

    # Get or create conversation
    conversation_id = conversation_store.get_or_create_conversation(request.conversation_id)

    # Get conversation history
    history = conversation_store.get_recent_messages(conversation_id, limit=10)

    # Retrieve candidates
    candidates = retriever.retrieve(request.query, top_k=10)

    # Rerank candidates
    ranked_candidates, retrieval_label = reranker.rerank(
        request.query, candidates, top_n=request.top_n
    )

    # Expand wiki links from top candidates
    linked_context = link_expander.expand(ranked_candidates)

    # Generate answer
    answer = answerer.answer(
        request.query,
        ranked_candidates,
        retrieval_label,
        conversation_history=history,
        linked_context=linked_context,
    )

    # Build citations
    citations = _build_citations(ranked_candidates)

    # Save conversation
    conversation_store.add_message(conversation_id, "user", request.query)
    conversation_store.add_message(conversation_id, "assistant", answer)

    # Log query
    latency_ms = (time.time() - start_time) * 1000
    query_logger.log_query(
        query=request.query,
        conversation_id=conversation_id,
        retrieval_label=retrieval_label,
        citations=citations,
        latency_ms=latency_ms,
    )

    return AskResponse(
        answer=answer,
        conversation_id=conversation_id,
        citations=citations,
        retrieval_label=retrieval_label,
    )


@router.post("/ask/stream")
async def ask_stream(
    request: AskRequest,
    retriever: Annotated[HybridRetriever, Depends(get_retriever)],
    link_expander: Annotated[LinkExpander, Depends(get_link_expander)],
    conversation_store: Annotated[ConversationStore, Depends(get_conversation_store)],
    query_logger: Annotated[QueryLogger, Depends(get_query_logger)],
) -> EventSourceResponse:
    """Stream an answer with Server-Sent Events."""
    start_time = time.time()

    # Select provider (3-way dispatch)
    if request.provider == "local":
        reranker = get_local_reranker()
        answerer = get_local_answerer()
    elif request.provider == "openai":
        reranker = get_openai_reranker()
        answerer = get_openai_answerer()
    else:
        reranker = get_reranker()
        answerer = get_answerer()

    # Get or create conversation
    conversation_id = conversation_store.get_or_create_conversation(request.conversation_id)

    # Get conversation history
    history = conversation_store.get_recent_messages(conversation_id, limit=10)

    # Retrieve and rerank
    candidates = retriever.retrieve(request.query, top_k=10)
    ranked_candidates, retrieval_label = reranker.rerank(
        request.query, candidates, top_n=request.top_n
    )

    # Expand wiki links from top candidates
    linked_context = link_expander.expand(ranked_candidates)

    # Build citations
    citations = _build_citations(ranked_candidates)

    async def generate() -> AsyncIterator[dict[str, object]]:
        # Send citations first
        yield {
            "event": "citations",
            "data": json.dumps([c.model_dump() for c in citations]),
        }

        # Stream answer tokens
        answer_parts = []
        for token in answerer.answer_stream(
            request.query,
            ranked_candidates,
            retrieval_label,
            conversation_history=history,
            linked_context=linked_context,
        ):
            answer_parts.append(token)
            yield {"event": "token", "data": token}

        # Save full answer to conversation
        full_answer = "".join(answer_parts)
        conversation_store.add_message(conversation_id, "user", request.query)
        conversation_store.add_message(conversation_id, "assistant", full_answer)

        # Log query
        latency_ms = (time.time() - start_time) * 1000
        query_logger.log_query(
            query=request.query,
            conversation_id=conversation_id,
            retrieval_label=retrieval_label,
            citations=citations,
            latency_ms=latency_ms,
        )

        # Send done event
        yield {
            "event": "done",
            "data": json.dumps(
                {
                    "conversation_id": conversation_id,
                    "retrieval_label": retrieval_label.value,
                }
            ),
        }

    return EventSourceResponse(generate())
