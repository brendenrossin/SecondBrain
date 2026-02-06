"""Gradio UI for SecondBrain chat interface."""

import time
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any, TypedDict

import gradio as gr

from secondbrain.api.dependencies import (
    check_and_reindex,
    get_answerer,
    get_conversation_store,
    get_index_tracker,
    get_lexical_store,
    get_local_answerer,
    get_local_reranker,
    get_query_logger,
    get_reranker,
    get_retriever,
    get_vector_store,
)
from secondbrain.config import get_settings
from secondbrain.models import Citation
from secondbrain.retrieval.reranker import LLMReranker
from secondbrain.synthesis.answerer import Answerer


class _Provider(TypedDict):
    reranker: LLMReranker
    answerer: Answerer


@dataclass
class LatencyMetrics:
    """Track latency metrics for a conversation."""

    retrieval_times: list[float] = field(default_factory=list)
    rerank_times: list[float] = field(default_factory=list)
    generation_times: list[float] = field(default_factory=list)

    def add(self, retrieval_ms: float, rerank_ms: float, generation_ms: float) -> None:
        """Add timing for a query."""
        self.retrieval_times.append(retrieval_ms)
        self.rerank_times.append(rerank_ms)
        self.generation_times.append(generation_ms)

    def format_display(self) -> str:
        """Format metrics for display."""
        if not self.retrieval_times:
            return ""

        n = len(self.retrieval_times)
        avg_ret = sum(self.retrieval_times) / n
        avg_rerank = sum(self.rerank_times) / n
        avg_gen = sum(self.generation_times) / n
        total = avg_ret + avg_rerank + avg_gen

        # Get last query times
        last_ret = self.retrieval_times[-1]
        last_rerank = self.rerank_times[-1]
        last_gen = self.generation_times[-1]
        last_total = last_ret + last_rerank + last_gen

        return f"""
---
**Performance ({n} queries)**

| Step | Last | Avg |
|------|------|-----|
| Retrieval | {last_ret:.0f}ms | {avg_ret:.0f}ms |
| Reranking | {last_rerank:.0f}ms | {avg_rerank:.0f}ms |
| Generation | {last_gen:.0f}ms | {avg_gen:.0f}ms |
| **Total** | **{last_total:.0f}ms** | **{total:.0f}ms** |
"""


def format_citations(citations: list[Citation]) -> str:
    """Format citations for display in the UI."""
    if not citations:
        return "No sources found."

    parts = []
    for i, c in enumerate(citations, 1):
        heading = " > ".join(c.heading_path) if c.heading_path else "Top level"
        parts.append(f"""
### [{i}] {c.note_title}

**Path:** `{c.note_path}`
**Section:** {heading}
**Similarity:** {c.similarity_score:.2f} | **Rerank:** {c.rerank_score:.1f}/10

> {c.snippet}
""")
    return "\n---\n".join(parts)


MOBILE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* Apply Inter font globally */
.gradio-container, .gradio-container * {
    font-family: 'Inter', sans-serif !important;
}

/* Remove excess padding on mobile */
.gradio-container {
    padding: 0 !important;
    max-width: 100% !important;
}

/* Desktop: constrain width and center */
@media (min-width: 768px) {
    .gradio-container {
        max-width: 900px !important;
        margin: 0 auto !important;
    }
}

/* Compact header */
.gradio-container h2 {
    margin: 8px 16px !important;
    font-size: 1.3rem !important;
}

/* Chatbot fills available space */
.chat-panel {
    flex-grow: 1 !important;
    min-height: 200px !important;
}

/* Touch-friendly accordion targets (44px min per Apple HIG) */
.gradio-accordion > button {
    min-height: 44px !important;
    font-size: 1rem !important;
}

/* Sticky input at bottom */
.input-row {
    position: sticky !important;
    bottom: 0 !important;
    background: var(--background-fill-primary) !important;
    padding: 8px !important;
    z-index: 10 !important;
}
"""


def get_index_status() -> str:
    """Get formatted index status for the admin panel."""
    vector_count = get_vector_store().count()
    lexical_count = get_lexical_store().count()
    tracker_stats = get_index_tracker().get_stats()

    last_indexed = tracker_stats["last_indexed_at"] or "Never"
    # Trim ISO seconds fraction for readability
    if isinstance(last_indexed, str) and "." in last_indexed:
        last_indexed = last_indexed.split(".")[0].replace("T", " ")

    return (
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Vector chunks | {vector_count} |\n"
        f"| Lexical chunks | {lexical_count} |\n"
        f"| Tracked files | {tracker_stats['file_count']} |\n"
        f"| Tracker chunks | {tracker_stats['total_chunks']} |\n"
        f"| Last indexed | {last_indexed} |"
    )



def create_ui() -> "gr.Blocks":
    """Create the Gradio UI."""
    # Get shared instances
    retriever = get_retriever()
    conversation_store = get_conversation_store()
    query_logger = get_query_logger()

    # Provider instances: local (Ollama) and API (OpenAI)
    providers: dict[str, _Provider] = {
        "Local (Ollama)": {
            "reranker": get_local_reranker(),
            "answerer": get_local_answerer(),
        },
        "OpenAI API": {
            "reranker": get_reranker(),
            "answerer": get_answerer(),
        },
    }

    # Note: Embedding model lazy-loads on first query to avoid startup hangs
    print("SecondBrain UI starting (embedding model will load on first query)...")

    def chat_stream(
        message: str,
        history: list[dict[str, str]],
        conversation_id: str | None,
        metrics: LatencyMetrics | None,
        provider_name: str,
    ) -> Generator[
        tuple[list[dict[str, str]], str | None, list[Citation], str, LatencyMetrics, str], None, None
    ]:
        """Process a chat message with streaming response."""
        start_time = time.time()

        # Select provider
        provider = providers.get(provider_name, providers["Local (Ollama)"])
        reranker = provider["reranker"]
        answerer = provider["answerer"]

        # Initialize metrics if needed
        if metrics is None:
            metrics = LatencyMetrics()

        # Add user message immediately
        history = history.copy()
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": ""})

        # Show searching status
        yield (
            history,
            conversation_id,
            [],
            f"**Searching your notes...** ({provider_name})",
            metrics,
            metrics.format_display(),
        )

        # Get or create conversation
        conv_id = conversation_store.get_or_create_conversation(conversation_id)

        # Get conversation history for context
        conv_history = conversation_store.get_recent_messages(conv_id, limit=10)

        # Retrieve candidates
        t0 = time.time()
        candidates = retriever.retrieve(message, top_k=10)
        retrieval_ms = (time.time() - t0) * 1000
        print(f"[TIMING] Retrieval: {retrieval_ms:.0f}ms", flush=True)

        yield history, conv_id, [], f"**Reranking results...** ({provider_name})", metrics, metrics.format_display()

        # Rerank
        t0 = time.time()
        ranked_candidates, retrieval_label = reranker.rerank(message, candidates, top_n=5)
        rerank_ms = (time.time() - t0) * 1000
        print(f"[TIMING] Reranking: {rerank_ms:.0f}ms", flush=True)

        # Build citations
        citations = [
            Citation(
                note_path=rc.candidate.note_path,
                note_title=rc.candidate.note_title,
                heading_path=rc.candidate.heading_path,
                chunk_id=rc.candidate.chunk_id,
                snippet=rc.candidate.chunk_text[:300] + "..."
                if len(rc.candidate.chunk_text) > 300
                else rc.candidate.chunk_text,
                similarity_score=rc.candidate.similarity_score,
                rerank_score=rc.rerank_score,
            )
            for rc in ranked_candidates
        ]

        # Format citations for display (without metrics yet)
        citations_display = format_citations(citations)
        label_info = f"\n\n**Retrieval Status:** `{retrieval_label.value}`"

        # Show sources while generating
        yield history, conv_id, citations, citations_display + label_info, metrics, metrics.format_display()

        # Stream the answer
        t0 = time.time()
        answer_text = ""
        for token in answerer.answer_stream(
            message,
            ranked_candidates,
            retrieval_label,
            conversation_history=conv_history,
        ):
            answer_text += token
            history[-1]["content"] = answer_text
            yield history, conv_id, citations, citations_display + label_info, metrics, metrics.format_display()

        generation_ms = (time.time() - t0) * 1000
        print(f"[TIMING] Answer generation: {generation_ms:.0f}ms", flush=True)

        # Update metrics
        metrics.add(retrieval_ms, rerank_ms, generation_ms)

        # Save to conversation
        conversation_store.add_message(conv_id, "user", message)
        conversation_store.add_message(conv_id, "assistant", answer_text)

        # Log query
        latency_ms = (time.time() - start_time) * 1000
        query_logger.log_query(
            query=message,
            conversation_id=conv_id,
            retrieval_label=retrieval_label,
            citations=citations,
            latency_ms=latency_ms,
        )

        # Final yield — performance goes to admin panel, not sources
        yield history, conv_id, citations, citations_display + label_info, metrics, metrics.format_display()

    def clear_chat() -> tuple[list[dict[str, str]], None, list[Any], str, LatencyMetrics, str]:
        """Clear the chat and start a new conversation."""
        return [], None, [], "Start a conversation to see sources.", LatencyMetrics(), ""

    def check_reindex_periodic() -> tuple[str, str]:
        """Hourly timer callback: check for trigger file, reindex if needed."""
        msg = check_and_reindex()
        if msg:
            print(f"[TIMER REINDEX] {msg}", flush=True)
            return get_index_status(), msg
        return get_index_status(), ""

    # Build UI
    with gr.Blocks(
        title="SecondBrain",
        fill_height=True,
    ) as demo:
        # State must be defined inside Blocks context in Gradio 6.x
        current_conversation_id = gr.State(None)
        current_citations = gr.State([])
        current_metrics = gr.State(LatencyMetrics())

        reindex_timer = gr.Timer(value=3600, active=True)  # Check every hour

        gr.Markdown("## SecondBrain")

        chatbot = gr.Chatbot(
            show_label=False,
            height=None,
            scale=1,
            min_height=200,
            placeholder="Ask anything about your vault...",
            elem_classes=["chat-panel"],
        )

        with gr.Accordion("Settings", open=False):
            model_provider = gr.Radio(
                choices=["Local (Ollama)", "OpenAI API"],
                value="OpenAI API",
                label="Model Provider",
                interactive=True,
            )
            clear_btn = gr.Button("New Conversation", size="sm")

        with gr.Accordion("Sources", open=False):
            sources_display = gr.Markdown(
                value="Start a conversation to see sources.",
                elem_classes=["sources-panel"],
            )

        with gr.Accordion("Admin", open=False):
            admin_stats = gr.Markdown(value=get_index_status())
            admin_perf = gr.Markdown(value="")
            refresh_btn = gr.Button("Refresh Stats", size="sm")

        msg = gr.Textbox(
            show_label=False,
            placeholder="Ask anything...",
            lines=1,
            max_lines=4,
            submit_btn=True,
            autofocus=True,
            elem_classes=["input-row"],
        )

        # Event handlers
        msg.submit(
            chat_stream,
            inputs=[msg, chatbot, current_conversation_id, current_metrics, model_provider],
            outputs=[
                chatbot,
                current_conversation_id,
                current_citations,
                sources_display,
                current_metrics,
                admin_perf,
            ],
        ).then(
            lambda: "",
            outputs=[msg],
        )

        clear_btn.click(
            clear_chat,
            outputs=[
                chatbot,
                current_conversation_id,
                current_citations,
                sources_display,
                current_metrics,
                admin_perf,
            ],
        )

        # Admin panel handler
        refresh_btn.click(
            get_index_status,
            outputs=[admin_stats],
        )

        # Periodic reindex check (picks up daily_sync trigger file)
        reindex_timer.tick(
            check_reindex_periodic,
            outputs=[admin_stats, admin_perf],
        )

    return demo  # type: ignore[no-any-return]


def main() -> None:
    """Run the Gradio UI."""
    settings = get_settings()

    # Check if vault is configured
    if not settings.vault_path:
        print("WARNING: SECONDBRAIN_VAULT_PATH not set. Set it before indexing.")
        print("Example: export SECONDBRAIN_VAULT_PATH=/path/to/your/vault")
    else:
        print(f"Vault path: {settings.vault_path}")

    # Reindex at startup (outside Gradio thread pool) if trigger file exists
    reindex_msg = check_and_reindex()
    if reindex_msg:
        print(f"[REINDEX] {reindex_msg}")
    else:
        print("No pending reindex.")

    demo = create_ui()
    demo.launch(
        server_name=settings.host,
        server_port=settings.gradio_port,
        share=False,
        pwa=True,
        css=MOBILE_CSS,
        theme=gr.themes.Soft(),
        favicon_path="assets/favicon.png",
    )


if __name__ == "__main__":
    main()
