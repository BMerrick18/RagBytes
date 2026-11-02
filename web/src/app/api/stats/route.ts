import { connection } from "next/server";

const API_URL = process.env.RAGBYTE_API_URL ?? "http://127.0.0.1:8000";

export async function GET() {
  await connection();
  try {
    const response = await fetch(`${API_URL}/v1/stats`, { signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error(`API stats returned ${response.status}`);
    return Response.json(await response.json());
  } catch {
    return Response.json({ detail: "The usage totals are unavailable." }, { status: 503 });
  }
}
