export interface EventSummary {
  id: number;
  external_id: string;
  source: string;
  title: string;
  short_description: string | null;
  url: string;
  start_datetime: string;
  end_datetime: string | null;
  location_name: string | null;
  location_address: string | null;
  is_online: boolean;
  organizer_name: string | null;
  tags: string | null; // JSON array string e.g. '["AI","LLM"]'
  is_free: boolean;
  price_min: number | null;
  price_max: number | null;
  relevance_score: number | null;
  relevance_justification: string | null;
}

export interface EventDetail extends EventSummary {
  description: string | null;
  ranked_at: string | null;
  fetched_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EventListResponse {
  events: EventSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface ScrapeRun {
  id: number;
  source: string;
  started_at: string;
  completed_at: string | null;
  events_fetched: number;
  events_new: number;
  events_updated: number;
  events_ranked: number;
  status: "running" | "success" | "failed";
  error_message: string | null;
}

export type SortBy = "score" | "date";

export interface EventFilters {
  min_score: number;
  max_score: number;
  date_from?: string;
  date_to?: string;
  source?: string;
  is_free?: boolean;
  is_online?: boolean;
  q?: string;
  sort_by: SortBy;
  limit: number;
  offset: number;
}
