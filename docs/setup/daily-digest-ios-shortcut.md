# Daily Digest — iOS Shortcut Setup

A one-time, on-device automation that fires a native iPhone notification each
morning with your SecondBrain digest. Fully local-first: your phone calls your
Mac over Tailscale — nothing routes through Apple/Google/cloud push servers.

## Prerequisites

- iPhone on the same Tailscale tailnet as the Mac Studio running SecondBrain.
- The API reachable over Tailscale, e.g. `http://<tailscale-name>:8000`.
  Verify from the phone's browser: `http://<tailscale-name>:8000/api/v1/digest`
  should return JSON like `{"title": "SecondBrain · Aug 2", "body": "3 overdue · 2 due today", "count": 5}`.

## Build the Shortcut (automation)

Shortcuts app → **Automation** tab → **+** → **Create Personal Automation**.

1. **Trigger:** *Time of Day* → pick your time (e.g. 8:00 AM) → *Daily*. Turn
   **Run Immediately** on (so it fires without a confirmation tap).
2. **Get Contents of URL** — `http://<tailscale-name>:8000/api/v1/digest`
   (Method: GET).
3. **Get Dictionary Value** — Key `count` from the previous step. Store as a
   variable (e.g. `Count`).
4. **If** `Count` *is greater than* `0`:
   - **Get Dictionary Value** — Key `title` → variable `Title`.
   - **Get Dictionary Value** — Key `body` → variable `Body`.
   - **Show Notification** — Title = `Title`, Body = `Body`.
   - *(Otherwise: do nothing — stays quiet on all-clear days.)*

## Notes

- **Quiet by design:** the endpoint returns `count: 0` with an all-clear body
  when nothing needs attention; the `If count > 0` gate means no notification
  fires on those days.
- **Tailscale down / Mac asleep:** the fetch fails silently and no notification
  shows — not fatal. (The API launchd service uses `caffeinate -ims` to keep the
  Mac awake; see CLAUDE.md.)
- **Future sections:** when ENGAGE-2 (resurfacing) and FEED-1 (content feed)
  land, they fold into the same `body` one-liner automatically — no Shortcut
  changes needed.
