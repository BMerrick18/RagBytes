import { connection } from "next/server";

const API_URL = process.env.RAGBYTE_API_URL ?? "http://127.0.0.1:8000";

export async function GET() {
  await connection();
  const web = process.env.RAGBYTE_VERSION ?? "dev";

  try {
    const response = await fetch(`${API_URL}/health`, { signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error(`API health returned ${response.status}`);
    const api: { version: string } = await response.json();
    return Response.json({ status: "ok", web, api: api.version });
  } catch {
    return Response.json({ status: "degraded", web, api: null }, { status: 503 });
  }
}
