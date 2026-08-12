interface ScoreBarProps {
  score: number | null;
  size?: "sm" | "md";
}

function scoreBadgeClass(score: number | null): string {
  if (score === null) return "bg-gray-100 text-gray-400";
  if (score >= 9) return "bg-emerald-500 text-white";
  if (score >= 7) return "bg-green-200 text-green-900";
  if (score >= 5) return "bg-blue-100 text-blue-900";
  if (score >= 3) return "bg-yellow-100 text-yellow-900";
  return "bg-gray-200 text-gray-600";
}

export function ScoreBar({ score, size = "md" }: ScoreBarProps) {
  const label = score !== null ? score.toFixed(1) : "–";
  const pct = score !== null ? (score / 10) * 100 : 0;
  const badgeClass = scoreBadgeClass(score);
  const textSize = size === "sm" ? "text-xs" : "text-sm";

  return (
    <div className="flex items-center gap-2">
      <span
        className={`inline-flex items-center justify-center rounded-full font-semibold ${textSize} px-2 py-0.5 min-w-[2.5rem] ${badgeClass}`}
      >
        {label}
      </span>
      <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-yellow-300 via-green-400 to-emerald-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
