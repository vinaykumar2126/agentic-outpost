import { Suspense } from "react";
import { getEvents } from "@/lib/api";
import { EventCard } from "@/components/EventCard";
import { FilterBar } from "@/components/FilterBar";
import type { EventFilters } from "@/types/event";

interface PageProps {
  searchParams: Promise<Record<string, string>>;
}

export default async function Home({ searchParams }: PageProps) {
  const sp = await searchParams;

  const filters: Partial<EventFilters> = {
    min_score: sp.min_score ? parseFloat(sp.min_score) : 0,
    sort_by: (sp.sort_by as "score" | "date") ?? "score",
    limit: 50,
    offset: sp.offset ? parseInt(sp.offset) : 0,
    ...(sp.q && { q: sp.q }),
    ...(sp.is_free && { is_free: sp.is_free === "true" }),
    ...(sp.is_online && { is_online: sp.is_online === "true" }),
    ...(sp.date_from && { date_from: sp.date_from }),
    ...(sp.date_to && { date_to: sp.date_to }),
  };

  let result = { events: [], total: 0, limit: 50, offset: 0 };
  let error = "";

  try {
    result = await getEvents(filters);
  } catch {
    error = "Could not connect to the backend. Is it running on port 8000?";
  }

  return (
    <main className="max-w-3xl mx-auto px-4 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Bay Area AI Events</h1>
        <p className="text-sm text-gray-500 mt-1">
          {result.total} upcoming events · ranked by relevance to AI engineering & agentic AI
        </p>
      </header>

      <Suspense>
        <FilterBar />
      </Suspense>

      {error && (
        <div className="mt-4 rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="mt-4 flex flex-col gap-4">
        {result.events.length === 0 && !error && (
          <p className="text-center text-gray-400 py-12">
            No events found. Try running <code className="bg-gray-100 px-1 rounded">make scrape</code> in the backend.
          </p>
        )}
        {result.events.map((event) => (
          <EventCard key={event.id} event={event} />
        ))}
      </div>

      {result.total > result.limit && (
        <div className="mt-8 text-center text-sm text-gray-500">
          Showing {result.events.length} of {result.total} events
        </div>
      )}
    </main>
  );
}
