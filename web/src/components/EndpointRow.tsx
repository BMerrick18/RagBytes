import type { ReactNode } from "react";

interface EndpointRowProps {
  verb: "GET" | "POST";
  path: string;
  soon?: boolean;
  action?: ReactNode;
  below?: ReactNode;
  children: ReactNode;
}

export function EndpointRow({ verb, path, soon, action, below, children }: EndpointRowProps) {
  const tone =
    verb === "POST"
      ? "bg-cyan-400/10 text-cyan-300 ring-cyan-400/30"
      : "bg-emerald-400/10 text-emerald-300 ring-emerald-400/30";
  return (
    <li className={`flex flex-col gap-3 px-4 py-3 ${soon ? "opacity-60" : ""}`}>
      <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:gap-4">
        <span className="flex shrink-0 items-center gap-2 sm:w-60">
          <span className={`rounded-md px-2 py-0.5 font-mono text-xs font-semibold ring-1 ring-inset ${tone}`}>
            {verb}
          </span>
          <span className="font-mono text-sm text-zinc-100">{path}</span>
        </span>
        <span className="flex-1 text-sm text-zinc-400">
          {soon && (
            <span className="mr-2 rounded bg-zinc-800 px-1.5 py-0.5 text-xs font-medium text-zinc-300">Coming soon</span>
          )}
          {children}
        </span>
        {action}
      </div>
      {below}
    </li>
  );
}
