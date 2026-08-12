"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

export function FilterBar() {
  const router = useRouter();
  const params = useSearchParams();

  const update = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(params.toString());
      if (value === "" || value === undefined) {
        next.delete(key);
      } else {
        next.set(key, value);
      }
      next.delete("offset"); // reset pagination on filter change
      router.push(`/?${next.toString()}`);
    },
    [params, router]
  );

  const minScore = params.get("min_score") ?? "0";
  const sortBy = params.get("sort_by") ?? "score";
  const isFree = params.get("is_free") ?? "";
  const q = params.get("q") ?? "";

  return (
    <div className="flex flex-wrap items-center gap-3 py-4 px-1">
      {/* Search */}
      <input
        type="text"
        placeholder="Search events..."
        defaultValue={q}
        onChange={(e) => update("q", e.target.value)}
        className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-52 focus:outline-none focus:ring-2 focus:ring-blue-400"
      />

      {/* Min relevance score */}
      <div className="flex items-center gap-2 text-sm">
        <label className="text-gray-600 whitespace-nowrap">Min score:</label>
        <input
          type="range"
          min={0}
          max={10}
          step={0.5}
          value={minScore}
          onChange={(e) => update("min_score", e.target.value)}
          className="w-28 accent-emerald-500"
        />
        <span className="text-gray-800 font-medium w-6">{minScore}</span>
      </div>

      {/* Sort */}
      <div className="flex items-center gap-2 text-sm">
        <label className="text-gray-600">Sort:</label>
        <select
          value={sortBy}
          onChange={(e) => update("sort_by", e.target.value)}
          className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
        >
          <option value="score">Relevance</option>
          <option value="date">Date</option>
        </select>
      </div>

      {/* Free only */}
      <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={isFree === "true"}
          onChange={(e) => update("is_free", e.target.checked ? "true" : "")}
          className="accent-emerald-500"
        />
        Free only
      </label>

      {/* Clear */}
      {params.toString() && (
        <button
          onClick={() => router.push("/")}
          className="text-xs text-gray-400 hover:text-gray-700 underline"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}
