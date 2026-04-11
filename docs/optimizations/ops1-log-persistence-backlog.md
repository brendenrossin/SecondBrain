# OPS-1 Log Persistence — Optimization Backlog

| # | Severity | Confidence | Finding | Suggested Fix |
|---|----------|------------|---------|---------------|
| 1 | Low | Medium (2/3) | `prune_old_usage()` doesn't guard against negative `retention_days` | Add `retention_days = max(1, retention_days)` at method start |
| 2 | Medium | Low (1/3) | No Makefile target to install newsyslog config (requires sudo) | Add `install-newsyslog` target: `sudo cp etc/newsyslog.d/secondbrain.conf /etc/newsyslog.d/` |
| 3 | Low | Low (1/3) | No test for `retention_days=0` edge case | Add test verifying all records are deleted when retention is 0 |
