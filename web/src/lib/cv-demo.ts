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
    chunks: [
      {
        ...data.tiers.basic[0],
        why: "The opening note, both bread paragraphs, and the first sentence of The till land in one chunk. The heading change does not start a new one.",
      },
      {
        ...data.tiers.basic[1],
        why: "The rest of the till sentence starts this chunk, which then runs on through the closing routine and the tax note.",
      },
    ],
    illustration: false,
    explanation:
      "Basic joins the note into one stream and cuts it about every 500 characters, even across a heading. The first chunk stops after “The card machine settles overnight.” The next sentence of The till is pushed into the following chunk, along with Before you leave. Keeping each heading whole is what Structured does.",
  },
  structured: {
    chunks: [
      {
        ...data.tiers.structured[0],
        why: "The opening note stays its own chunk because it sits under the title.",
      },
      {
        ...data.tiers.structured[1],
        why: "The bread starts a new chunk because the heading changed. The white loaves and the rye loaves stay together.",
      },
      {
        ...data.tiers.structured[2],
        why: "The till is one chunk again, so the sentence Basic split in half is whole.",
      },
      {
        ...data.tiers.structured[3],
        why: "Before you leave stays one chunk. The tax note is still glued to the closing routine, because they share a heading.",
      },
    ],
    illustration: false,
    explanation:
      "Structured starts a new chunk at each heading. The till is whole again, and the two bread paragraphs stay together because they share a heading. Before you leave is also one chunk, so the council-tax note is still attached to locking up. Splitting that change of subject is what Semantic does.",
  },
  semantic: {
    illustration: true,
    explanation:
      "Semantic keeps the heading rule, so The till stays separate and the two bread paragraphs stay together. Under Before you leave the subject changes: locking up is one chunk, and the council-tax note starts another. Only very short neighbouring headings on the same subject share a chunk.",
    chunks: [
      {
        sections: [0],
        topic: "The handover",
        why: "The opening note is its own heading, so it stays its own chunk.",
      },
      {
        sections: [1, 2],
        topic: "The bread",
        why: "The white loaves and the rye loaves are the same subject, so they stay together.",
      },
      {
        sections: [3],
        topic: "The till",
        why: "The till is short, so it is compared with the bread, but it is a different subject and starts its own chunk.",
      },
      {
        sections: [4],
        topic: "Locking up",
        why: "This paragraph is about closing the shop.",
      },
      {
        sections: [5],
        topic: "The tax note",
        why: "The council-tax note is a different subject under the same heading, so it starts a new chunk.",
      },
    ],
  },
  llm: {
    illustration: true,
    explanation:
      "LLM sends the file and writes the topic chunks. The wording, heading, and page come back on each chunk.",
    chunks: [
      {
        sections: [0],
        topic: "The handover",
        why: "The opening note is one topic, so it stays its own chunk.",
      },
      {
        sections: [1, 2],
        topic: "The bread",
        why: "The white loaves and the rye loaves are the same topic.",
      },
      {
        sections: [3],
        topic: "The till",
        why: "The till is a new topic, so it starts a new chunk.",
      },
      {
        sections: [4, 5],
        topic: "Closing and the tax note",
        why: "The model groups these two short notes. A real figure on the page would be a chunk of its own.",
      },
    ],
  },
  enriched: {
    illustration: true,
    explanation:
      "Enriched will take these chunks and add a summary, keywords and document context, so a search for “household bill” finds the tax note even though those words are not in it.",
    chunks: [
      {
        sections: [0, 1, 2],
        summary: "Sunday opening notes for the bakery, including oven time and crust for the white and rye loaves.",
        keywords: ["handover", "oven", "rye", "white loaves"],
        why: "“Handover” is added as a keyword, although the note only says it was written for the person who opens on Sunday.",
      },
      {
        sections: [3],
        summary: "Count a fifty-pound float before the first customer and keep the notes in the blue tin.",
        keywords: ["cash float", "card machine", "blue tin"],
        why: "The summary names the job, counting the float, so a question about the morning cash finds this chunk.",
      },
      {
        sections: [4],
        summary: "Closing routine: ovens off, counters wiped, door locked, alarm set, and the cash drawer left open.",
        keywords: ["closing routine", "alarm", "cash drawer"],
        why: "The summary turns the closing list into one line someone can search for.",
      },
      {
        sections: [5],
        summary: "The flat upstairs has a council-tax payment due on Monday, paid from the personal account.",
        keywords: ["household bill", "council tax", "personal account"],
        why: "“Household bill” is added as a keyword, although the paragraph never uses those words.",
      },
    ],
  },
};
