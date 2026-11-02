# Marsha — interactive DBT skills trainer

A tiny web app built on the same principles as this repo: only three files
matter, and the markdown program is the one a human edits and iterates on.

- **`marsha.md`** — the program: Marsha's persona (modeled on Dr. Marsha
  Linehan's published therapeutic style), the full DBT skills curriculum
  (mindfulness, distress tolerance, emotion regulation, interpersonal
  effectiveness, walking the middle path), and the rules for building
  interactive micro-trainings. **Edit this file to change behavior** — it is
  re-read on every request, so changes are live on the next message.
- **`app.py`** — one-file server (Python stdlib HTTP + the Anthropic SDK,
  streaming responses over SSE). Not normally edited.
- **`static/index.html`** — one-file chat UI, no build step. Includes a
  "speak replies" toggle that reads Marsha's responses aloud with the
  browser's speech synthesis (an unhurried, lower-pitched voice — her style,
  not a clone of her actual voice).

## Quick start

**Try it with no API key (demo mode):**

```bash
python3 marsha/app.py
# open http://localhost:8765
```

Without `ANTHROPIC_API_KEY` set, the server serves the full UI with scripted
Marsha-style replies (keyword-routed: anger, anxiety, conflict, crisis,
"teach me something") so you can test the chat, streaming, and the
"speak replies" voice toggle end to end. Each demo conversation starts with a
banner making clear the replies are canned.

**Run with the real model:**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv run --with anthropic marsha/app.py
# open http://localhost:8765
```

## What it does

Tell Marsha what's going on. She validates first (using Linehan's six levels
of validation), figures out whether you need a crisis-survival skill right now
or a learn-something moment, proposes the right module and skill, and walks
you through an interactive micro-training using your own situation as the
worked example — ending with one small piece of practice homework. Dialectical
throughout: "you're doing the best you can" AND "you can do better."

## Important

This is an educational demo, **not therapy and not Dr. Linehan**. It is not a
substitute for a DBT program or a clinician, and it is not a crisis service.
If you are in crisis, call or text **988** (US) or your local emergency number.
