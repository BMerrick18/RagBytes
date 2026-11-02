"use client";

import { TIERS } from "@/lib/tiers";

function TierStrength({ level, className = "" }: { level: number; className?: string }) {
  return (
    <svg viewBox="0 0 16 12" className={`h-3.5 w-5 shrink-0 -rotate-90 ${className}`} aria-hidden>
      {[1, 2, 3, 4].map((bar) => {
        const height = bar * 3;
        return (
          <rect
            key={bar}
            x={(bar - 1) * 4}
            y={12 - height}
            width="3"
            height={height}
            rx="0.6"
            className={bar <= level ? "fill-cyan-300" : "fill-zinc-500"}
          />
        );
      })}
    </svg>
  );
}

interface TierPickerProps {
  id?: string;
  value: string;
  onChange: (tier: string) => void;
  collapsed?: boolean;
}

export function TierPicker({ id, value, onChange, collapsed = false }: TierPickerProps) {
  return (
    <div
      id={id}
      role="radiogroup"
      aria-label="Chunking tier"
      className={collapsed ? "grid w-full grid-cols-2 gap-2" : "grid gap-3 sm:grid-cols-2 xl:grid-cols-4"}
    >
      {TIERS.map((tier, index) => {
        const selected = tier.id === value;
        return (
          <button
            key={tier.id}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={!tier.available}
            onClick={() => onChange(tier.id)}
            className={`border text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 ${
              collapsed
                ? "relative inline-flex w-full min-w-0 items-center justify-center rounded-lg px-8 py-2 text-center text-sm font-semibold"
                : "relative flex flex-col gap-2 rounded-xl p-4"
            } ${
              selected
                ? "border-cyan-400 bg-cyan-400/10 text-cyan-100"
                : "border-zinc-800 bg-zinc-900/60 text-zinc-100 hover:border-zinc-600"
            } ${tier.available ? "" : "cursor-not-allowed opacity-60 hover:border-zinc-800"}`}
          >
            {collapsed ? (
              <>
                {tier.name}
                <TierStrength level={index + 1} className="absolute top-1/2 right-3 -translate-y-1/2" />
              </>
            ) : (
              <>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Tier {index + 1}</span>
                  {!tier.available && (
                    <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[11px] font-medium text-zinc-400">
                      Coming soon
                    </span>
                  )}
                </div>
                <div>
                  <p className="flex items-center gap-2 font-semibold text-zinc-100">
                    {tier.name}
                    <TierStrength level={index + 1} />
                  </p>
                  <p className="text-sm text-cyan-300/90">{tier.tagline}</p>
                </div>
                <p className="text-sm leading-relaxed text-zinc-400">{tier.description}</p>
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}
