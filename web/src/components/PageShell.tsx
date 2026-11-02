import type { ReactNode } from "react";

export function PageShell({ title, intro, children }: { title: string; intro: ReactNode; children: ReactNode }) {
  return (
    <main className="flex-1">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-10 px-6 py-10">
        <header className="flex flex-col gap-4">
          <h1 className="text-3xl font-semibold tracking-tight text-zinc-100 sm:text-4xl">{title}</h1>
          <div className="max-w-2xl text-zinc-400">{intro}</div>
        </header>
        {children}
      </div>
    </main>
  );
}

export function DocSection({ id, title, children }: { id?: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="flex flex-col gap-4 text-zinc-300">
      <h2 className="text-xl font-semibold text-zinc-100">{title}</h2>
      {children}
    </section>
  );
}

export function CodeBlock({ label, children }: { label?: string; children: string }) {
  return (
    <figure className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/60">
      {label && (
        <figcaption className="border-b border-zinc-800 px-4 py-2 text-xs font-medium text-zinc-400">{label}</figcaption>
      )}
      <pre className="overflow-x-auto p-4 font-mono text-[13px] leading-relaxed text-zinc-200">{children}</pre>
    </figure>
  );
}

export function Code({ children }: { children: ReactNode }) {
  return <code className="rounded bg-zinc-800/80 px-1.5 py-0.5 font-mono text-[13px] text-zinc-100">{children}</code>;
}
