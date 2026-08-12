import Link from "next/link";
import type { EventSummary } from "@/types/event";
import { ScoreBar } from "./ScoreBar";

interface EventCardProps {
  event: EventSummary;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function parseTags(tags: string | null): string[] {
  if (!tags) return [];
  try {
    return JSON.parse(tags);
  } catch {
    return [];
  }
}

export function EventCard({ event }: EventCardProps) {
  const tags = parseTags(event.tags);

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm hover:shadow-md transition-shadow flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <Link
          href={`/events/${event.id}`}
          className="font-semibold text-gray-900 hover:text-blue-600 transition-colors leading-snug"
        >
          {event.title}
        </Link>
        <div className="shrink-0 w-32">
          <ScoreBar score={event.relevance_score} size="sm" />
        </div>
      </div>

      {event.short_description && (
        <p className="text-sm text-gray-500 line-clamp-2">{event.short_description}</p>
      )}

      {event.relevance_justification && (
        <p className="text-xs text-emerald-700 italic">"{event.relevance_justification}"</p>
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
        <span>📅 {formatDate(event.start_datetime)}</span>
        {event.is_online ? (
          <span>🌐 Online</span>
        ) : event.location_name ? (
          <span>📍 {event.location_name}</span>
        ) : null}
        {event.organizer_name && <span>👤 {event.organizer_name}</span>}
        <span>{event.is_free ? "🆓 Free" : event.price_min ? `$${event.price_min}+` : "Paid"}</span>
      </div>

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {tags.slice(0, 5).map((tag) => (
            <span
              key={tag}
              className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-100"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="flex justify-between items-center pt-1">
        <span className="text-xs text-gray-400 capitalize">{event.source}</span>
        <a
          href={event.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs font-medium text-blue-600 hover:underline"
        >
          RSVP →
        </a>
      </div>
    </div>
  );
}
