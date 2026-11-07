import { TIERS } from "@/lib/tiers";

const API_URL = process.env.RAGBYTE_API_URL ?? "http://127.0.0.1:8000";
// The API validates these values and answers 422 when one is not allowed.
const SEMANTIC_FIELDS = ["style", "strict_headings", "max_chunk_chars"];

export async function POST(request: Request) {
  const form = await request.formData();
  const file = form.get("file");
  const tier = String(form.get("method") ?? "basic");
  if (!(file instanceof File)) {
    return Response.json({ detail: "No file was uploaded." }, { status: 400 });
  }
  if (!TIERS.some((option) => option.id === tier && option.available)) {
    return Response.json({ detail: `Unknown chunking tier: ${tier}` }, { status: 400 });
  }

  const upstream = new FormData();
  upstream.append("file", file, file.name);
  if (tier === "semantic") {
    for (const field of SEMANTIC_FIELDS) {
      const value = form.get(field);
      if (typeof value === "string" && value !== "") upstream.append(field, value);
    }
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}/v1/chunk/${tier}`, {
      method: "POST",
      body: upstream,
    });
  } catch {
    return Response.json(
      { detail: `Could not reach the chunking service at ${API_URL}. Is it running?` },
      { status: 502 },
    );
  }

  return new Response(response.body, {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
  });
}
