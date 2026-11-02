import { TIERS } from "@/lib/tiers";

const API_URL = process.env.RAGBYTE_API_URL ?? "http://127.0.0.1:8000";

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
