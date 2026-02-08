# Voice Chat — OpenAI Realtime API Integration

> **Status:** Planned
> **Estimated effort:** ~2-3 weeks
> **Depends on:** Phase 3.5 (Next.js frontend, done), Phase 4 (Tailscale remote access, done)

## Problem

The current chat interface is text-only. For hands-free use cases — walking, driving, cooking, or just preferring conversation over typing — there's no way to interact with the knowledge base by voice. The user currently dictates via a third-party tool (Wispr Flow) and then manually submits text, which adds friction and breaks the conversational flow.

## Proposed Solution

Add an optional voice mode to the existing chat interface using the **OpenAI Realtime API** with **server-side Voice Activity Detection (VAD)**. The voice mode is activated by a microphone button — text input remains the default. Voice conversations produce the same grounded, citation-backed answers as text chat, with the model calling a `search_knowledge_base` tool to query the RAG pipeline.

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **OpenAI Realtime API (not Whisper + TTS)** | True speech-to-speech with sub-second latency. No roundtrip through STT → LLM → TTS. Server VAD handles turn-taking naturally. |
| **`gpt-realtime-mini` model** | Newer GA model (Dec 2025) with 18.6pp better instruction following and 12.9pp better tool calling vs prior snapshots. ~60-80% cheaper than full `gpt-realtime`. Audio input: $10/1M tokens, output: $20/1M tokens. |
| **Browser audio I/O (not PyAudio)** | `navigator.mediaDevices.getUserMedia` and Web Audio API work on all platforms (Mac, iPhone, iPad) without native dependencies. Audio routes to whatever output device is active (speakers, AirPods). |
| **Backend WebSocket relay** | API key stays server-side. Backend intercepts tool calls to run RAG locally. Single secure endpoint. |
| **Server VAD (not push-to-talk)** | More natural conversation flow. The server detects speech start/stop. Push-to-talk can be added as a fallback option later. |
| **User interrupt / barge-in** | Audio from the Realtime API arrives faster than real-time and queues for playback. When user speech is detected, the frontend flushes the playback queue immediately. If the model response is still in progress, a `response.cancel` is sent to stop generation. |
| **Opt-in microphone button** | Text is the default mode. Voice is activated explicitly. No ambient listening. |
| **Logging, not persistence** | All events (transcripts, tool calls, errors) are written to a JSONL log file. This is a personal tool, not a multi-user application — logging is sufficient for debugging and review. |

---

## Architecture

### System Overview

```
Browser (mic/speaker)          FastAPI Backend           OpenAI Realtime API
    |                              |                          |
    |-- WebSocket ------------------->-- WebSocket ----------->|
    |   (PCM audio chunks)         |   (relay + intercept)    |
    |<-----------------------------<--------------------------|
    |   (PCM audio chunks)         |   (relay)                |
    |                              |                          |
    |                              |   <-- function_call:     |
    |                              |   search_knowledge_base  |
    |                              |        |                 |
    |                              |   HybridRetriever +      |
    |                              |   LLMReranker runs       |
    |                              |        |                 |
    |                              |   -- tool result ------->|
    |                              |                          |
    |<-- audio: "Based on         <-- audio response ---------|
    |    your notes from           |                          |
    |    yesterday..."             |                          |
```

### Data Flow

1. User taps the microphone button in the chat UI
2. Browser requests mic permission (`getUserMedia`), opens WebSocket to backend
3. Backend opens a WebSocket to `wss://api.openai.com/v1/realtime?model=gpt-realtime-mini`, sends `session.update` with instructions and tools
4. Browser captures PCM16 audio via AudioWorklet, sends chunks as base64 over WebSocket
5. OpenAI server VAD detects speech boundaries, processes the utterance
6. If the model needs vault data, it emits a `function_call` for `search_knowledge_base`
7. Backend intercepts the tool call, runs `HybridRetriever.retrieve()` → `LLMReranker.rerank()`, formats results
8. Backend sends the tool result back to the Realtime API via `conversation.item.create` + `response.create`
9. The model generates a spoken response grounded in the retrieved notes
10. Audio response streams back through the backend relay to the browser
11. Browser queues PCM16 audio chunks and plays through `AudioContext.destination` (speakers/AirPods)
12. Transcripts (input + output) are displayed in the chat message thread and logged to file

### Session Configuration

```json
{
  "model": "gpt-realtime-mini",
  "modalities": ["text", "audio"],
  "voice": "alloy",
  "input_audio_format": "pcm16",
  "output_audio_format": "pcm16",
  "input_audio_transcription": {
    "model": "whisper-1"
  },
  "turn_detection": {
    "type": "server_vad",
    "threshold": 0.5,
    "prefix_padding_ms": 300,
    "silence_duration_ms": 500
  },
  "instructions": "You are SecondBrain, a helpful voice assistant connected to the user's personal Obsidian knowledge base. Use the search_knowledge_base tool to find relevant notes before answering questions about the user's notes, tasks, projects, or anything in their vault. ONLY use information returned by the tool. If the tool returns no relevant results, say so honestly. Be concise and conversational — this is a voice interface, so keep responses brief and natural. When referencing information, mention which note it came from. Sources include dates and folder context. Use dates to answer temporal queries like 'yesterday', 'this week', 'most recent', etc.",
  "tools": [
    {
      "type": "function",
      "name": "search_knowledge_base",
      "description": "Search the user's Obsidian vault for relevant notes, tasks, projects, and knowledge. Use this tool whenever the user asks about their notes, tasks, schedule, projects, or any personal information stored in their vault.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "Natural language search query derived from the user's spoken request"
          }
        },
        "required": ["query"]
      }
    }
  ]
}
```

---

## User Interrupt / Barge-In Pattern

This is the most critical real-time behavior. The Realtime API generates audio faster than real-time — by the time the user interrupts, most or all of the response audio has already been sent to the client and is sitting in the playback queue. The interrupt pattern must flush this queue instantly so the user doesn't hear stale audio.

### Response State Machine

The frontend tracks the model's response lifecycle:

```
                  response.created
        idle ──────────────────────► in_progress
                                         │
                          ┌──────────────┤
                          │              │
              response.done        speech_started
                          │         (user interrupt)
                          ▼              │
                        done             ▼
                                    interrupted
```

**States:**
- `idle` — no active response, waiting for user input
- `in_progress` — model is generating a response (audio chunks arriving)
- `done` — response completed normally
- `interrupted` — user spoke during response, playback was flushed

### Event Flow: Normal Response

```
Server → input_audio_buffer.speech_started    # User starts speaking
Server → input_audio_buffer.speech_stopped    # User stops speaking
Server → response.created                     # Model starts responding
Server → response.audio.delta (repeated)      # Audio chunks → playback queue
Server → response.audio_transcript.delta      # Transcript tokens → chat UI
Server → response.audio_transcript.done       # Full assistant transcript
Server → response.done                        # Response complete
Server → conversation.item.input_audio_transcription.completed  # User transcript (async)
```

### Event Flow: User Interrupt (Barge-In)

```
Server → response.created                     # Model starts responding
Server → response.audio.delta (repeated)      # Audio chunks → playback queue
  ... user starts speaking mid-response ...
Server → input_audio_buffer.speech_started    # VAD detects user speech
  Client:
    1. Flush the audio playback queue immediately (stop all queued audio)
    2. Note how many milliseconds of audio were actually played
    3. If response state is still `in_progress`:
       - Send `response.cancel` to stop model generation
       - Send `conversation.item.truncate` with `audio_end_ms` set to
         the amount of audio actually played (so the server's transcript
         matches what the user heard)
    4. Set response state to `interrupted`
  ... server processes new user speech as next turn ...
```

### Why `response.cancel` Is Conditional

The Realtime API generates audio faster than real-time. In most cases, by the time the user interrupts, the full response has already been sent (`response.done` already received). In that case, we only need to flush the playback queue — no `response.cancel` needed.

`response.cancel` is only sent when `response.done` has NOT been received yet (the model is still generating). This avoids sending unnecessary cancel events.

### Why `conversation.item.truncate` Matters

The server maintains a transcript of what it believes the user heard. If we don't send `conversation.item.truncate` with the correct `audio_end_ms`, the server's context will include text the user never actually heard, leading to confusing follow-up responses. Truncation keeps the server's state in sync with reality.

### Frontend Audio Queue Implementation

```typescript
// AudioWorklet-based playback with queue tracking
class AudioPlaybackQueue {
  private queue: Float32Array[] = [];
  private totalQueuedMs: number = 0;
  private totalPlayedMs: number = 0;

  // Called when response.audio.delta arrives
  enqueue(pcm16Chunk: ArrayBuffer): void {
    // Decode base64 → PCM16 → Float32, push to queue
    this.totalQueuedMs += chunkDurationMs;
  }

  // Called when speech_started arrives during playback
  flush(): number {
    const playedMs = this.totalPlayedMs;
    this.queue = [];           // Dump all queued audio
    this.stopCurrentSource();  // Stop what's currently playing
    this.totalQueuedMs = 0;
    this.totalPlayedMs = 0;
    return playedMs;           // Return how much was actually played
  }

  // AudioWorklet posts back when chunks finish playing
  onChunkPlayed(durationMs: number): void {
    this.totalPlayedMs += durationMs;
  }
}
```

---

## Backend Implementation

### New WebSocket Endpoint

**`WS /api/v1/voice`**

A WebSocket endpoint that relays audio between the browser and the OpenAI Realtime API, intercepting tool calls to run RAG locally.

```
src/secondbrain/api/voice.py     # WebSocket endpoint + relay logic
```

**Connection lifecycle:**
1. Browser connects to `ws://localhost:8000/api/v1/voice`
2. Backend establishes WebSocket to `wss://api.openai.com/v1/realtime?model=gpt-realtime-mini`
3. Backend sends `session.update` with instructions and tools
4. Two concurrent relay tasks:
   - **Browser → OpenAI**: Forward audio input events (`input_audio_buffer.append`)
   - **OpenAI → Browser**: Forward audio output and transcript events, intercept tool calls
5. On tool call interception:
   - Parse the `search_knowledge_base` query argument
   - Run `HybridRetriever.retrieve()` → `LLMReranker.rerank()`
   - Format top results as context text (same format as `Answerer._build_context()`)
   - Send `conversation.item.create` (tool result) + `response.create` back to OpenAI
6. Forward transcript and state events to browser for display in chat UI
7. On disconnect: close both WebSocket connections

**Events forwarded to browser (for UI updates):**
- `input_audio_buffer.speech_started` — triggers interrupt handling + shows "Listening..."
- `input_audio_buffer.speech_stopped` — shows "Processing..."
- `response.created` — sets response state to `in_progress`
- `response.audio.delta` — audio chunks for playback queue
- `response.audio_transcript.delta` — assistant transcript tokens for chat display
- `response.audio_transcript.done` — full assistant transcript
- `conversation.item.input_audio_transcription.completed` — user's transcribed text for chat display
- `response.function_call_arguments.done` — shows "Searching notes..."
- `response.done` — sets response state to `done`, ready for next turn

**Events from browser (forwarded or handled):**
- `input_audio_buffer.append` — forwarded directly to OpenAI
- `response.cancel` — forwarded to OpenAI (only when response is in_progress)
- `conversation.item.truncate` — forwarded to OpenAI (with audio_end_ms from frontend)

### Tool Call Handler

```python
async def handle_tool_call(
    name: str,
    arguments: dict,
    retriever: HybridRetriever,
    reranker: LLMReranker,
) -> str:
    """Run RAG pipeline for a tool call and return formatted context."""
    query = arguments["query"]
    candidates = retriever.retrieve(query, top_k=10)
    ranked, label = reranker.rerank(query, candidates, top_n=5)

    if not ranked:
        return "No relevant notes found in the vault for this query."

    parts = []
    for i, rc in enumerate(ranked, 1):
        c = rc.candidate
        header = f"[{i}]"
        if c.note_folder:
            header += f" [{c.note_folder}]"
        if c.note_date:
            header += f" ({c.note_date})"
        header += f" {c.note_title}"
        if c.heading_path:
            header += f" > {' > '.join(c.heading_path)}"
        parts.append(f"{header}\n{c.chunk_text}")

    return "\n\n---\n\n".join(parts)
```

### Event Logging

All voice session events are logged to a JSONL file at `data/voice-sessions.log`. Each line is a JSON object with:

```json
{
  "timestamp": "2026-02-08T14:30:00.000Z",
  "session_id": "abc123",
  "event_type": "input_audio_buffer.speech_started",
  "direction": "server",
  "data": { ... }
}
```

**Logged events:**
- Session start/end (with duration)
- All transcript events (user input transcription, assistant audio transcript)
- Tool calls (query, result summary, latency)
- Interrupt events (speech_started during response, audio_end_ms, whether response.cancel was sent)
- Errors (connection failures, tool call failures, API errors)

This provides full observability without needing a database. Log rotation can be handled externally if needed.

---

## Frontend Implementation

### New Components

```
frontend/src/components/chat/VoiceButton.tsx      # Mic toggle button
frontend/src/components/chat/VoiceOverlay.tsx      # Active voice session UI
frontend/src/hooks/useVoiceChat.ts                 # WebSocket + audio + interrupt logic
frontend/src/lib/audio-playback.ts                 # AudioWorklet-based playback queue
```

### VoiceButton

- Positioned next to the send button in `ChatInput`
- Microphone icon (from lucide-react: `Mic` / `MicOff`)
- Click to start voice session, click again to stop
- Visual states:
  - **Idle**: subtle mic icon, matches send button style
  - **Connecting**: pulsing animation
  - **Active/Listening**: accent-colored glow, waveform or pulse animation
  - **Processing**: dimmed with spinner

### VoiceOverlay

- Appears when voice mode is active, overlays the bottom of the chat area
- Shows:
  - Live waveform visualization (from input audio levels)
  - Status text: "Listening...", "Searching your notes...", "Speaking..."
  - Stop button to end the voice session
- Tap anywhere outside the overlay or press stop to end voice mode

### useVoiceChat Hook

Manages the WebSocket connection, audio pipeline, and interrupt handling:

```typescript
interface UseVoiceChatReturn {
  isVoiceActive: boolean;
  voiceStatus: 'idle' | 'connecting' | 'listening' | 'processing' | 'speaking';
  responseState: 'idle' | 'in_progress' | 'done' | 'interrupted';
  startVoice: () => Promise<void>;
  stopVoice: () => void;
}
```

**Audio capture pipeline:**
1. `getUserMedia({ audio: { sampleRate: 24000, channelCount: 1 } })`
2. `AudioWorklet` processor to extract raw PCM16 samples at 24kHz
3. Send PCM16 chunks as base64-encoded `input_audio_buffer.append` events over WebSocket

**Audio playback pipeline:**
1. Receive `response.audio.delta` events with base64-encoded PCM16 audio
2. Decode and enqueue into `AudioPlaybackQueue`
3. `AudioWorklet` plays chunks sequentially, tracking `totalPlayedMs`
4. Play through `AudioContext.destination` (routes to active output: speakers/AirPods)

**Interrupt handling:**
1. On `input_audio_buffer.speech_started`:
   - Call `audioPlaybackQueue.flush()` → returns `playedMs`
   - If `responseState === 'in_progress'`:
     - Send `response.cancel` to backend (relayed to OpenAI)
     - Send `conversation.item.truncate` with `audio_end_ms: playedMs`
   - Set `responseState = 'interrupted'`
2. On `response.created`: set `responseState = 'in_progress'`
3. On `response.done`: set `responseState = 'done'`

### ChatProvider Extensions

Add voice state to the existing ChatProvider:

```typescript
// New state
const [isVoiceActive, setIsVoiceActive] = useState(false);
const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>('idle');

// New context values
voiceStatus: VoiceStatus;
startVoice: () => Promise<void>;
stopVoice: () => void;
```

Voice transcripts are added to the same `messages` array as text messages, keeping one unified conversation thread.

---

## UI/UX Details

### Chat Input Area (Voice Inactive — Default)

```
+--------------------------------------------------+
| Ask a follow-up...                    [Mic] [->] |
+--------------------------------------------------+
```

The mic button sits between the textarea and the send button. Subtle, non-intrusive.

### Chat Input Area (Voice Active)

```
+--------------------------------------------------+
|                                                  |
|         ( ( ( o ) ) )    Listening...            |
|                                                  |
|                [Stop]                            |
+--------------------------------------------------+
```

The input area transforms into a voice overlay with a waveform/pulse animation and status indicator. The text input is temporarily hidden.

### Message Display

Voice messages appear in the same chat thread:

```
YOU (voice)
"What am I bringing to Ryan's Super Bowl party?"

SECONDBRAIN (voice)
"Based on your daily note from February 7th, you're bringing
queso dip and chips to Ryan's Super Bowl party."
(Source: [1])
```

A small speaker/mic icon badge distinguishes voice messages from typed ones, but they're otherwise identical in styling.

### Status Indicators During Tool Use

When the model calls `search_knowledge_base`:
- Voice overlay shows: "Searching your notes..."
- The model may also say "Let me check your notes..." before the tool call completes (natural conversational filler, configured via session instructions)

---

## Platform Compatibility

| Platform | Mic Input | Audio Output | WebSocket | Notes |
|----------|:---------:|:------------:|:---------:|-------|
| Mac (Chrome/Safari) | Yes | Yes | Yes | Full support |
| Mac (Firefox) | Yes | Yes | Yes | Full support |
| iPhone (Safari) | Yes | Yes | Yes | Tab must be in foreground |
| iPhone (Chrome) | Yes | Yes | Yes | Uses Safari's WebKit engine |
| iPad | Yes | Yes | Yes | Same as iPhone |
| AirPods | N/A | Yes | N/A | Audio routes automatically when connected |

**Mobile caveat:** On iOS, the WebSocket stays alive only while the browser tab is in the foreground. If the user switches apps, the voice session will disconnect. This is a browser-level constraint, not something we can work around. The UI should handle reconnection gracefully.

---

## Cost Considerations

Using `gpt-realtime-mini` (the cost-efficient model):

| Component | Pricing | Usage Pattern |
|-----------|---------|---------------|
| Audio input | $10 / 1M tokens (~$0.006/min) | User speech (typically short queries) |
| Audio output | $20 / 1M tokens (~$0.024/min) | Model responses (brief, conversational) |
| Cached audio input | $0.30 / 1M tokens | Repeated session context |
| Text input | $0.60 / 1M tokens | Tool results (RAG context) |
| Text output | $2.40 / 1M tokens | Transcript generation |
| **Est. per query** | **~$0.01–0.03** | 10-15s input + 15-30s output |

**vs `gpt-realtime` (full model):** Audio input $32/1M, output $64/1M — roughly 3x more expensive. The mini model has strong enough instruction following and tool calling for this use case.

**Mitigation:**
- Voice mode is opt-in, not default
- Session instructions emphasize brevity ("keep responses brief and natural")
- Tool results are passed as text tokens (much cheaper than audio)
- Session timeout: auto-disconnect after 2 minutes of silence
- Keep system prompt concise — long prompts significantly increase per-turn cost since they're sent as input tokens every turn

---

## Configuration

### Environment Variables

```bash
# Existing (already required)
SECONDBRAIN_OPENAI_API_KEY=sk-...

# New
SECONDBRAIN_VOICE_ENABLED=true              # Feature flag (default: false)
SECONDBRAIN_VOICE_MODEL=gpt-realtime-mini   # Realtime model (gpt-realtime-mini or gpt-realtime)
SECONDBRAIN_VOICE_VOICE=alloy               # Voice preset (alloy|echo|shimmer|etc)
SECONDBRAIN_VOICE_SESSION_TIMEOUT=120       # Auto-disconnect after N seconds of silence
```

### Feature Flag

Voice chat is behind `SECONDBRAIN_VOICE_ENABLED`. When disabled:
- The mic button is hidden in the chat UI
- The `/api/v1/voice` WebSocket endpoint returns 403
- No Realtime API connections are made

---

## Implementation Phases

### Phase A: Backend WebSocket Relay + Logging (~3-4 days)
- [ ] Add `src/secondbrain/api/voice.py` with WebSocket endpoint
- [ ] Implement OpenAI Realtime API connection and `session.update`
- [ ] Implement bidirectional event relay (browser ↔ OpenAI)
- [ ] Implement tool call interception and RAG pipeline integration
- [ ] Add JSONL event logging (transcripts, tool calls, interrupts, errors)
- [ ] Add feature flag and configuration
- [ ] Test with a WebSocket client (e.g., `websocat`) to verify relay works

### Phase B: Frontend Audio Pipeline + Interrupts (~3-4 days)
- [ ] Add `useVoiceChat` hook with WebSocket connection management
- [ ] Implement audio capture via AudioWorklet (getUserMedia → PCM16 → base64)
- [ ] Implement `AudioPlaybackQueue` with chunk-level playback tracking (`totalPlayedMs`)
- [ ] Implement interrupt handler:
  - On `speech_started`: flush playback queue, send `response.cancel` (if in_progress), send `conversation.item.truncate` with `audio_end_ms`
- [ ] Track response state machine (`idle` → `in_progress` → `done` | `interrupted`)
- [ ] Add mic permission handling and error states

### Phase C: Voice UI Components (~2-3 days)
- [ ] Add `VoiceButton` component to ChatInput
- [ ] Add `VoiceOverlay` with status indicators and waveform
- [ ] Extend ChatProvider with voice state
- [ ] Display transcripts in message thread (with voice badge)
- [ ] Handle session lifecycle (connect, active, disconnect, error)

### Phase D: Polish and Edge Cases (~2 days)
- [ ] Auto-disconnect on silence timeout
- [ ] Graceful handling of WebSocket disconnects / reconnection
- [ ] Mobile Safari compatibility testing (especially AudioWorklet support)
- [ ] Error states: mic permission denied, API key missing, backend down
- [ ] Loading/connecting states with appropriate UI feedback

---

## Testing Strategy

### Unit Tests
- Tool call handler: verify RAG results are formatted correctly
- Session config builder: verify instructions and tools are correct
- Audio playback queue: verify flush returns correct playedMs
- Response state machine: verify transitions on each event

### Integration Tests
- WebSocket endpoint: verify connection lifecycle (connect → relay → disconnect)
- Tool call round-trip: verify function_call → RAG → tool_result flow
- Interrupt flow: verify speech_started → flush → cancel → truncate sequence
- Feature flag: verify endpoint returns 403 when disabled

### Manual Testing
- Mac Chrome: full voice conversation with tool calls
- Mac Chrome: interrupt mid-response, verify audio stops immediately
- iPhone Safari: mic permission, audio playback through speakers and AirPods
- Network interruption: verify graceful disconnect and recovery
- Long conversation: verify memory/performance stability over multiple turns

---

## Security Considerations

- **API key protection**: The OpenAI API key never reaches the browser. All Realtime API communication goes through the backend relay.
- **Mic permission**: Standard browser permission prompt. No ambient listening — mic is only active when voice mode is explicitly started.
- **Audio data**: Audio streams are relayed in real-time and not persisted on disk. Only text transcripts are logged.
- **Tailscale**: Voice WebSocket is bound to 127.0.0.1, same as all other endpoints. Remote access requires Tailscale VPN.
- **Rate limiting**: Consider adding a max session duration (default 5 minutes) to prevent runaway API costs from forgotten sessions.

---

## Design Decisions (Resolved)

| Question | Decision | Rationale |
|----------|----------|-----------|
| **Voice selection** | Single default (`alloy`). No UI picker. | Change via env var if needed. Don't build settings UI for a single-user tool. |
| **Conversation continuity** | Start fresh each voice session. | Injecting prior text history into the Realtime API context is complex and error-prone. Keep voice sessions self-contained. Users can reference prior context verbally. |
| **Offline fallback** | Show error with "try text input instead." | A Whisper STT → text chat → browser TTS fallback is a completely different architecture. Not worth building. |
| **Push-to-talk** | Server VAD only for v1. | PTT can be added later if VAD proves unreliable in practice. Server VAD provides more natural conversation flow. |
| **Reranker latency** | Keep reranker enabled. Monitor latency in practice. | The model's conversational filler ("Let me check your notes...") covers the 2-5s reranker delay. If latency feels bad, a `SECONDBRAIN_VOICE_SKIP_RERANKER` option can bypass it — but don't build this preemptively. |

---

## References

- [OpenAI Realtime API Conversations Guide](https://platform.openai.com/docs/guides/realtime-conversations)
- [OpenAI Realtime API Client Events Reference](https://platform.openai.com/docs/api-reference/realtime-client-events)
- [OpenAI Realtime API Server Events Reference](https://platform.openai.com/docs/api-reference/realtime-server-events)
- [gpt-realtime-mini Model](https://platform.openai.com/docs/models/gpt-realtime-mini)
- [Introducing gpt-realtime (OpenAI Blog)](https://openai.com/index/introducing-gpt-realtime/)
- [Realtime API Cost Management](https://platform.openai.com/docs/guides/realtime-costs)
- [Azure Realtime Audio Reference (event details)](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/realtime-audio-reference)
