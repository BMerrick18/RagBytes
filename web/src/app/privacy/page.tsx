import type { Metadata } from "next";
import { DocSection, PageShell } from "@/components/PageShell";

export const metadata: Metadata = {
  title: "Privacy",
  description: "What RagBytes does with the documents you upload.",
};

const CONTACT_URL = "https://www.linkedin.com/in/ben-merrick-0835b4302/";

export default function PrivacyPage() {
  return (
    <PageShell
      title="Privacy"
      intro={<p>The short version: we chunk your document, send the chunks back, and keep none of it.</p>}
    >
      <DocSection title="Your documents">
        <ul className="flex list-disc flex-col gap-2 pl-5">
          <li>Uploads travel over HTTPS to our server, are chunked, and the chunks are returned in the same request.</li>
          <li>
            The file is held only while that request runs. It is never written to a database or file store, and it is
            discarded as soon as the response is sent.
          </li>
          <li>We don&apos;t read, sell, or train models on your documents or their chunks.</li>
          <li>
            Semantic chunking sends the passage text to OpenAI to decide where the meaning shifts. That text is
            discarded with the file when the response is sent. RagBytes uses its own OpenAI key. You are not asked
            for one. Basic and Structured stay on our server.
          </li>
          <li>Chunks are shown in your browser only. Closing or reloading the page clears them.</li>
        </ul>
      </DocSection>

      <DocSection title="What is recorded">
        <ul className="flex list-disc flex-col gap-2 pl-5">
          <li>
            We keep two running totals: how many documents have been chunked and how many chunks were made. They are
            plain numbers, with nothing about who uploaded what or what the documents said.
          </li>
          <li>
            Our server keeps short-lived technical logs of each request (time, address requested and response status)
            to keep the service running. They never include file contents.
          </li>
          <li>
            RagBytes is served through Cloudflare, which protects it from abuse and rate limits heavy use. Cloudflare
            handles requests under its own{" "}
            <a
              href="https://www.cloudflare.com/privacypolicy/"
              className="text-cyan-300 underline underline-offset-4 hover:text-cyan-200"
            >
              privacy policy
            </a>
            .
          </li>
          <li>
            We count visits with Cloudflare Web Analytics, which doesn&apos;t use cookies or follow you across sites.
          </li>
          <li>There are no accounts, no cookies and no advertising trackers.</li>
        </ul>
      </DocSection>

      <DocSection title="Where it runs">
        <p>The service runs on a DigitalOcean server in London, UK.</p>
      </DocSection>

      <DocSection title="Questions">
        <p>
          Message{" "}
          <a href={CONTACT_URL} className="text-cyan-300 underline underline-offset-4 hover:text-cyan-200">
            Ben Merrick on LinkedIn
          </a>
          .
        </p>
      </DocSection>
    </PageShell>
  );
}
