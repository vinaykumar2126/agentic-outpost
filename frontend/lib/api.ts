import type { EventDetail, EventFilters, EventListResponse } from "@/types/event";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function getEvents(filters: Partial<EventFilters> = {}): Promise<EventListResponse> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, val]) => {
    if (val !== undefined && val !== null && val !== "") {
      params.set(key, String(val));
    }
  });

  const res = await fetch(`${API_BASE}/api/events?${params.toString()}`, {
    next: { revalidate: 300 }, // cache for 5 minutes
  });

  if (!res.ok) throw new Error(`Failed to fetch events: ${res.status}`);
  return res.json();
}

export async function getEvent(id: number): Promise<EventDetail> {
  const res = await fetch(`${API_BASE}/api/events/${id}`, {
    next: { revalidate: 300 },
  });
  if (!res.ok) throw new Error(`Event ${id} not found`);
  return res.json();
}
