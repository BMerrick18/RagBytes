"use client";

import { useId, useState } from "react";
import {
  maxChunkCharsProblem,
  MAX_CHUNK_CHARS_RANGE,
  SEMANTIC_STYLES,
  type SemanticOptions,
} from "@/lib/semantic";
import { formatNumber } from "@/lib/stats";

interface SemanticOptionsPanelProps {
  value: SemanticOptions;
  onChange: (options: SemanticOptions) => void;
  disabled?: boolean;
}

export function SemanticOptionsPanel({ value, onChange, disabled = false }: SemanticOptionsPanelProps) {
  const [draft, setDraft] = useState(value.maxChunkChars === null ? "" : String(value.maxChunkChars));
  const sizeId = useId();
  const sizeHintId = useId();
  const strictId = useId();
  const chosen = SEMANTIC_STYLES.find((style) => style.id === value.style) ?? SEMANTIC_STYLES[1];
  const problem = maxChunkCharsProblem(value.maxChunkChars);

  function setSize(text: string) {
    setDraft(text);
    const trimmed = text.trim();
    onChange({ ...value, maxChunkChars: trimmed === "" ? null : Number(trimmed) });
  }

  return (
    <fieldset
      disabled={disabled}
      className="flex flex-col gap-4 rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 disabled:opacity-60"
    >
      <legend className="px-1 text-sm font-medium text-zinc-300">Semantic options</legend>

      <div className="flex flex-col gap-2">
        <span className="text-sm text-zinc-400">Style</span>
        <div role="radiogroup" aria-label="Semantic style" className="grid gap-2 sm:grid-cols-3">
          {SEMANTIC_STYLES.map((style) => {
            const selected = style.id === value.style;
            return (
              <button
                key={style.id}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => onChange({ ...value, style: style.id })}
                className={`flex min-h-11 flex-col gap-1 rounded-lg border p-3 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 ${
                  selected
                    ? "border-cyan-400 bg-cyan-400/10"
                    : "border-zinc-800 bg-zinc-900/60 hover:border-zinc-600"
                }`}
              >
                <span className={`text-sm font-semibold ${selected ? "text-cyan-100" : "text-zinc-100"}`}>
                  {style.name}
                </span>
                <span className="text-xs leading-relaxed text-zinc-400">{style.summary}</span>
                <span className="text-xs text-zinc-500">Up to {formatNumber(style.maxChars)} characters</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={sizeId} className="text-sm text-zinc-400">
            Largest chunk, in characters
          </label>
          <input
            id={sizeId}
            type="number"
            inputMode="numeric"
            min={MAX_CHUNK_CHARS_RANGE.min}
            max={MAX_CHUNK_CHARS_RANGE.max}
            step={100}
            value={draft}
            onChange={(event) => setSize(event.target.value)}
            placeholder={`${formatNumber(chosen.maxChars)} (${chosen.name} default)`}
            aria-invalid={problem !== null}
            aria-describedby={sizeHintId}
            className="min-h-11 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-cyan-400 focus:outline-none aria-[invalid=true]:border-rose-400"
          />
          <span id={sizeHintId} aria-live="polite" className={`text-xs ${problem ? "text-rose-300" : "text-zinc-500"}`}>
            {problem ??
              `Leave blank for the style's limit, or set ${formatNumber(MAX_CHUNK_CHARS_RANGE.min)} to ${formatNumber(MAX_CHUNK_CHARS_RANGE.max)}.`}
          </span>
        </div>

        <label htmlFor={strictId} className="flex min-h-11 cursor-pointer items-start gap-3 self-start pt-6">
          <input
            id={strictId}
            type="checkbox"
            checked={value.strictHeadings}
            onChange={(event) => onChange({ ...value, strictHeadings: event.target.checked })}
            className="mt-0.5 h-5 w-5 shrink-0 accent-cyan-400"
          />
          <span className="flex flex-col gap-0.5">
            <span className="text-sm font-medium text-zinc-200">Strict headings</span>
            <span className="text-xs leading-relaxed text-zinc-400">
              Never let a chunk span two headings, even very short ones. Useful when every chunk must cite one
              exact section.
            </span>
          </span>
        </label>
      </div>
    </fieldset>
  );
}
