# Data Model

## 1) Entities (conceptual)
### Note
- `note_id` (stable hash of vault-relative path)
- `path`, `title`
- `frontmatter` (YAML JSON)
- `created_at`, `updated_at`
- `explicit_links` (parsed `[[...]]`)
- `tags` (parsed `#tag` + frontmatter tags)

### Chunk
- `chunk_id` (stable)
- `note_id`
- `heading_path` (e.g., `Engagement Ring > Constraints`)
- `start_offset`, `end_offset` (optional)
- `text`
- `embedding` (vector ref)
- `checksum` (for change detection)

### Extraction (metadata)
- `chunk_id`
- `summary`
- `key_phrases`
- `entities` (list with type + confidence)
- `dates` (normalized, with confidence)
- `action_items` (text + confidence)
- `provenance` (model/version + prompt hash)

### Graph (optional)
**Node types**
- `Note`, `Chunk`, `Entity`, `Concept`

**Edge types**
- `MENTIONS` (Chunk → Entity)
- `IN_NOTE` (Chunk → Note)
- `RELATED` (Entity ↔ Entity or Note ↔ Note)
- `CONSTRAINS` (Entity/Concept → Concept)
- `DECIDED` (Note/Chunk → Concept)
- `NEXT_STEP` (Chunk → ActionItem)

## 2) Practical KG strategy
Start with the simplest, highest-signal edges:
- explicit `[[links]]` as Note↔Note edges
- entity mentions from extraction
- similarity edges from embedding neighbors (thresholded and capped)
- co-occurrence edges for entities within same note section

Avoid early:
- open-ended “relation extraction” that hallucinates edges
- deep ontologies

## 3) Stable IDs
### Note ID
`note_id = sha256(vault_id + relative_path)`

### Chunk ID
`chunk_id = sha256(note_id + heading_path + normalized_block_text)`  
or  
`chunk_id = sha256(note_id + start_end_offsets)` (if you keep stable offsets)

Key requirement: if you edit a sentence, you shouldn't invalidate the entire note.

## 4) Frontmatter conventions (optional but recommended)
Encourage lightweight frontmatter that helps retrieval:
```yaml
---
type: spec|meeting|daily|idea|reference
topics: [engagement-ring, jewelry, shopping]
status: active|done|parking-lot
---
```

Never require it; auto-extraction should work without it.

## 5) Example: engagement ring “spec page”
Create a canonical note:
- `Reference/Engagement Ring Spec.md`
with sections:
- Requirements
- Constraints (must/avoid)
- Open questions
- Vendors
- Timeline

The system can help build/maintain this page via suggestions and synthesis.
