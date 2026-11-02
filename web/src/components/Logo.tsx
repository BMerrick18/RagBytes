export function Logo({ className = "h-9 w-9" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="8" className="fill-cyan-400" />
      <path d="M7 21c3-1 5-6 9-10 1 3 3 5 9 6-4 1-6 4-9 4-3 0-6 1-9 0z" className="fill-zinc-950" />
      <path d="M8 24h4M14 24h4M20 24h4" stroke="currentColor" strokeWidth={2} strokeLinecap="round" className="text-zinc-950" />
    </svg>
  );
}

export function LogoSvg() {
  return (
    <svg viewBox="0 0 32 32" width="36" height="36" aria-hidden>
      <rect width="32" height="32" rx="8" fill="#22d3ee" />
      <path d="M7 21c3-1 5-6 9-10 1 3 3 5 9 6-4 1-6 4-9 4-3 0-6 1-9 0z" fill="#09090b" />
      <path d="M8 24h4M14 24h4M20 24h4" fill="none" stroke="#09090b" strokeWidth={2} strokeLinecap="round" />
    </svg>
  );
}
