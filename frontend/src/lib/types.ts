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
  provider?: "openai" | "local";
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
