"""
Marsha — a DBT skills-training chatbot in the spirit of this repo:
three files that matter, and the markdown program is the one you edit.

  marsha.md          — the program: persona + curriculum (human edits this)
  app.py             — this server (one file, stdlib http + anthropic SDK)
  static/index.html  — the chat UI (one file, no build step)

Run:  ANTHROPIC_API_KEY=... uv run --with anthropic marsha/app.py
Then open http://localhost:8765
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import anthropic

HERE = Path(__file__).parent
MODEL = "claude-opus-4-8"
PORT = int(os.environ.get("PORT", "8765"))

client = anthropic.Anthropic()


def system_prompt() -> str:
    # Re-read on every request so editing marsha.md is live, like program.md.
    return (HERE / "marsha.md").read_text()


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
        except anthropic.APIError as e:
            self._sse({"error": f"API error: {e.message}"})
        except BrokenPipeError:
            pass

    def _sse(self, obj: dict):
        try:
            self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
            self.wfile.flush()
        except BrokenPipeError:
            raise

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"Marsha is listening at http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
