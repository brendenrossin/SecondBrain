---
id: '003'
title: Repo UI plist matches the installed Next.js service
project: second-brain
tier: quick
status: Approved
version: 0.1.0
created: '2026-11-22'
updated: '2026-11-22'
tags: []
history:
- status: Draft
  date: '2026-11-22'
  note: created
- status: Approved
  date: '2026-11-22'
  note: gate passed
---
# 003 — Repo UI plist matches the installed Next.js service

## Intent
The repo copy of `com.secondbrain.ui.plist` still launches the deprecated Gradio UI
(`uv run python -m secondbrain.ui` from the repo root). The installed copy in
`~/Library/LaunchAgents/` runs the Next.js production build: `/opt/homebrew/bin/npm run start` with
`WorkingDirectory` `frontend/` and `ThrottleInterval` 10. `make install-ui-service` copies the repo
file over the installed one, so running it today would silently swap Mission Control for Gradio.
The other three plists (api, daily-sync, langfuse) already match their installed copies byte for
byte. Fixed means:
- the repo plist is byte-identical to the installed one;
- a test pins what the repo plist launches, so it can't drift back;
- `make ui` no longer starts Gradio.

`frontend/package.json` `start` is `next start -p 7860 -H 127.0.0.1`, so the port and bind live
there, not in the plist.

## Acceptance Criteria
```gherkin
Feature: The repo UI plist launches the Next.js production server

  Scenario: Repo plist launches npm start in frontend/
    Given the repo file com.secondbrain.ui.plist
    When it is parsed with plistlib
    Then Label is "com.secondbrain.ui"
    And ProgramArguments is ["/opt/homebrew/bin/npm", "run", "start"]
    And WorkingDirectory is the repo root joined with "frontend"
    And RunAtLoad is true, KeepAlive is true and ThrottleInterval is 10
    And StandardOutPath and StandardErrorPath are under the repo's data/logs/ directory

  Scenario: Repo plist no longer launches Gradio
    Given the repo file com.secondbrain.ui.plist
    When its ProgramArguments are read
    Then none of them is "secondbrain.ui"
    And none of them ends in "/uv"

  Scenario: The frontend start script binds loopback on port 7860
    Given frontend/package.json
    When its "start" script is read
    Then it is "next start -p 7860 -H 127.0.0.1"

  Scenario: make ui runs the Next.js frontend, not Gradio
    Given the Makefile
    When the recipe for the "ui" target is read
    Then it does not contain "secondbrain.ui"
    And it runs "npm run start" in frontend/

  Scenario: Repo and installed copies match after the fix (manual check, not a test)
    Given the fix is merged
    When "diff com.secondbrain.ui.plist ~/Library/LaunchAgents/com.secondbrain.ui.plist" runs
    Then it prints nothing and exits 0
```

The last scenario is a one-off manual check. The test suite never reads `~/Library/LaunchAgents/`.

## Files
| File | Action | Note |
|---|---|---|
| `com.secondbrain.ui.plist` | Update | Replace it with the installed Next.js copy (npm start, `frontend/`, ThrottleInterval 10). |
| `Makefile` | Update | `ui:` runs `cd frontend && npm run start`; fix the "Run Gradio UI" comment. |
| `tests/test_launchd_plists.py` | New | The four scenarios above, using plistlib in the same style as `tests/test_langfuse_start.py`. |
| `CLAUDE.md` | Update | The `make ui` line says it runs the Next.js frontend (port 7860), not Gradio. |
