# Operations & Observability

## 1) Environments
- dev: local-only
- staging: optional (mirror of prod config)
- prod: whichever deployment mode you choose

## 2) Observability
### Logs
- structured JSON logs
- request_id correlation
- do not log raw note bodies

### Metrics
- indexing duration, files processed
- chunks indexed, embeddings generated
- query latency p50/p95
- error rates by endpoint

### Tracing (optional)
- OpenTelemetry spans:
  - ingest.parse
  - chunk
  - embed
  - bm25.search
  - vector.search
  - rerank
  - synthesize

## 3) Backups
- Vault: primary backups (Time Machine + optional encrypted cloud)
- DB: daily encrypted snapshots
- Test restore monthly

## 4) Runbooks
- Full reindex from scratch
- Recover from corrupted DB
- Rotate API keys
- Disable remote access quickly

## 5) Release process
- semantic versioning
- migrations for DB schema
- canary indexing run before enabling watchers

## 6) Performance tuning knobs
- chunk size targets
- K_lex/K_vec
- rerank top N
- caching embeddings
