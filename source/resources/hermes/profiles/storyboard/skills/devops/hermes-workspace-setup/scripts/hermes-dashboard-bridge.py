#!/usr/bin/env python3
"""
Hermes Dashboard Bridge — exposes state.db sessions via Claude Dashboard API.
Runs on port 9119 so Hermes Workspace auto-discovers it.

The Workspace probes port 9119 via /api/status, then scrapes the root HTML
for window.__HERMES_SESSION_TOKEN__ before calling /api/sessions.
"""

import json
import sqlite3
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERMES_HOME = Path.home() / ".hermes"
STATE_DB = HERMES_HOME / "state.db"

DASHBOARD_TOKEN = str(uuid.uuid4())
ROOT_HTML = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>Hermes Dashboard Bridge</title>
<script>window.__HERMES_SESSION_TOKEN__="{DASHBOARD_TOKEN}";</script>
</head><body>
<h1>Hermes Dashboard Bridge</h1>
<p>Serving {STATE_DB} on port 9119</p>
</body></html>"""


def get_db():
    conn = sqlite3.connect(str(STATE_DB))
    conn.row_factory = sqlite3.Row
    return conn


def session_row_to_dict(row):
    return {
        "id": row["id"],
        "source": row["source"],
        "user_id": row["user_id"],
        "model": row["model"],
        "title": row["title"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "end_reason": row["end_reason"],
        "message_count": row["message_count"],
        "tool_call_count": row["tool_call_count"],
        "input_tokens": row["input_tokens"],
        "output_tokens": row["output_tokens"],
        "cache_read_tokens": row["cache_read_tokens"],
        "cache_write_tokens": row["cache_write_tokens"],
        "reasoning_tokens": row["reasoning_tokens"],
        "parent_session_id": row["parent_session_id"],
        "last_active": None,
        "is_active": row["ended_at"] is None,
        "preview": None,
    }


def message_row_to_dict(row):
    tool_calls_raw = row["tool_calls"]
    tool_calls = None
    if tool_calls_raw:
        try:
            tool_calls = json.loads(tool_calls_raw)
        except Exception:
            tool_calls = tool_calls_raw
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "role": row["role"],
        "content": row["content"],
        "tool_call_id": row["tool_call_id"],
        "tool_calls": tool_calls,
        "tool_name": row["tool_name"],
        "timestamp": row["timestamp"],
        "token_count": row["token_count"],
        "finish_reason": row["finish_reason"],
        "reasoning": row["reasoning"],
    }


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, body, status=200, content_type="application/json"):
        body_bytes = (
            body.encode("utf-8")
            if isinstance(body, str)
            else json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(body_bytes))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body_bytes)

    def _send_json(self, data, status=200):
        self._send(data, status)

    def _send_error(self, status, message):
        self._send_json({"error": message}, status)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS"
        )
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type, Authorization"
        )
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path == "":
            self._send(ROOT_HTML, content_type="text/html; charset=utf-8")
            return

        if path == "/api/status":
            self._send_json({"version": "hermes-bridge-1.0.0", "status": "ok"})
            return

        if path == "/api/sessions":
            limit = int(params.get("limit", [50])[0])
            offset = int(params.get("offset", [0])[0])
            conn = get_db()
            try:
                total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                rows = conn.execute(
                    "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
                sessions = [session_row_to_dict(r) for r in rows]
                for s in sessions:
                    msg = conn.execute(
                        "SELECT content FROM messages WHERE session_id=? AND role IN ('user','assistant') ORDER BY id LIMIT 1",
                        (s["id"],),
                    ).fetchone()
                    if msg and msg["content"]:
                        s["preview"] = msg["content"][:200]
                self._send_json(
                    {
                        "sessions": sessions,
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                    }
                )
            finally:
                conn.close()
            return

        if path == "/api/sessions/search":
            q = params.get("q", [""])[0]
            conn = get_db()
            try:
                rows = conn.execute(
                    """SELECT DISTINCT s.id as session_id, s.title, s.source, s.model,
                       s.started_at as session_started, m.content as snippet, m.role
                    FROM sessions s
                    JOIN messages m ON m.session_id = s.id
                    WHERE m.content LIKE ?
                    ORDER BY s.started_at DESC LIMIT 20""",
                    (f"%{q}%",),
                ).fetchall()
                self._send_json({"results": [dict(r) for r in rows]})
            finally:
                conn.close()
            return

        parts = path.split("/")
        if len(parts) == 4 and parts[1] == "api" and parts[2] == "sessions":
            session_id = parts[3]
            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT * FROM sessions WHERE id=?", (session_id,)
                ).fetchone()
                if not row:
                    self._send_error(404, "Session not found")
                    return
                s = session_row_to_dict(row)
                msg = conn.execute(
                    "SELECT content FROM messages WHERE session_id=? AND role IN ('user','assistant') ORDER BY id LIMIT 1",
                    (session_id,),
                ).fetchone()
                if msg and msg["content"]:
                    s["preview"] = msg["content"][:200]
                self._send_json(s)
            finally:
                conn.close()
            return

        if (
            len(parts) == 5
            and parts[1] == "api"
            and parts[2] == "sessions"
            and parts[4] == "messages"
        ):
            session_id = parts[3]
            conn = get_db()
            try:
                srow = conn.execute(
                    "SELECT * FROM sessions WHERE id=?", (session_id,)
                ).fetchone()
                if not srow:
                    self._send_error(404, "Session not found")
                    return
                rows = conn.execute(
                    "SELECT * FROM messages WHERE session_id=? ORDER BY id",
                    (session_id,),
                ).fetchall()
                self._send_json(
                    {
                        "messages": [message_row_to_dict(r) for r in rows],
                        "session_started": srow["started_at"],
                        "model": srow["model"],
                    }
                )
            finally:
                conn.close()
            return

        self._send_error(404, "Not found")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        parts = parsed.path.rstrip("/").split("/")
        if len(parts) == 4 and parts[1] == "api" and parts[2] == "sessions":
            session_id = parts[3]
            conn = get_db()
            try:
                conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
                conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
                conn.commit()
                self._send_json({"ok": True})
            finally:
                conn.close()
            return
        self._send_error(404, "Not found")


def main():
    port = 9119
    server = HTTPServer(("127.0.0.1", port), DashboardHandler)
    print(f"Hermes Dashboard Bridge running on http://127.0.0.1:{port}")
    print(f"Reading sessions from: {STATE_DB}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
