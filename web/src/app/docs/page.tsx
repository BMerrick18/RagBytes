import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense, type ReactNode } from "react";
import { ApiPlayground } from "@/components/ApiPlayground";
import { EndpointRow } from "@/components/EndpointRow";
import { Code, CodeBlock, DocSection, PageShell } from "@/components/PageShell";
import { RunnableGet } from "@/components/RunnableGet";
import { ACCEPTED_EXTENSIONS, TIERS } from "@/lib/tiers";

export const metadata: Metadata = {
  title: "API docs",
  description: "Chunk documents from your own code with the RagBytes HTTP API.",
};

const EXAMPLE_RESPONSE = `{
  "filename": "guide.md",
  "file_id": "6f1c…",
  "chunks": [
    {
      "chunk_id": "b2e4…",
      "metadata": {
        "filename": "guide.md",
        "file_id": "6f1c…",
        "chunk_number": 0,
        "title": "Guide",
        "headings": ["Install"],
        "heading": "Install",
        "subheading": null,
        "page": null,
        "format": "text",
        "media_type": null,
        "details": { "start": 0, "end": 20 }
      },
      "embed_text": "Guide > Install\\n\\nInstall the package.",
      "content": "Install the package."
    }
  ]
}`;

export default function ApiDocsPage() {
  return (
    <PageShell
      title="RagBytes API"
      intro={
        <p>
          Everything the website does is available over HTTP. Send a document, get back chunks that are ready to embed.
          No account or key is needed.
        </p>
      }
    >
      <Suspense fallback={<p className="text-zinc-500">Loading…</p>}>
        <ApiDocs />
      </Suspense>
    </PageShell>
  );
}

async function ApiDocs() {
  await connection();
  const base = (process.env.RAGBYTE_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
  return (
    <>
      <div className="flex flex-wrap gap-3">
        <DocLink href={`${base}/docs`} primary>
          Try it in Swagger UI
        </DocLink>
        <DocLink href={`${base}/redoc`}>Reference (ReDoc)</DocLink>
        <DocLink href={`${base}/openapi.json`}>OpenAPI spec (openapi.json)</DocLink>
      </div>

      <DocSection title="Base URL">
        <CodeBlock>{base}</CodeBlock>
      </DocSection>

      <DocSection title="Try it">
        <p>
          Each tier has its own endpoint. Upload the file to it as <Code>multipart/form-data</Code> in a field
          called <Code>file</Code>. Pick a tier and a document below, copy the code, or send the request straight from
          this page.
        </p>
        <ApiPlayground base={base} />
      </DocSection>

      <DocSection title="Chunking endpoints">
        <p>
          Each tier takes the same file upload and returns the same response. Semantic sends the passage text to
          OpenAI to find the cuts, then discards it. Supported file types:{" "}
          {ACCEPTED_EXTENSIONS.join(", ")}.
        </p>
        <ul className="flex flex-col divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900/40">
          {TIERS.map((tier) => (
            <EndpointRow key={tier.id} verb="POST" path={`/v1/chunk/${tier.id}`} soon={!tier.available}>
              <span className="font-medium text-zinc-100">{tier.name}.</span> {tier.description}
            </EndpointRow>
          ))}
        </ul>
        <p>
          Semantic also takes optional form fields. <Code>style</Code> is <Code>precise</Code> for small, focused
          chunks, <Code>balanced</Code> (the default) for general search, or <Code>broad</Code> for larger chunks
          that keep more context. <Code>strict_headings=true</Code> stops very short neighbouring headings from
          sharing a chunk. <Code>max_chunk_chars</Code> caps the chunk size, from 500 to 8,000 characters. The
          response repeats the settings it used under <Code>options</Code>.
        </p>
      </DocSection>

      <DocSection title="Other endpoints">
        <ul className="flex flex-col divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900/40">
          <RunnableGet base={base} path="/v1/methods">
            List the available tiers, the endpoint for each, and the file types the service accepts.
          </RunnableGet>
          <RunnableGet base={base} path="/v1/stats">
            See how many documents have been chunked and how many chunks were made. Only these two totals are kept.
          </RunnableGet>
          <RunnableGet base={base} path="/health">
            Check the service is up and see which build it is running.
          </RunnableGet>
        </ul>
      </DocSection>

      <DocSection title="Response">
        <p>
          Chunks come back in document order. For each one, send <Code>embed_text</Code> to your embedding model and
          store <Code>content</Code> and <Code>metadata</Code> next to the vector.
        </p>
        <ul className="flex list-disc flex-col gap-2 pl-5">
          <li>
            <Code>embed_text</Code> is the heading path, a blank line, then the chunk&apos;s text. The heading path
            tells the embedding model where the chunk sits in the document.
          </li>
          <li>
            <Code>metadata.title</Code> is the document&apos;s title when one heading sits above all the others, such
            as the name at the top of a CV. It starts the path in <Code>embed_text</Code> but is left out of{" "}
            <Code>headings</Code>, so <Code>heading</Code> is the section itself, such as Experience.
          </li>
          <li>
            <Code>content</Code> is the chunk&apos;s text, or base64 bytes when <Code>metadata.media_type</Code> is
            an image type.
          </li>
          <li>
            <Code>metadata.format</Code> is one of text, list, table, image, chart, code or complex.
          </li>
          <li>
            <Code>metadata.page</Code> is the page number for PDFs, otherwise null.
          </li>
        </ul>
        <CodeBlock label="200 OK">{EXAMPLE_RESPONSE}</CodeBlock>
      </DocSection>

      <DocSection title="Errors and limits">
        <p>
          Errors return JSON with a <Code>detail</Code> message.
        </p>
        <ul className="flex flex-col divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900/40">
          <Status code="400">The file could not be read.</Status>
          <Status code="404">No such tier, or the tier isn&apos;t available yet.</Status>
          <Status code="413">The upload is over 50 MB.</Status>
          <Status code="415">The filename suffix isn&apos;t a supported file type.</Status>
          <Status code="422">A semantic option is not one of the allowed values.</Status>
          <Status code="502">Semantic could not embed the document. The file was discarded.</Status>
          <Status code="503">Semantic chunking is not configured on the server.</Status>
          <Status code="429">
            More than 10 chunking requests in 10 seconds from your address. Wait 10 seconds and retry.
          </Status>
          <Status code="524">The document took longer than about 100 seconds to process. Try splitting it.</Status>
        </ul>
      </DocSection>
    </>
  );
}

function DocLink({ href, primary, children }: { href: string; primary?: boolean; children: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={
        primary
          ? "inline-flex min-h-11 items-center rounded-lg bg-cyan-400 px-4 py-2 font-semibold text-zinc-950 transition-colors hover:bg-cyan-300 md:min-h-0"
          : "inline-flex min-h-11 items-center rounded-lg border border-zinc-700 px-4 py-2 font-medium text-zinc-200 transition-colors hover:border-zinc-500 hover:bg-zinc-900 md:min-h-0"
      }
    >
      {children}
    </a>
  );
}

function Status({ code, children }: { code: string; children: ReactNode }) {
  return (
    <li className="flex gap-4 px-4 py-3 text-sm">
      <span className="w-10 shrink-0 font-mono font-semibold text-zinc-100">{code}</span>
      <span className="text-zinc-400">{children}</span>
    </li>
  );
}
