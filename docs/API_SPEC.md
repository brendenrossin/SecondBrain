# API Spec (Draft)

Base: `/api/v1`

## 1) Auth
POC: none (localhost only)

V1+: token/session-based auth with passkeys/OIDC.

---

## 2) Query
### POST `/query`
Request:
```json
{
  "q": "What are the engagement ring constraints?",
  "top_k": 10,
  "filters": {
    "path_prefix": "Reference/",
    "tags": ["engagement-ring"],
    "type": "spec"
  },
  "mode": "hybrid",
  "include_synthesis": false
}
```

Response:
```json
{
  "results": [
    {
      "score": 0.87,
      "note_title": "Engagement Ring Spec",
      "note_path": "Reference/Engagement Ring Spec.md",
      "heading_path": "Requirements > Constraints",
      "snippet": "Avoid X-crossing cathedral arms ... hidden halo ...",
      "citations": [
        {"note_path":"Reference/Engagement Ring Spec.md","chunk_id":"...","heading_path":"Requirements > Constraints"}
      ]
    }
  ]
}
```

---

## 3) Related notes
### GET `/notes/{note_id}/related?top_k=20`
Returns semantically related notes + reasons (shared entities, similarity).

---

## 4) Suggestions report (write-back preflight)
### POST `/suggestions`
Request:
```json
{
  "scope": {"path_prefix":"Reference/"},
  "suggest_links": true,
  "suggest_tags": true
}
```

Response: list of suggested edits with confidence.

---

## 5) Apply changeset (V2+)
### POST `/changesets/apply`
Requires elevated scope.
- Applies link/tag edits to Markdown files
- Creates backup + optional git commit

---

## 6) Ask (conversational RAG)
### POST `/ask`
Chat-style endpoint with LLM synthesis and conversation history.

Request:
```json
{
  "query": "What did I decide about the engagement ring prongs?",
  "conversation_id": "optional-uuid",
  "top_n": 5
}
```

Response:
```json
{
  "answer": "Based on your notes, you decided...",
  "conversation_id": "uuid",
  "citations": [
    {
      "note_path": "Reference/Engagement Ring Spec.md",
      "note_title": "Engagement Ring Spec",
      "heading_path": ["Requirements", "Prong Style"],
      "chunk_id": "abc123",
      "snippet": "Decided on 4-prong cathedral setting...",
      "similarity_score": 0.89,
      "rerank_score": 8.5
    }
  ],
  "retrieval_label": "PASS"
}
```

### POST `/ask/stream`
Streaming variant using Server-Sent Events (SSE).

Events:
- `citation`: Sent first with all citations
- `token`: Streamed answer tokens
- `done`: Final metadata (retrieval_label, conversation_id)

---

## 7) Health & ops
### GET `/health`
### GET `/metrics` (prometheus style)
