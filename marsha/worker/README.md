# Wise Mind Coach — Cloudflare Worker

A public DBT skills-practice chat that costs little or nothing to run. One
Cloudflare Worker serves the page, keeps your Anthropic API key secret, and
enforces two limits so a public link can't run up a bill:

- **Per-visitor limit**: 30 messages per hour per visitor (visitors are
  identified by a salted hash of their IP; raw IPs are never stored).
- **Daily spending cap**: once the day's model costs reach $1.00, the coach
  pauses until midnight UTC and tells visitors to come back tomorrow (with
  the 988 line shown).

## Files

| File | What it is |
|---|---|
| `src/prompt.md` | The coach's instructions and DBT curriculum. **Edit this to change behavior.** |
| `public/index.html` | The chat page |
| `src/index.ts` | The Worker: `/chat` streams replies, `/status` shows today's spend |
| `wrangler.jsonc` | Settings: model, limits, prices |

## Deploy (about 10 minutes)

You need a free [Cloudflare account](https://dash.cloudflare.com/sign-up) and an
[Anthropic API key](https://console.anthropic.com/).

```bash
cd marsha/worker
npm install
npx wrangler login                          # opens a browser to sign in to Cloudflare
npx wrangler secret put ANTHROPIC_API_KEY   # paste your key when asked
npx wrangler secret put IP_SALT             # paste any long random string
npx wrangler deploy
```

Wrangler prints your public URL (`https://wise-mind-coach.<you>.workers.dev`).
To use your own domain, add it under the Worker's **Settings → Domains & Routes**
in the Cloudflare dashboard.

**Also set a spend limit in the Anthropic Console** (Settings → Limits). The
Worker's cap is the first line of defense; the Console limit is the backstop
if anything goes wrong.

## Run it locally

```bash
printf 'ANTHROPIC_API_KEY=sk-ant-...\nIP_SALT=anything\n' > .dev.vars
npm run dev     # http://localhost:8787
```

## Costs

- **Cloudflare**: the free plan covers this (100,000 requests a day; Durable
  Objects are included on the free plan).
- **Model**: `claude-haiku-4-5` costs about half a cent per message at these
  settings. The default $1/day cap allows roughly 200 messages a day, so the
  worst case is about $30/month. Raise `DAILY_BUDGET_USD` as traffic grows.

## Changing settings

Edit `vars` in `wrangler.jsonc` and run `npx wrangler deploy` again:

- `DAILY_BUDGET_USD` — the daily spending cap
- `MESSAGES_PER_HOUR` — the per-visitor hourly limit
- `MODEL`, `INPUT_PRICE_PER_MTOK`, `OUTPUT_PRICE_PER_MTOK` — switch models
  (update both prices to match, or the spending cap will be wrong)
- `MAX_TOKENS` — the longest reply allowed

Check today's spend at any time: `https://<your-url>/status`.

## Known limits

- Spend is recorded after each reply finishes, so a burst of simultaneous
  messages right at the cap can overshoot it by a few cents.
- Conversations live only in the visitor's browser tab. Nothing is stored
  server-side except hourly message counts and the daily spend total.
- The prompt is shorter than the minimum Haiku needs for prompt caching, so
  every message pays full input price. That's already reflected in the
  estimate above.
- This is an educational tool, not therapy. Before promoting it publicly,
  have a lawyer review the framing; several US states regulate AI that
  provides mental-health services.
