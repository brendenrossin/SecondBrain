"""CLI entry point for RAG evaluation: python -m secondbrain.eval"""

import sys
from pathlib import Path

from secondbrain.api.dependencies import (
    get_embedder,
    get_lexical_store,
    get_retriever,
    get_settings,
    get_vector_store,
)
from secondbrain.eval.eval_harness import RAGEvaluator, load_queries, print_report, save_report


def main() -> None:
    settings = get_settings()
    data_path = Path(settings.data_path)

    # Load eval queries
    queries_path = Path(__file__).parent / "eval_queries.yaml"
    if not queries_path.exists():
        print(f"Error: eval queries not found at {queries_path}", file=sys.stderr)
        sys.exit(1)

    # Check that stores have data
    vector_store = get_vector_store()
    chunk_count = vector_store.count()
    if chunk_count == 0:
        print("Error: vector store is empty. Run 'make reindex' first.", file=sys.stderr)
        sys.exit(1)

    print(f"Vector store has {chunk_count} chunks")
    print(f"Lexical store has {get_lexical_store().count()} chunks")

    queries = load_queries(queries_path)
    print(f"Loaded {len(queries)} eval queries")

    retriever = get_retriever()
    embedder = get_embedder()
    model_name = embedder.model_name

    evaluator = RAGEvaluator(retriever, top_k=10)
    report = evaluator.run(queries, model_name=model_name)

    print_report(report)

    output_dir = data_path / "eval"
    saved_path = save_report(report, output_dir)
    print(f"Report saved to {saved_path}")


if __name__ == "__main__":
    main()
