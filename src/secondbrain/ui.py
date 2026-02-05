"""Gradio UI for SecondBrain chat interface."""

import time

import gradio as gr

from secondbrain.api.dependencies import (
    get_answerer,
    get_conversation_store,
    get_query_logger,
    get_reranker,
    get_retriever,
)
from secondbrain.config import get_settings
from secondbrain.models import Citation


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


def create_ui() -> "gr.Blocks":
    """Create the Gradio UI."""
    # Get shared instances
    retriever = get_retriever()
    reranker = get_reranker()
    answerer = get_answerer()
    conversation_store = get_conversation_store()
    query_logger = get_query_logger()

    # State for current conversation and citations
    current_conversation_id = gr.State(None)
    current_citations = gr.State([])

    def chat(
        message: str,
        history: list[tuple[str, str]],
        conversation_id: str | None,
    ) -> tuple[list[tuple[str, str]], str | None, list[Citation], str]:
        """Process a chat message and return response with citations."""
        start_time = time.time()

        # Get or create conversation
        conv_id = conversation_store.get_or_create_conversation(conversation_id)

        # Get conversation history for context
        conv_history = conversation_store.get_recent_messages(conv_id, limit=10)

        # Retrieve candidates
        candidates = retriever.retrieve(message, top_k=10)

        # Rerank
        ranked_candidates, retrieval_label = reranker.rerank(
            message, candidates, top_n=5
        )

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

        # Generate answer
        answer = answerer.answer(
            message,
            ranked_candidates,
            retrieval_label,
            conversation_history=conv_history,
        )

        # Save to conversation
        conversation_store.add_message(conv_id, "user", message)
        conversation_store.add_message(conv_id, "assistant", answer)

        # Log query
        latency_ms = (time.time() - start_time) * 1000
        query_logger.log_query(
            query=message,
            conversation_id=conv_id,
            retrieval_label=retrieval_label,
            citations=citations,
            latency_ms=latency_ms,
        )

        # Update history
        history.append((message, answer))

        # Format citations for display
        citations_display = format_citations(citations)

        # Add retrieval label info
        label_info = f"\n\n**Retrieval Status:** `{retrieval_label.value}`"
        citations_display = citations_display + label_info

        return history, conv_id, citations, citations_display

    def clear_chat() -> tuple[list[tuple[str, str]], None, list[Citation], str]:
        """Clear the chat and start a new conversation."""
        return [], None, [], "Start a conversation to see sources."

    # Build UI
    with gr.Blocks(
        title="SecondBrain",
        theme=gr.themes.Soft(),
        css="""
        .sources-panel { max-height: 600px; overflow-y: auto; }
        .chat-panel { min-height: 500px; }
        """,
    ) as demo:
        gr.Markdown("# SecondBrain")
        gr.Markdown("Ask questions about your Obsidian vault")

        with gr.Row():
            # Left column: Chat
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    label="Chat",
                    height=500,
                    elem_classes=["chat-panel"],
                )
                with gr.Row():
                    msg = gr.Textbox(
                        label="Your question",
                        placeholder="What did I decide about...?",
                        scale=4,
                        lines=2,
                    )
                    submit_btn = gr.Button("Ask", variant="primary", scale=1)

                with gr.Row():
                    clear_btn = gr.Button("New Conversation", size="sm")

            # Right column: Sources
            with gr.Column(scale=2), gr.Accordion("Sources", open=True):
                sources_display = gr.Markdown(
                    value="Start a conversation to see sources.",
                    elem_classes=["sources-panel"],
                )

        # Event handlers
        submit_btn.click(
            chat,
            inputs=[msg, chatbot, current_conversation_id],
            outputs=[chatbot, current_conversation_id, current_citations, sources_display],
        ).then(
            lambda: "",
            outputs=[msg],
        )

        msg.submit(
            chat,
            inputs=[msg, chatbot, current_conversation_id],
            outputs=[chatbot, current_conversation_id, current_citations, sources_display],
        ).then(
            lambda: "",
            outputs=[msg],
        )

        clear_btn.click(
            clear_chat,
            outputs=[chatbot, current_conversation_id, current_citations, sources_display],
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

    demo = create_ui()
    demo.launch(
        server_name=settings.host,
        server_port=settings.gradio_port,
        share=False,
    )


if __name__ == "__main__":
    main()
