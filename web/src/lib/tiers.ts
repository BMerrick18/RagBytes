export interface Tier {
  /** The tier name in the backend, served at POST /v1/chunk/<id>. */
  id: string;
  name: string;
  tagline: string;
  description: string;
  /** False disables choosing this tier and rejects it on the website upload route. */
  available: boolean;
  /** False hides the tier. The implementation stays in the repo. */
  listed: boolean;
}

export const TIERS: Tier[] = [
  {
    id: "basic",
    name: "Basic",
    tagline: "Fixed-size chunks",
    description:
      "Cuts the document about every 500 characters, including across headings. A sentence that would pass that limit starts the next chunk. A sentence longer than 500 characters is split at the word boundary closest to 500. Images, charts, and complex regions stay whole.",
    available: true,
    listed: true,
  },
  {
    id: "structured",
    name: "Structured",
    tagline: "Follows titles and sections",
    description:
      "One chunk per heading and subheading, with no minimum length. A short subsection stays its own chunk, and a section is split only once it passes about 2,000 characters. When a paragraph is split, the next chunk repeats its last sentence.",
    available: true,
    listed: true,
  },
  {
    id: "semantic",
    name: "Semantic",
    tagline: "Splits where the meaning changes",
    description:
      "Embeds neighbouring passages and starts a new chunk where the meaning shifts. A chunk stays inside its heading, except that very short neighbouring headings on the same subject can share one. The passage text is sent to OpenAI for those embeddings and then discarded.",
    // Shown grayed out, like Enriched. Set available and RAGBYTES_SEMANTIC_ENABLED to publish it again.
    available: false,
    listed: true,
  },
  {
    id: "llm",
    name: "LLM",
    tagline: "Splits where the topic changes",
    description:
      "Sends the uploaded file to a language model and asks for written chunks by topic. The file is not extracted first. The model copies each chunk's wording and fills its heading, page, and format. A long file is sent again until the model reaches the end, then the file is discarded.",
    available: process.env.NEXT_PUBLIC_RAGBYTE_LLM_ENABLED === "true",
    listed: process.env.NEXT_PUBLIC_RAGBYTE_LLM_ENABLED === "true",
  },
  {
    id: "enriched",
    name: "Enriched",
    tagline: "Adds context with a language model",
    description:
      "Adds a summary, keywords and document context to every chunk, and describes images and diagrams.",
    available: false,
    listed: true,
  },
];

export const LISTED_TIERS = TIERS.filter((tier) => tier.listed);

export function isOffered(id: string): boolean {
  return TIERS.some((tier) => tier.id === id && tier.listed && tier.available);
}

export const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".html", ".htm", ".md", ".markdown", ".txt"];

export function isAccepted(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((extension) => name.endsWith(extension));
}
