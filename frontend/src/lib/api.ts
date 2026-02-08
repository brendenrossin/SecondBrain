import type {
  AskRequest,
  Citation,
  ConversationSummary,
  Conversation,
  TaskResponse,
  TaskCategory,
} from "./types";

const BASE = "/api/v1";

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

// --- Chat ---

export interface StreamCallbacks {
  onCitations: (citations: Citation[]) => void;
  onToken: (token: string) => void;
  onDone: (data: { conversation_id: string; retrieval_label: string }) => void;
  onError: (error: Error) => void;
}

export async function askStream(
  req: AskRequest,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${BASE}/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    callbacks.onError(new Error(`API error ${res.status}: ${text}`));
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    callbacks.onError(new Error("No response body"));
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "";

  function processLines(lines: string[]) {
    for (const rawLine of lines) {
      // Strip \r from CRLF line endings (sse_starlette uses \r\n)
      const line = rawLine.replace(/\r$/, "");
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        const data = line.slice(6);
        try {
          if (currentEvent === "citations") {
            callbacks.onCitations(JSON.parse(data));
          } else if (currentEvent === "token") {
            callbacks.onToken(JSON.parse(data));
          } else if (currentEvent === "done") {
            callbacks.onDone(JSON.parse(data));
          }
        } catch {
          // non-JSON data for token events
          if (currentEvent === "token") {
            callbacks.onToken(data);
          }
        }
      }
    }
  }

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    processLines(lines);
  }

  // Flush decoder and process any remaining buffered data
  buffer += decoder.decode();
  if (buffer) {
    processLines(buffer.split("\n"));
  }
}

// --- Conversations ---

export async function getConversations(): Promise<ConversationSummary[]> {
  return fetchJSON(`${BASE}/conversations`);
}

export async function getConversation(id: string): Promise<Conversation> {
  return fetchJSON(`${BASE}/conversations/${id}`);
}

export async function deleteConversation(id: string): Promise<void> {
  await fetch(`${BASE}/conversations/${id}`, { method: "DELETE" });
}

// --- Tasks ---

export async function getTasks(filters?: {
  category?: string;
  completed?: boolean;
  sub_project?: string;
}): Promise<TaskResponse[]> {
  const params = new URLSearchParams();
  if (filters?.category) params.set("category", filters.category);
  if (filters?.completed !== undefined)
    params.set("completed", String(filters.completed));
  if (filters?.sub_project) params.set("sub_project", filters.sub_project);
  const qs = params.toString();
  return fetchJSON(`${BASE}/tasks${qs ? `?${qs}` : ""}`);
}

export async function getUpcomingTasks(days = 7): Promise<TaskResponse[]> {
  return fetchJSON(`${BASE}/tasks/upcoming?days=${days}`);
}

export async function getTaskCategories(): Promise<TaskCategory[]> {
  return fetchJSON(`${BASE}/tasks/categories`);
}

// --- Index ---

export async function getIndexStats(): Promise<{
  total_notes: number;
  total_chunks: number;
  embedding_model: string;
}> {
  return fetchJSON(`${BASE}/index/stats`);
}

export async function triggerExtraction(): Promise<{ status: string }> {
  return fetchJSON(`${BASE}/extract`, { method: "POST" });
}

export async function getMetadata(
  path: string
): Promise<Record<string, unknown>> {
  return fetchJSON(`${BASE}/metadata/${encodeURIComponent(path)}`);
}

export async function getSuggestions(
  path: string
): Promise<Record<string, unknown>> {
  return fetchJSON(`${BASE}/suggestions/${encodeURIComponent(path)}`);
}
