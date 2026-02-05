# Security & Privacy

## 1) Threat model (what can go wrong)
### Assets to protect
- Raw note content (high sensitivity)
- Derived artifacts: embeddings, summaries, entities
- Auth tokens/session cookies
- API keys for hosted models
- Audit logs (may include sensitive queries)

### Adversaries
- Opportunistic internet scanners (if you expose services)
- Account takeover (phishing/credential reuse)
- Malware on local machine
- Supply chain (deps/plugins)
- Data exfil via hosted LLM calls

## 2) Core security posture
- **Local-first by default**
- No public internet exposure in POC
- Remote access only behind VPN/tunnel + strong auth
- Minimal data sent to external model providers; explicit opt-in

## 3) Security requirements
### Authentication & authorization
- Prefer passkeys / WebAuthn for web UI
- Support TOTP backup if needed
- Session expiration + rotation
- Authorization:
  - read-only endpoints default
  - write-back endpoints require explicit elevated scope

### Network security
- Bind local services to `127.0.0.1` by default
- If remote:
  - VPN (Tailscale/WireGuard) OR Cloudflare Zero Trust
  - No open ports on router
- Rate limiting on all endpoints
- IP allowlist optional

### Data encryption
- At rest:
  - Disk encryption on Mac
  - If server DB: encrypted volume (or Postgres at rest encryption via disk)
- In transit:
  - TLS everywhere for remote access
- Secrets:
  - OS keychain / dotenv not committed
  - rotate keys easily

### Logging and privacy
- Avoid logging raw note content
- Log request IDs, timing, and high-level outcomes
- Audit log for remote queries (timestamp + user + endpoint), but redact sensitive text where possible

### External model safety
- Clear “modes”:
  - Local-only mode (no external calls)
  - Hosted-LLM mode (explicit)
- When using hosted LLMs:
  - send only retrieved chunks, not entire vault
  - minimize context
  - optionally strip PII (configurable)
- Cache embeddings locally to avoid repeated uploads

## 4) Secure write-back strategy
Never auto-edit notes.
Use a “changeset” workflow:
1. generate suggestions (links/tags)
2. present diff
3. user approves
4. apply changes
5. commit to git (optional) for rollback

## 5) Deployment hardening checklist (V1+)
- [ ] TLS termination (tunnel provider or reverse proxy)
- [ ] Strong auth (passkeys) + CSRF protection
- [ ] Rate limits + WAF/tunnel rules
- [ ] No directory listing; no vault path exposure
- [ ] Dependency scanning (pip-audit / osv)
- [ ] Backups encrypted + tested restore

## 6) Data retention & backups
- Vault remains source of truth; back up via:
  - Time Machine / local snapshots
  - encrypted cloud backup (optional)
- Indexes can be rebuilt; still back up DB for convenience
- Keep a “rebuild from scratch” runbook

## 7) Secure mobile access patterns
### Best: VPN
- Phone joins private network; query service remains private

### Good: Zero-trust tunnel
- Cloudflare Access / similar, with device posture checks

### Avoid early: Public endpoints
- High risk, higher complexity
