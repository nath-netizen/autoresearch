"""
Marsha — a DBT skills-training chatbot in the spirit of this repo:
three files that matter, and the markdown program is the one you edit.

  marsha.md          — the program: persona + curriculum (human edits this)
  app.py             — this server (one file, stdlib http + anthropic SDK)
  static/index.html  — the chat UI (one file, no build step)

Run with the real model:
  ANTHROPIC_API_KEY=... uv run --with anthropic marsha/app.py

Run in demo mode (no API key, no dependencies — scripted Marsha-style replies
so you can try the UI):
  uv run marsha/app.py        # or: python3 marsha/app.py

Then open http://localhost:8765
"""

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
MODEL = "claude-opus-4-8"
PORT = int(os.environ.get("PORT", "8765"))

DEMO_MODE = not os.environ.get("ANTHROPIC_API_KEY")
if not DEMO_MODE:
    import anthropic
    client = anthropic.Anthropic()


def system_prompt() -> str:
    # Re-read on every request so editing marsha.md is live, like program.md.
    return (HERE / "marsha.md").read_text()


# ---------------------------------------------------------------------------
# Demo responder: a tiny scripted stand-in for the model so the UI can be
# tried without an API key. Keyword-routed, Linehan-flavored, and honest
# about being canned.
# ---------------------------------------------------------------------------

DEMO_BANNER = (
    "(Demo mode — no API key set, so these are scripted sample replies. "
    "Set ANTHROPIC_API_KEY to talk to the real model.)\n\n"
)

DEMO_FLOWS = [
    (("suicid", "kill myself", "self-harm", "self harm", "hurt myself", "cutting"),
     "I hear how much pain you're in, and I'm glad you said it out loud — that "
     "took something. Listen to me: this chatbot is not the right help for this "
     "moment, and you deserve the real thing. Call or text 988 right now, or "
     "your local emergency number, and your therapist if you have one.\n\n"
     "While you reach out, one crisis skill as a bridge — TIPP: hold something "
     "cold to your face, or step outside into cold air. It drops your heart rate "
     "fast. Survive this moment without making it worse. That's the whole job "
     "right now."),
    (("angry", "anger", "furious", "rage", "lash", "yell"),
     "Okay — anger. Given what happened, of course you're angry; that emotion is "
     "doing its job. AND acting on the urge is probably going to cost you "
     "something you care about. Both things are true.\n\n"
     "Here's a micro-training: Opposite Action, from emotion regulation. First, "
     "check the facts — does the anger fit the facts, and does acting on it work "
     "for you? If not, we act opposite: gently avoid the person instead of "
     "attacking, unclench the hands, half-smile, even a touch of kindness. It "
     "feels absurd. Do it anyway — the emotion follows the body.\n\n"
     "Want to walk through it with the actual situation? Tell me what set it off."),
    (("anxious", "anxiety", "panic", "worry", "overwhelm", "stress"),
     "That sounds genuinely hard — and your body is reacting exactly the way a "
     "sensitive nervous system reacts. Nothing about you is broken; you're "
     "overwhelmed.\n\n"
     "So first: is this a five-alarm fire or a slow burn? If your heart is "
     "pounding right now, we do TIPP — paced breathing, exhale longer than the "
     "inhale, four in, six out, for two minutes. If it's a slow burn, we go to "
     "mindfulness: Observe and Describe. Just the facts, no judgments — 'I "
     "notice my chest is tight. I notice the thought that I'll fail.' Thoughts "
     "are thoughts, not facts.\n\n"
     "Which one is it — fire or burn?"),
    (("friend", "boyfriend", "girlfriend", "partner", "mom", "dad", "boss",
      "coworker", "fight", "argument", "conflict", "ask for", "say no"),
     "Relationships — where everybody's doing the best they can and it's still a "
     "mess. Before we pick a skill, one question, because it decides everything: "
     "in this conversation, what matters most — getting what you want "
     "(objectives), keeping the relationship, or keeping your self-respect? You "
     "rarely get to max all three.\n\n"
     "If it's the objective, we build a DEAR MAN: Describe the facts, Express "
     "how you feel, Assert what you want, Reinforce why it's good for them too. "
     "If it's the relationship, GIVE: be Gentle, act Interested, Validate. If "
     "it's self-respect, FAST: be Fair, no over-Apologizing, Stick to your "
     "values, be Truthful.\n\n"
     "So — which one is it?"),
    (("teach", "training", "learn", "skill", "lesson", "module"),
     "Good — you came to learn. I like that. Here's the menu, pick what fits "
     "your life right now:\n\n"
     "Mindfulness — finding Wise Mind, the place where reason and emotion "
     "overlap. Distress Tolerance — surviving a crisis without making it worse. "
     "Emotion Regulation — understanding emotions and turning their volume "
     "down. Interpersonal Effectiveness — asking, refusing, and keeping your "
     "self-respect while you do it.\n\n"
     "Which one, and what's a real situation we can use as the worked example? "
     "Skills practiced on real life stick. Skills practiced in the abstract "
     "evaporate."),
]

DEMO_DEFAULT = (
    "I'm listening — and I want to make sure I actually get it before we pick a "
    "skill. Two things can be true at once: what you're feeling makes complete "
    "sense given what's happening, AND there may be a more effective way "
    "through it. That's the whole game.\n\n"
    "Tell me a little more: what happened, and what did you feel in your body "
    "when it did? Or, if you'd rather, just say 'teach me something' and I'll "
    "lay out the menu — mindfulness, distress tolerance, emotion regulation, or "
    "interpersonal effectiveness."
)


def demo_reply(messages: list) -> str:
    last = next((m["content"] for m in reversed(messages)
                 if m.get("role") == "user"), "")
    if isinstance(last, list):  # content-block form
        last = " ".join(b.get("text", "") for b in last)
    text = last.lower()
    reply = next((r for keys, r in DEMO_FLOWS if any(k in text for k in keys)),
                 DEMO_DEFAULT)
    banner = DEMO_BANNER if len(messages) <= 1 else ""
    return banner + reply


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = (HERE / "static" / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/chat":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            messages = json.loads(self.rfile.read(length))["messages"]
        except (json.JSONDecodeError, KeyError):
            self.send_error(400)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        try:
            if DEMO_MODE:
                # Stream word by word so the UI behaves like the real thing.
                for word in demo_reply(messages).split(" "):
                    self._sse({"text": word + " "})
                    time.sleep(0.02)
            else:
                with client.messages.stream(
                    model=MODEL,
                    max_tokens=2048,
                    thinking={"type": "adaptive"},
                    output_config={"effort": "low"},
                    system=[{
                        "type": "text",
                        "text": system_prompt(),
                        "cache_control": {"type": "ephemeral"},
                    }],
                    messages=messages,
                ) as stream:
                    for text in stream.text_stream:
                        self._sse({"text": text})
                    final = stream.get_final_message()
                if final.stop_reason == "refusal":
                    self._sse({"text": "I can't go there with you — but I'm still here. What else is going on?"})
            self._sse({"done": True})
        except BrokenPipeError:
            pass
        except Exception as e:
            self._sse({"error": f"server error: {e}"})

    def _sse(self, obj: dict):
        try:
            self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
            self.wfile.flush()
        except BrokenPipeError:
            raise

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    mode = "DEMO mode (no ANTHROPIC_API_KEY — scripted replies)" if DEMO_MODE \
        else f"live mode ({MODEL})"
    print(f"Marsha is listening at http://localhost:{PORT} — {mode}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
