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

## 6) Health & ops
### GET `/health`
### GET `/metrics` (prometheus style)
