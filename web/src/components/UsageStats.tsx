import Link from "next/link";

/** Privacy note shown beside the founder card. */
export function UsageStats() {
  return (
    <div className="hidden items-start gap-3 rounded-2xl border border-emerald-400/30 bg-emerald-400/10 p-4 md:flex">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        aria-hidden
        className="mt-0.5 h-5 w-5 shrink-0 text-emerald-300"
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 3 5 6v5c0 4.5 3 8.5 7 10 4-1.5 7-5.5 7-10V6l-7-3Z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="m9 12 2 2 4-4" />
      </svg>
      <div className="flex flex-col gap-0.5">
        <p className="font-semibold text-emerald-200">No data is stored</p>
        <p className="text-sm text-zinc-400">
          Files are chunked in memory and discarded as soon as the chunks are returned.{" "}
          <Link href="/privacy" className="text-zinc-300 underline underline-offset-4 hover:text-zinc-100">
            Privacy
          </Link>
        </p>
      </div>
    </div>
  );
}
