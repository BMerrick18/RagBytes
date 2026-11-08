"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { ChunkingDemo } from "@/components/ChunkingDemo";
import { CollapseButton } from "@/components/CollapseButton";
import { Dropzone } from "@/components/Dropzone";
import { HowItWorks } from "@/components/HowItWorks";
import { ResultsView } from "@/components/ResultsView";
import { SemanticOptionsPanel } from "@/components/SemanticOptionsPanel";
import { TierPicker } from "@/components/TierPicker";
import { UsageStats } from "@/components/UsageStats";
import { loadSampleDocument, SAMPLE_DOCUMENT } from "@/lib/sample";
import {
  DEFAULT_SEMANTIC_OPTIONS,
  maxChunkCharsProblem,
  semanticFields,
  styleName,
  type SemanticOptions,
} from "@/lib/semantic";
import { formatNumber } from "@/lib/stats";
import { isAccepted, isOffered, TIERS } from "@/lib/tiers";
import type { ChunkResponse, Job } from "@/lib/types";

async function chunkFile(file: File, tier: string, semantic?: SemanticOptions): Promise<ChunkResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("method", tier);
  if (tier === "semantic" && semantic) {
    for (const [name, value] of semanticFields(semantic)) form.append(name, value);
  }
  const response = await fetch("/api/chunks", { method: "POST", body: form });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(errorMessage(body?.detail) ?? `The service returned ${response.status}.`);
  }
  return body as ChunkResponse;
}

/** A string detail, or the messages from a validation error's list of problems. */
function errorMessage(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => (typeof item?.msg === "string" ? item.msg : null)).filter(Boolean);
    if (messages.length > 0) return messages.join(" ");
  }
  return undefined;
}

export function RagByteApp() {
  const [tier, setTier] = useState("structured");
  const [semantic, setSemantic] = useState<SemanticOptions>(DEFAULT_SEMANTIC_OPTIONS);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [rejected, setRejected] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [loadingSample, setLoadingSample] = useState(false);
  const [sampleError, setSampleError] = useState<string | null>(null);
  const [tiersOpen, setTiersOpen] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const tierPickerId = useId();

  const queued = jobs.filter((job) => job.status === "queued");
  const selected = jobs.find((job) => job.id === selectedId) ?? null;
  const optionsInvalid = tier === "semantic" && maxChunkCharsProblem(semantic.maxChunkChars) !== null;

  function addFiles(files: File[]) {
    const accepted = files.filter(isAccepted);
    setRejected(files.filter((file) => !isAccepted(file)).map((file) => file.name));
    setJobs((current) => [
      ...current,
      ...accepted.map((file) => ({ id: crypto.randomUUID(), file, tier, status: "queued" as const })),
    ]);
  }

  async function addSample() {
    setLoadingSample(true);
    try {
      addFiles([await loadSampleDocument()]);
    } catch (error) {
      setSampleError(error instanceof Error ? error.message : String(error));
    } finally {
      setLoadingSample(false);
    }
  }

  function update(id: string, changes: Partial<Job>) {
    setJobs((current) => current.map((job) => (job.id === id ? { ...job, ...changes } : job)));
  }

  async function run() {
    setRunning(true);
    const options = tier === "semantic" ? semantic : undefined;
    for (const job of queued) {
      update(job.id, { status: "running", tier, semantic: options });
      const started = performance.now();
      try {
        const result = await chunkFile(job.file, tier, options);
        update(job.id, { status: "done", result, elapsedMs: performance.now() - started });
        setSelectedId((current) => current ?? job.id);
      } catch (error) {
        update(job.id, { status: "error", error: error instanceof Error ? error.message : String(error) });
      }
    }
    setRunning(false);
  }

  function chunkAgain(job: Job) {
    setJobs((current) => [...current, { id: crypto.randomUUID(), file: job.file, tier, status: "queued" }]);
  }

  function remove(id: string) {
    setJobs((current) => current.filter((job) => job.id !== id));
    if (selectedId === id) setSelectedId(null);
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-10 px-6 py-10">
      <header className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="flex min-w-0 flex-col gap-3 lg:col-start-1 lg:row-start-1">
          <h1 className="max-w-2xl text-3xl font-semibold tracking-tight text-zinc-100 sm:text-4xl">
            Turn documents into chunks that are ready to embed.
          </h1>
          <p className="max-w-2xl text-zinc-400">
            Upload PDFs, Word documents, web pages, Markdown or plain text. RagBytes strips page clutter, keeps
            headings, tables and images in context, and returns chunks you can drop straight into a vector store.
          </p>
          <a 
            href="#choose-tier" 
            className="inline-flex w-fit items-center self-end rounded-lg bg-cyan-400 px-5 py-2.5 font-semibold text-zinc-950 transition-colors hover:bg-cyan-300"
          >
            Try it
          </a>
          <HowItWorks />
          <button
            id="see-example-top"
            type="button"
            onClick={() => setDemoOpen((open) => !open)}
            className="inline-flex w-fit items-center self-end rounded-lg bg-cyan-400 px-5 py-2.5 font-semibold text-zinc-950 transition-colors hover:bg-cyan-300 lg:hidden"
          >
            {demoOpen ? "Hide example" : "See an example"}
          </button>
        </div>
        <div className={`${demoOpen ? "flex" : "hidden lg:flex"} min-w-0 flex-col gap-3 lg:col-span-2 lg:row-start-2`}>
          <ChunkingDemo key={demoOpen ? "open" : "closed"} tier={tier} startOpen={demoOpen} />
          <button
            type="button"
            onClick={() => {
              document.getElementById("see-example-top")?.scrollIntoView({ block: "center" });
              setDemoOpen(false);
            }}
            className="inline-flex w-fit items-center self-end rounded-lg bg-cyan-400 px-5 py-2.5 font-semibold text-zinc-950 transition-colors hover:bg-cyan-300 lg:hidden"
          >
            Hide example
          </button>
        </div>
        <div className="flex w-full shrink-0 flex-col gap-3 sm:w-96 sm:self-start lg:col-start-2 lg:row-start-1 lg:w-auto">
          <FounderCard />
          <UsageStats />
        </div>
      </header>

      <section id="choose-tier" className="flex scroll-mt-24 flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <StepTitle number={1} title="Choose a chunking tier" />
          <CollapseButton
            open={tiersOpen}
            onToggle={() => setTiersOpen(!tiersOpen)}
            controls={tierPickerId}
            showLabel="Show details"
            hideLabel="Hide details"
          />
        </div>
        <TierPicker id={tierPickerId} value={tier} onChange={setTier} collapsed={!tiersOpen} />
        {tier === "semantic" && <SemanticOptionsPanel value={semantic} onChange={setSemantic} disabled={running} />}
      </section>

      <section id="upload"className="flex flex-col gap-4">
        <StepTitle number={2} title="Add your documents" />
        <Dropzone onFiles={addFiles} disabled={running} />
        <p className="text-sm text-zinc-500">
          <span className="font-semibold text-zinc-200">No data is stored.</span> Your files are processed in memory
          and discarded as soon as the chunks are returned.
          {isOffered("semantic") &&
            " Semantic sends the passage text to OpenAI for the comparison, then discards that too."}{" "}
          <Link href="/privacy" className="text-zinc-400 underline underline-offset-4 hover:text-zinc-200">
            Privacy
          </Link>
        </p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-zinc-400">
          <span>No document to hand?</span>
          <button
            type="button"
            onClick={() => {
              setSampleError(null);
              addSample();
            }}
            disabled={running || loadingSample}
            className="inline-flex items-center gap-2 rounded-lg border border-cyan-400/30 bg-cyan-400/10 px-3 py-1.5 font-medium text-cyan-200 transition-colors hover:border-cyan-400/60 hover:bg-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-4 w-4" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M14 3v5h5M9 13h6M9 17h4" />
            </svg>
            {loadingSample ? "Loading sample…" : "Try the sample report"}
          </button>
          <a
            href={SAMPLE_DOCUMENT.url}
            download={SAMPLE_DOCUMENT.name}
            className="inline-flex min-h-11 min-w-11 items-center text-zinc-500 underline-offset-4 hover:text-zinc-300 hover:underline md:min-h-0 md:min-w-0"
          >
            Download it
          </a>
        </div>
        {sampleError && <p className="text-sm text-rose-300">{sampleError}</p>}
        {rejected.length > 0 && (
          <p className="text-sm text-amber-300">
            Skipped {rejected.join(", ")}: that file type isn&apos;t supported yet.
          </p>
        )}
        {jobs.length > 0 && (
          <ul className="flex flex-col divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900/40">
            {jobs.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                selected={job.id === selectedId}
                onSelect={() => setSelectedId(job.id)}
                onAgain={() => chunkAgain(job)}
                onRemove={() => remove(job.id)}
                disabled={running}
              />
            ))}
          </ul>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={run}
            disabled={running || queued.length === 0 || optionsInvalid}
            className="rounded-lg bg-cyan-400 px-5 py-2.5 font-semibold text-zinc-950 transition-colors hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400"
          >
            {running
              ? "Chunking…"
              : queued.length > 1
                ? `Chunk ${queued.length} documents`
                : "Chunk document"}
          </button>
          {jobs.length > 0 && !running && (
            <button
              type="button"
              onClick={() => {
                setJobs([]);
                setSelectedId(null);
              }}
              className="text-sm text-zinc-400 hover:text-zinc-200"
            >
              Clear all
            </button>
          )}
        </div>
      </section>

      {selected?.result && (
        <section className="flex flex-col gap-4">
          <StepTitle number={3} title="Review your chunks" />
          <ResultsView key={selected.id} result={selected.result} elapsedMs={selected.elapsedMs} />
        </section>
      )}
    </div>
  );
}

interface JobRowProps {
  job: Job;
  selected: boolean;
  onSelect: () => void;
  onAgain: () => void;
  onRemove: () => void;
  disabled: boolean;
}

function JobRow({ job, selected, onSelect, onAgain, onRemove, disabled }: JobRowProps) {
  const baseName = TIERS.find((tier) => tier.id === job.tier)?.name ?? job.tier;
  const tierName = job.semantic ? `${baseName} (${styleName(job.semantic.style)})` : baseName;
  return (
    <li className={`flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 ${selected ? "bg-cyan-400/5" : ""}`}>
      <StatusDot status={job.status} />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-zinc-100">{job.file.name}</p>
        <p className="truncate text-sm text-zinc-400">
          {formatNumber(Math.ceil(job.file.size / 1024))} KB
          {job.status === "queued" && " · waiting"}
          {job.status === "running" && ` · chunking with ${tierName}…`}
          {job.status === "done" && ` · ${formatNumber(job.result!.chunks.length)} chunks with ${tierName}`}
          {job.status === "error" && <span className="text-rose-300"> · {job.error}</span>}
        </p>
      </div>
      {job.status === "done" && (
        <button
          type="button"
          onClick={onSelect}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            selected ? "bg-cyan-400/20 text-cyan-200" : "text-cyan-300 hover:bg-zinc-800"
          }`}
        >
          {selected ? "Viewing" : "View"}
        </button>
      )}
      {(job.status === "done" || job.status === "error") && !disabled && (
        <button
          type="button"
          onClick={onAgain}
          className="min-h-11 rounded-md px-3 py-1.5 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-800 md:min-h-0"
        >
          Chunk again
        </button>
      )}
      {!disabled && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${job.file.name}`}
          className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
            <path strokeLinecap="round" d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
      )}
    </li>
  );
}

function StatusDot({ status }: { status: Job["status"] }) {
  const tone = {
    queued: "bg-zinc-500",
    running: "bg-cyan-400 animate-pulse",
    done: "bg-emerald-400",
    error: "bg-rose-400",
  }[status];
  return <span aria-label={status} className={`h-2.5 w-2.5 shrink-0 rounded-full ${tone}`} />;
}

function StepTitle({ number, title }: { number: number; title: string }) {
  return (
    <h2 className="flex items-center gap-3 text-lg font-semibold text-zinc-100">
      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-zinc-800 text-sm text-cyan-300">
        {number}
      </span>
      {title}
    </h2>
  );
}

const FOUNDER_URL = "https://www.linkedin.com/in/ben-merrick-0835b4302/";

function FounderCard() {
  return (
    <a
      href={FOUNDER_URL}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex w-full flex-col gap-3 rounded-2xl border border-zinc-800 bg-zinc-900/60 p-4 transition-colors hover:border-cyan-400/40 hover:bg-zinc-900"
    >
      <div className="flex items-center gap-4">
        <img
          src="/ben-merrick.png"
          alt="Ben Merrick"
          className="h-16 w-16 shrink-0 rounded-full object-cover ring-2 ring-cyan-400/30 transition group-hover:ring-cyan-400/60"
        />
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="text-xs font-semibold tracking-wider text-cyan-300 uppercase">Founder</span>
          <span className="text-lg font-semibold text-zinc-50">Ben Merrick</span>
          <span className="inline-flex items-center gap-1.5 text-sm text-zinc-400 transition-colors group-hover:text-cyan-200">
            <LinkedInIcon />
            Connect on LinkedIn
          </span>
        </div>
      </div>
      <p className="border-t border-zinc-800 pt-3 text-sm leading-relaxed text-zinc-300">
        Dentist turned Developer - bringing a clinical mindset to the tech space.{" "}
        <span className="inline-flex items-center gap-1.5 font-semibold text-emerald-300">
          <span className="h-2 w-2 rounded-full bg-emerald-400" aria-hidden />I am open for work.
        </span>
      </p>
    </a>
  );
}

function LinkedInIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className="h-4 w-4 fill-current">
      <path d="M20.45 20.45h-3.55v-5.57c0-1.33-.03-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.35V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28zM5.34 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12zM7.12 20.45H3.56V9h3.56v11.45zM22.23 0H1.77C.79 0 0 .77 0 1.73v20.54C0 23.23.79 24 1.77 24h20.46c.98 0 1.77-.77 1.77-1.73V1.73C24 .77 23.21 0 22.23 0z" />
    </svg>
  );
}
