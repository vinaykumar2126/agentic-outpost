import Link from "next/link";
import { notFound } from "next/navigation";
import { getEvent } from "@/lib/api";
import { ScoreBar } from "@/components/ScoreBar";

interface Props {
  params: Promise<{ id: string }>;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
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

export default async function EventPage({ params }: Props) {
  const { id } = await params;
  let event;

  try {
    event = await getEvent(parseInt(id));
  } catch {
    notFound();
  }

  const tags = parseTags(event.tags);

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <Link href="/" className="text-sm text-blue-600 hover:underline mb-6 inline-block">
        ← Back to events
      </Link>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 flex flex-col gap-5">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 leading-snug">{event.title}</h1>
          {event.organizer_name && (
            <p className="text-sm text-gray-500 mt-1">by {event.organizer_name}</p>
          )}
        </div>

        <div className="flex flex-col gap-1">
          <p className="text-xs text-gray-400 uppercase tracking-wide font-medium">AI Relevance</p>
          <ScoreBar score={event.relevance_score} />
          {event.relevance_justification && (
            <p className="text-sm text-emerald-700 italic mt-1">
              "{event.relevance_justification}"
            </p>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide font-medium mb-1">Date</p>
            <p className="text-gray-800">{formatDate(event.start_datetime)}</p>
            {event.end_datetime && (
              <p className="text-gray-500 text-xs mt-0.5">until {formatDate(event.end_datetime)}</p>
            )}
          </div>
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide font-medium mb-1">Location</p>
            <p className="text-gray-800">
              {event.is_online ? "Online" : event.location_name ?? "TBD"}
            </p>
            {event.location_address && (
              <p className="text-xs text-gray-500 mt-0.5">{event.location_address}</p>
            )}
          </div>
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide font-medium mb-1">Price</p>
            <p className="text-gray-800">
              {event.is_free ? "Free" : event.price_min ? `From $${event.price_min}` : "Paid"}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide font-medium mb-1">Source</p>
            <p className="text-gray-800 capitalize">{event.source}</p>
          </div>
        </div>

        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {tags.map((tag) => (
              <span
                key={tag}
                className="text-xs px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-100"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {event.description && (
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide font-medium mb-2">About</p>
            <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
              {event.description}
            </p>
          </div>
        )}

        <a
          href={event.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-flex items-center justify-center w-full rounded-lg bg-blue-600 text-white py-2.5 text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          RSVP on {event.source.charAt(0).toUpperCase() + event.source.slice(1)} →
        </a>
      </div>
    </main>
  );
}
