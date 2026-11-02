/**
 * Wise Mind Coach — Cloudflare Worker.
 *
 * Serves the chat page from ./public and answers POST /chat by streaming a
 * reply from the Anthropic API. The API key stays server-side. A single
 * Durable Object enforces a per-visitor hourly message limit and a hard
 * daily spending cap, so a public link cannot run up a surprise bill.
 *
 * Edit src/prompt.md to change the coach's behavior (like program.md in the
 * parent repo); edit wrangler.jsonc "vars" to change limits and model.
 */
import Anthropic from "@anthropic-ai/sdk";
import { DurableObject } from "cloudflare:workers";
import PROMPT from "./prompt.md";

export interface Env {
  ANTHROPIC_API_KEY: string;
  IP_SALT: string;
  LIMITER: DurableObjectNamespace<Limiter>;
  MODEL: string;
  MAX_TOKENS: string;
  MESSAGES_PER_HOUR: string;
  DAILY_BUDGET_USD: string;
  INPUT_PRICE_PER_MTOK: string;
  OUTPUT_PRICE_PER_MTOK: string;
}

const MAX_TURNS = 16; // conversation turns sent to the model
const MAX_CHARS = 2000; // per user message

type Turn = { role: "user" | "assistant"; content: string };

// ---------------------------------------------------------------------------
// Limiter: one global Durable Object (strongly consistent, free-plan friendly).
// ---------------------------------------------------------------------------

export class Limiter extends DurableObject<Env> {
  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    ctx.storage.sql.exec(`
      CREATE TABLE IF NOT EXISTS hits (visitor TEXT, hour INTEGER, n INTEGER,
        PRIMARY KEY (visitor, hour));
      CREATE TABLE IF NOT EXISTS spend (day TEXT PRIMARY KEY, usd REAL);
    `);
  }

  /** Reserve one message for this visitor, or say why not. */
  admit(visitor: string, perHour: number, budgetUsd: number): { ok: true } | { ok: false; reason: "rate" | "budget" } {
    const sql = this.ctx.storage.sql;
    const hour = Math.floor(Date.now() / 3_600_000);
    const day = new Date().toISOString().slice(0, 10);

    sql.exec("DELETE FROM hits WHERE hour < ?", hour);
    sql.exec("DELETE FROM spend WHERE day < ?", day);

    const spent = sql.exec<{ usd: number }>("SELECT usd FROM spend WHERE day = ?", day).toArray()[0]?.usd ?? 0;
    if (spent >= budgetUsd) return { ok: false, reason: "budget" };

    const n = sql.exec<{ n: number }>("SELECT n FROM hits WHERE visitor = ? AND hour = ?", visitor, hour).toArray()[0]?.n ?? 0;
    if (n >= perHour) return { ok: false, reason: "rate" };

    sql.exec(
      "INSERT INTO hits (visitor, hour, n) VALUES (?, ?, 1) ON CONFLICT(visitor, hour) DO UPDATE SET n = n + 1",
      visitor, hour,
    );
    return { ok: true };
  }

  /** Add the actual cost of a finished reply to today's total. */
  record(usd: number): void {
    const day = new Date().toISOString().slice(0, 10);
    this.ctx.storage.sql.exec(
      "INSERT INTO spend (day, usd) VALUES (?, ?) ON CONFLICT(day) DO UPDATE SET usd = usd + ?",
      day, usd, usd,
    );
  }

  /** Today's spend, for the /status endpoint. */
  today(): { day: string; usd: number } {
    const day = new Date().toISOString().slice(0, 10);
    const usd = this.ctx.storage.sql.exec<{ usd: number }>("SELECT usd FROM spend WHERE day = ?", day).toArray()[0]?.usd ?? 0;
    return { day, usd };
  }
}

// ---------------------------------------------------------------------------
// Request handling
// ---------------------------------------------------------------------------

async function visitorId(req: Request, salt: string): Promise<string> {
  // Store a salted hash, never the raw IP.
  const ip = req.headers.get("CF-Connecting-IP") ?? "unknown";
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(salt + ip));
  return [...new Uint8Array(bytes).slice(0, 12)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function parseTurns(body: unknown): Turn[] | null {
  const msgs = (body as { messages?: unknown })?.messages;
  if (!Array.isArray(msgs) || msgs.length === 0) return null;
  const turns: Turn[] = [];
  for (const m of msgs) {
    const role = (m as Turn)?.role;
    const content = (m as Turn)?.content;
    if ((role !== "user" && role !== "assistant") || typeof content !== "string" || !content.trim()) return null;
    turns.push({ role, content: content.slice(0, MAX_CHARS) });
  }
  // Keep the most recent turns, starting and ending on a user turn.
  let recent = turns.slice(-MAX_TURNS);
  while (recent.length && recent[0].role !== "user") recent = recent.slice(1);
  if (!recent.length || recent[recent.length - 1].role !== "user") return null;
  return recent;
}

const json = (obj: unknown, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json" } });

async function chat(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return json({ error: "bad_request" }, 400);
  }
  const messages = parseTurns(body);
  if (!messages) return json({ error: "bad_request" }, 400);

  const limiter = env.LIMITER.get(env.LIMITER.idFromName("global"));
  const verdict = await limiter.admit(
    await visitorId(req, env.IP_SALT ?? ""),
    Number(env.MESSAGES_PER_HOUR),
    Number(env.DAILY_BUDGET_USD),
  );
  if (!verdict.ok) return json({ error: verdict.reason }, 429);

  const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY });
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();
  const enc = new TextEncoder();
  const send = (obj: unknown) => writer.write(enc.encode(`data: ${JSON.stringify(obj)}\n\n`));

  const run = async () => {
    try {
      const stream = client.messages.stream({
        model: env.MODEL,
        max_tokens: Number(env.MAX_TOKENS),
        system: PROMPT,
        messages,
      });
      for await (const event of stream) {
        if (event.type === "content_block_delta" && event.delta.type === "text_delta") {
          await send({ text: event.delta.text });
        }
      }
      const final = await stream.finalMessage();
      const u = final.usage;
      const inTok = u.input_tokens + (u.cache_creation_input_tokens ?? 0) * 1.25 + (u.cache_read_input_tokens ?? 0) * 0.1;
      const usd = (inTok * Number(env.INPUT_PRICE_PER_MTOK) + u.output_tokens * Number(env.OUTPUT_PRICE_PER_MTOK)) / 1e6;
      await limiter.record(usd);
      if (final.stop_reason === "refusal") await send({ error: "refused" });
      await send({ done: true });
    } catch (e) {
      const code = e instanceof Anthropic.RateLimitError ? "busy" : "upstream";
      console.error("chat failed", e instanceof Anthropic.APIError ? e.status : "", String(e));
      await send({ error: code }).catch(() => {});
    } finally {
      await writer.close().catch(() => {});
    }
  };
  ctx.waitUntil(run());

  return new Response(readable, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
  });
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname === "/chat" && req.method === "POST") return chat(req, env, ctx);
    if (url.pathname === "/status" && req.method === "GET") {
      const limiter = env.LIMITER.get(env.LIMITER.idFromName("global"));
      const t = await limiter.today();
      return json({ ...t, budget: Number(env.DAILY_BUDGET_USD) });
    }
    // Everything else is a static asset (served before the Worker runs) or a 404.
    return new Response("Not found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
