"use client";

import { useRef, useState } from "react";
import { ApiResponse, callApi, type ApiResult } from "@/components/ApiResponse";
import { CodeBlock } from "@/components/PageShell";
import { SemanticOptionsPanel } from "@/components/SemanticOptionsPanel";
import { loadSampleDocument } from "@/lib/sample";
import {
  DEFAULT_SEMANTIC_OPTIONS,
  maxChunkCharsProblem,
  semanticFields,
  type SemanticOptions,
} from "@/lib/semantic";
import { formatNumber } from "@/lib/stats";
import { ACCEPTED_EXTENSIONS, isAccepted, TIERS } from "@/lib/tiers";

type Language = "curl" | "python" | "javascript";

const LANGUAGES: { id: Language; label: string }[] = [
  { id: "curl", label: "curl" },
  { id: "python", label: "Python" },
  { id: "javascript", label: "JavaScript" },
];

function snippet(language: Language, url: string, filename: string, fields: [string, string][]): string {
  switch (language) {
    case "curl":
      return ["curl", `-F "file=@${filename}"`, ...fields.map(([name, value]) => `-F "${name}=${value}"`), url].join(
        fields.length > 0 ? " \\\n  " : " ",
      );
    case "python": {
      const data = fields.length
        ? `\n        data={${fields.map(([name, value]) => `"${name}": "${value}"`).join(", ")}},`
        : "";
      return `import requests

with open("${filename}", "rb") as f:
    response = requests.post(
        "${url}",
        files={"file": f},${data}
        timeout=120,
    )
response.raise_for_status()

for chunk in response.json()["chunks"]:
    vector = embed(chunk["embed_text"])  # your embedding model
    store(vector, chunk["content"], chunk["metadata"])`;
    }
    case "javascript":
      return `const form = new FormData();
form.append("file", file); // a File, e.g. from <input type="file">: ${filename}
${fields.map(([name, value]) => `form.append("${name}", "${value}");\n`).join("")}
const response = await fetch("${url}", { method: "POST", body: form });
if (!response.ok) throw new Error((await response.json()).detail);
const { chunks } = await response.json();
console.log(chunks.length, "chunks");`;
  }
}

function countChunks(result: ApiResult): string | undefined {
  if (!result.ok || typeof result.body !== "object" || result.body === null) return undefined;
  const chunks = (result.body as { chunks?: unknown[] }).chunks;
  return Array.isArray(chunks) ? `${formatNumber(chunks.length)} chunks` : undefined;
}

export function ApiPlayground({ base }: { base: string }) {
  const available = TIERS.filter((tier) => tier.available);
  const [tier, setTier] = useState(available[0].id);
  const [language, setLanguage] = useState<Language>("curl");
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ApiResult | null>(null);
  const [semantic, setSemantic] = useState<SemanticOptions>(DEFAULT_SEMANTIC_OPTIONS);
  const input = useRef<HTMLInputElement>(null);

  const url = `${base}/v1/chunk/${tier}`;
  const filename = file?.name ?? "report.pdf";
  const fields = tier === "semantic" ? semanticFields(semantic) : [];
  const optionsInvalid = tier === "semantic" && maxChunkCharsProblem(semantic.maxChunkChars) !== null;

  function choose(chosen: File | undefined) {
    setResult(null);
    if (!chosen) return;
    if (!isAccepted(chosen)) {
      setProblem(`${chosen.name} isn't a supported file type.`);
      return;
    }
    setProblem(null);
    setFile(chosen);
  }

  async function pickSample() {
    try {
      choose(await loadSampleDocument());
    } catch (error) {
      setProblem(error instanceof Error ? error.message : String(error));
    }
  }

  async function send() {
    if (!file) return;
    setRunning(true);
    const form = new FormData();
    form.append("file", file);
    for (const [name, value] of fields) form.append(name, value);
    setResult(await callApi(url, { method: "POST", body: form }));
    setRunning(false);
  }

  return (
    <div className="flex flex-col gap-5 rounded-2xl border border-zinc-800 bg-zinc-900/30 p-5">
      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium text-zinc-300">1. Pick a tier</span>
        <div className="flex flex-wrap gap-2">
          {available.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => {
                setTier(option.id);
                setResult(null);
              }}
              aria-pressed={tier === option.id}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                tier === option.id
                  ? "bg-cyan-400/15 text-cyan-200 ring-1 ring-cyan-400/50"
                  : "border border-zinc-700 text-zinc-300 hover:border-zinc-500"
              }`}
            >
              {option.name}
            </button>
          ))}
        </div>
        {tier === "semantic" && (
          <SemanticOptionsPanel
            value={semantic}
            onChange={(options) => {
              setSemantic(options);
              setResult(null);
            }}
            disabled={running}
          />
        )}
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium text-zinc-300">2. Choose a document</span>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <button
            type="button"
            onClick={() => input.current?.click()}
            className="rounded-lg border border-zinc-700 px-3 py-1.5 font-medium text-zinc-200 transition-colors hover:border-zinc-500"
          >
            Choose file
          </button>
          <button
            type="button"
            onClick={pickSample}
            className="rounded-lg border border-cyan-400/30 bg-cyan-400/10 px-3 py-1.5 font-medium text-cyan-200 transition-colors hover:border-cyan-400/60"
          >
            Use the sample report
          </button>
          <span className="text-zinc-400">
            {file ? `${file.name} (${formatNumber(Math.ceil(file.size / 1024))} KB)` : "No file chosen"}
          </span>
          <input
            ref={input}
            type="file"
            accept={ACCEPTED_EXTENSIONS.join(",")}
            className="hidden"
            onChange={(event) => {
              choose(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </div>
        {problem && <p className="text-sm text-amber-300">{problem}</p>}
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium text-zinc-300">3. The request</span>
        <div className="flex flex-wrap gap-1 self-start rounded-md bg-zinc-800/80 p-0.5 text-xs">
          {LANGUAGES.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setLanguage(option.id)}
              className={`rounded px-2.5 py-1 transition-colors ${
                language === option.id ? "bg-zinc-700 text-zinc-100" : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
        <CodeBlock>{snippet(language, url, filename, fields)}</CodeBlock>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={send}
          disabled={!file || running || optionsInvalid}
          className="rounded-lg bg-cyan-400 px-5 py-2.5 font-semibold text-zinc-950 transition-colors hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400"
        >
          {running ? "Sending…" : "Send request"}
        </button>
        <span className="text-sm text-zinc-500">
          {file
            ? `Sends ${file.name} from your browser to ${url}. Nothing is stored.`
            : "Choose a file or use the sample report to run this request."}
        </span>
      </div>

      {result && <ApiResponse result={result} summary={countChunks(result)} />}
    </div>
  );
}
