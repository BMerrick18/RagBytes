export interface Tier {
  /** The tier name in the backend, served at POST /v1/chunk/<id>. */
  id: string;
  name: string;
  tagline: string;
  description: string;
  available: boolean;
}

export const TIERS: Tier[] = [
  {
    id: "basic",
    name: "Basic",
    tagline: "Fixed-size chunks",
    description:
      "Cuts the document about every 500 characters, including across headings. A sentence that would pass that limit starts the next chunk. A sentence longer than 500 characters is split at the word boundary closest to 500. Images, charts, and complex regions stay whole.",
    available: true,
  },
  {
    id: "structured",
    name: "Structured",
    tagline: "Follows titles and sections",
    description:
      "One chunk per heading and subheading, with no minimum length. A short subsection stays its own chunk, and a section is split only once it passes about 2,000 characters. When a paragraph is split, the next chunk repeats its last sentence.",
    available: true,
  },
  {
    id: "semantic",
    name: "Semantic",
    tagline: "Splits where the meaning changes",
    description:
      "Embeds neighbouring passages and starts a new chunk where the meaning shifts. A chunk stays inside its heading, except that very short neighbouring headings on the same subject can share one. The passage text is sent to OpenAI for those embeddings and then discarded.",
    available: true,
  },
  {
    id: "enriched",
    name: "Enriched",
    tagline: "Adds context with a language model",
    description:
      "Adds a summary, keywords and document context to every chunk, and describes images and diagrams.",
    available: false,
  },
];

export const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".html", ".htm", ".md", ".markdown", ".txt"];

export function isAccepted(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((extension) => name.endsWith(extension));
}
