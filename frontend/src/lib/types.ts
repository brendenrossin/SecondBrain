// Mirrors src/secondbrain/models.py

export interface Citation {
  note_path: string;
  note_title: string;
  heading_path: string[];
  chunk_id: string;
  snippet: string;
  similarity_score: number;
  rerank_score: number;
}

export interface AskRequest {
  query: string;
  conversation_id?: string | null;
  top_n?: number;
  provider?: "anthropic" | "openai" | "local";
}

export interface AskResponse {
  answer: string;
  conversation_id: string;
  citations: Citation[];
  retrieval_label: string;
}

export interface ConversationMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

export interface ConversationSummary {
  conversation_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  preview: string;
}

export interface Conversation {
  conversation_id: string;
  messages: ConversationMessage[];
}

export interface TaskResponse {
  text: string;
  category: string;
  sub_project: string;
  due_date: string;
  completed: boolean;
  days_open: number;
  first_date: string;
  latest_date: string;
  appearance_count: number;
}

export interface TaskCategory {
  category: string;
  sub_projects: { name: string; count: number }[];
  total: number;
}

export interface Entity {
  text: string;
  entity_type: string;
  confidence: number;
}

export interface DateMention {
  text: string;
  normalized_date: string | null;
  date_type: string;
  confidence: number;
}

export interface ActionItem {
  text: string;
  confidence: number;
  priority: string | null;
}

export interface NoteMetadata {
  note_path: string;
  summary: string;
  key_phrases: string[];
  entities: Entity[];
  dates: DateMention[];
  action_items: ActionItem[];
  extracted_at: string;
  content_hash: string;
  model_used: string;
}

export interface RelatedNote {
  note_path: string;
  note_title: string;
  similarity_score: number;
  shared_entities: string[];
}

export interface LinkSuggestion {
  target_note_path: string;
  target_note_title: string;
  anchor_text: string;
  confidence: number;
  reason: string;
}

export interface TagSuggestion {
  tag: string;
  confidence: number;
  source_notes: string[];
}

export interface NoteSuggestions {
  note_path: string;
  note_title: string;
  related_notes: RelatedNote[];
  suggested_links: LinkSuggestion[];
  suggested_tags: TagSuggestion[];
  generated_at: string;
}

export interface IndexStats {
  vector_count: number;
  lexical_count: number;
}

// --- Morning Briefing ---

export interface BriefingTask {
  text: string;
  category: string;
  sub_project: string;
  due_date: string;
  days_open: number;
  first_date: string;
}

export interface DailyContext {
  date: string;
  focus_items: string[];
  notes_items: string[];
}

export interface BriefingResponse {
  today: string;
  today_display: string;
  overdue_tasks: BriefingTask[];
  due_today_tasks: BriefingTask[];
  aging_followups: BriefingTask[];
  yesterday_context: DailyContext | null;
  total_open: number;
}

// --- Admin / Cost Tracking ---

export interface UsageCostBreakdown {
  cost: number;
  calls: number;
  input_tokens: number;
  output_tokens: number;
}

export interface CostSummaryResponse {
  total_cost: number;
  total_calls: number;
  by_provider: Record<string, UsageCostBreakdown>;
  by_usage_type: Record<string, UsageCostBreakdown>;
  period: string;
}

export interface DailyCost {
  date: string;
  cost_usd: number;
  calls: number;
  by_provider: Record<string, number>;
}

export interface DailyCostsResponse {
  days: number;
  daily: DailyCost[];
}

export interface AdminStatsResponse {
  total_queries: number;
  avg_latency_ms: number;
  total_conversations: number;
  index_file_count: number;
  total_llm_calls: number;
  total_llm_cost: number;
}

// --- Quick Capture ---

export interface CaptureResponse {
  filename: string;
  message: string;
}
