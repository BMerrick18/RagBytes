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
      "Semantic will embed each passage and cut where the meaning shifts, whatever the headings say. The kit list and the North Pier observations would stay together because they describe the same trial, while the night readings and the follow-up separate.",
    chunks: [
      {
        sections: [0, 1],
        topic: "What the trial is",
        why: "The opening line and the overview both introduce the lighting trial, so their meaning is close enough to stay together.",
      },
      {
        sections: [2, 3, 4],
        topic: "Kit and North Pier",
        why: "The kit list and the North Pier notes name the same lamps and describe what they did on the pier, so the topic carries on across the heading.",
      },
      {
        sections: [5, 6, 7],
        topic: "One night's readings",
        why: "The language turns from the week's setup to the measurements on 12 March, so a new chunk starts here.",
      },
      {
        sections: [8, 9, 10],
        topic: "How it was run",
        why: "The walk, the sodium baseline and the follow-up are all about running the trial, so they're grouped even though Follow-up has its own heading.",
      },
      {
        sections: [11, 12],
        topic: "Who to ask",
        why: "Office names and contact details are a clear change of subject.",
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
