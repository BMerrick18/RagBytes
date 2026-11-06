import data from "@/lib/cv-demo.json";

export interface DemoSection {
  heading: string;
  kind: string;
  chars: number;
  preview: string;
  /** The section as it appears in the document, before chunking. */
  text: string;
}

/** One section, or run of sections under one heading, and why it started or joined its chunk. */
export interface DemoStep {
  sections: number[];
  chars: number;
  reason: string;
}

export interface DemoChunk {
  /** Indexes into DEMO_CV.sections, in document order. */
  sections: number[];
  chars?: number;
  /** Exact chunk text, when the tier cuts on a character count rather than whole sections. */
  text?: string;
  headings?: string[];
  steps?: DemoStep[];
  why?: string;
  topic?: string;
  summary?: string;
  keywords?: string[];
}

const BASIC = data.limits.chunk_size.toLocaleString("en-GB");
const STRUCTURED = data.limits.structured_chunk_size.toLocaleString("en-GB");

/** Steps whose reason is in this set joined the chunk before them; the rest started a chunk. */
export const JOIN_REASONS = new Set(["same_heading"]);

export const REASONS: Record<string, string> = {
  first: "Starts the first chunk.",
  new_heading: "Starts a new chunk because the heading or subheading changed.",
  full: `Starts a new chunk because the next sentence would pass ${BASIC} characters.`,
  kept_whole: "Stays its own chunk because images, charts, and complex regions are not cut into the character windows.",
  same_heading: `Joins the chunk: it sits under the same heading, and the chunk still fits in ${STRUCTURED} characters.`,
  too_long: `Starts a new chunk because joining would take the chunk past ${STRUCTURED} characters.`,
};

export interface DemoTier {
  chunks: DemoChunk[];
  /** True when the chunks are drawn by hand because the tier isn't built yet. */
  illustration: boolean;
  explanation: string;
}

/** Real output of the available chunkers on the sample report, written by scripts/build_cv_demo.py. */
export const DEMO_CV: { title: string; sections: DemoSection[] } = data;

export const DEMO_TIERS: Record<string, DemoTier> = {
  basic: {
    chunks: data.tiers.basic,
    illustration: false,
    explanation:
      "Basic joins the report into one stream and cuts it about every 500 characters, even across a heading. A sentence that would pass the limit moves into the next chunk. A sentence longer than 500 characters is split at the word boundary closest to 500. Keeping a heading and its text together is what Structured does.",
  },
  structured: {
    chunks: data.tiers.structured,
    illustration: false,
    explanation:
      "Structured starts a new chunk at each heading and subheading, with no minimum length. Text under that heading stays together until it would pass about 2,000 characters. The one-line readings note stays with the readings, because it has the same heading. Follow-up is its own chunk even though it is short, and the heading is stored on the chunk.",
  },
  semantic: {
    illustration: true,
    explanation:
      "Semantic embeds neighbouring passages and starts a new chunk where the meaning shifts. A chunk stays inside its heading. On the Readings heading, the date and the weather can stay together while the lux list starts a new chunk. Follow-up stays separate because it is the next heading.",
    chunks: [
      {
        sections: [0],
        topic: "The title",
        why: "The title is its own heading, so it is its own chunk.",
      },
      {
        sections: [1],
        topic: "The aim",
        why: "Overview is the next heading. The comparison never crosses that line.",
      },
      {
        sections: [2],
        topic: "The kit",
        why: "The kit list is one short list under its own heading, so it stays whole.",
      },
      {
        sections: [3, 4],
        topic: "North Pier",
        why: "Both passages sit under North Pier and describe the same stretch of the trial.",
      },
      {
        sections: [5, 6],
        topic: "The night",
        why: "The date and the weather are the same moment, so they stay together.",
      },
      {
        sections: [7],
        topic: "The measurements",
        why: "The lux readings are a shift in subject under Readings, so they start a new chunk.",
      },
      {
        sections: [8, 9],
        topic: "The method",
        why: "The walk and the sodium baseline are both how the trial was run.",
      },
      {
        sections: [10],
        topic: "Follow-up",
        why: "Follow-up is a new heading, so it starts a new chunk even when the subject is close.",
      },
      {
        sections: [11, 12],
        topic: "Who to ask",
        why: "The two contact lines share a heading and a subject.",
      },
    ],
  },
  enriched: {
    illustration: true,
    explanation:
      "Enriched will take well-shaped chunks and have a language model add a summary, keywords and document context to each, so a search for “quay lighting trial” finds the right chunk even when those exact words aren't in it.",
    chunks: [
      {
        sections: [0, 1, 2],
        summary: "A one-week trial of warmer quay lighting on North Pier, using warm-white LED heads, a lux meter and the existing painted marks.",
        keywords: ["quay lighting", "North Pier", "LED", "lux meter"],
        why: "The summary puts the aim and the kit in one line, so it matches a question about either.",
      },
      {
        sections: [3, 4],
        summary: "On North Pier, crews could read bollard numbers from further away, with less glare on the water, though a shadow remains behind each bollard.",
        keywords: ["bollards", "glare", "drizzle", "pier lighting"],
        why: "“Pier lighting” is added as a keyword, although the text only describes lamps, glare and bollard numbers.",
      },
      {
        sections: [5, 6, 7, 8, 9, 10, 11, 12],
        summary: "Readings from the night of 12 March, the walk used each night, follow-up work on South Pier, and two office contacts.",
        keywords: ["12 March", "method", "South Pier", "contacts"],
        why: "The summary pulls out what someone would search for: the date, the method and who to ask.",
      },
    ],
  },
};
