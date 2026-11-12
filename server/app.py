#!/usr/bin/env python3
"""Daedalus Thread server: static frontend + small JSON API over SQLite. Stdlib only.

    python3 server/app.py [--port 8000] [--db data/db/daedalus.sqlite]

Endpoints (GET, all JSON):
  /api/meta                      segments, object types, sources, build info
  /api/view?<filters>            everything the single pane needs for one filter state
  /api/artworks?<filters>&offset&limit&sort
  /api/artwork?id=<icarus id>    drill-down detail
  /api/suggest?q=<text>          grouped autocomplete
  /api/atlas?<filters>           best-known dated works with images and artist region (Atlas view)
Filters: node (repeatable, AND), century, creator, type, source, code (Iconclass, incl. descendants), q (title text), repro=1
"""
import argparse
import base64
import collections
import gzip
import hashlib
import hmac
import html
import json
import mimetypes
import os
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

sys.path.insert(0, os.path.dirname(__file__))
from queries import BadRequest, Queries  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WEB = os.path.join(ROOT, "web")
CACHE_SIZE = 2048
# Optional protection, configured by environment (e.g. /etc/daedalus-thread.env on the server):
#   SITE_PASSWORD [SITE_USER]  -> every request needs the password: a password-only sign-in page sets a signed
#                                 session cookie (30 days). HTTP Basic auth is still accepted for scripts
#                                 (curl -u :password); without SITE_USER any username is accepted there
#   RATE_PER_MIN (default 240) -> API requests per visitor per minute before answering 429
#   TRUST_PROXY=1               -> take the visitor IP from X-Forwarded-For (set when behind Caddy on localhost)
SITE_USER = os.environ.get("SITE_USER", "")
SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "")
RATE_PER_MIN = int(os.environ.get("RATE_PER_MIN", "240"))
TRUST_PROXY = os.environ.get("TRUST_PROXY") == "1"


class RateLimiter:
    """Token bucket per client IP: RATE_PER_MIN requests per minute, bursts up to a third of that."""

    def __init__(self, per_min):
        self.rate, self.burst = per_min / 60.0, max(10, per_min // 3)
        self.buckets, self.lock = {}, threading.Lock()

    def allow(self, ip):
        now = time.time()
        with self.lock:
            tokens, last = self.buckets.get(ip, (self.burst, now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            ok = tokens >= 1
            self.buckets[ip] = (tokens - 1 if ok else tokens, now)
            if len(self.buckets) > 50000:  # forget idle visitors
                self.buckets = {k: v for k, v in self.buckets.items() if now - v[1] < 600}
            return ok


LIMITER = RateLimiter(RATE_PER_MIN)
LOGIN_LIMITER = RateLimiter(10)  # sign-in attempts per visitor per minute

# Session cookie: "<expiry>.<hmac>", keyed by the password, so changing SITE_PASSWORD signs everyone out.
SESSION_COOKIE, SESSION_DAYS = "dt_session", 30
SESSION_KEY = hashlib.sha256(b"daedalus-thread-session:" + SITE_PASSWORD.encode("utf-8")).digest()
PUBLIC_PATHS = {"/healthz", "/assets/logo-96.png", "/assets/logo-192.png", "/assets/favicon-32.png", "/assets/apple-touch-icon.png",
                "/assets/wordmark.png"}


def session_token(expiry):
    return f"{expiry}.{hmac.new(SESSION_KEY, str(expiry).encode(), hashlib.sha256).hexdigest()}"


def session_valid(token):
    expiry, _, _ = (token or "").partition(".")
    return expiry.isdigit() and int(expiry) > time.time() and hmac.compare_digest(token, session_token(int(expiry)))


LOGIN_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Daedalus Thread</title><link rel="icon" type="image/png" sizes="32x32" href="/assets/favicon-32.png">
<meta name="robots" content="noindex"><style>
:root { --bg: #f5f3ee; --surface: #fffefb; --ink: #14232a; --muted: #5b686d; --line: #e1ded5; --navy: #022e3a; --gold: #cf9203; --danger: #b3261e; }
@media (prefers-color-scheme: dark) { :root { --bg: #0a171c; --surface: #10222a; --ink: #e8ecea; --muted: #9fb0b4; --line: #21363e; --navy: #cfe3e8; --gold: #e3a828; --danger: #ff8a80; } }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: var(--bg); color: var(--ink);
  font: 15px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; padding: 16px; }
main { width: min(380px, 100%); background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 32px 28px 28px; text-align: center; }
img { width: 72px; height: 72px; border-radius: 50%; background: #f5f3ee; }
h1 { font: 600 26px "Iowan Old Style", Palatino, Georgia, serif; color: var(--navy); margin: 12px 0 4px; }
h1 .wm { display: block; width: 100%; height: auto; max-width: 300px; margin: 6px auto 0; background: none; border-radius: 0; }
@media (prefers-color-scheme: dark) { h1 .wm { filter: brightness(0) invert(.9); } }
.thread { width: 48px; height: 2px; background: var(--gold); margin: 12px auto 18px; border: 0; }
p { color: var(--muted); margin: 0 0 18px; font-size: 14px; }
input { width: 100%; padding: 11px 16px; border: 1px solid var(--line); border-radius: 999px; background: var(--bg); color: var(--ink); font: inherit; }
input:focus { outline: 2px solid var(--navy); outline-offset: 1px; }
button { margin-top: 12px; width: 100%; padding: 11px 16px; border: 0; border-radius: 999px; background: var(--navy); color: var(--surface); font: 600 15px inherit; cursor: pointer; }
.err { color: var(--danger); font-weight: 600; margin: 12px 0 0; }
</style></head><body><main>
<img src="/assets/logo-192.png" alt="">
<h1><img class="wm" src="/assets/wordmark.png" alt="Daedalus Thread"></h1><hr class="thread">
<p>This preview is private. Enter the password to continue.</p>
<form method="post" action="/login"><input type="hidden" name="next" value="{next}">
<label for="pw" style="position:absolute;left:-9999px">Password</label>
<input id="pw" name="password" type="password" autocomplete="current-password" placeholder="Password" required autofocus>
<button type="submit">Enter</button>{error}</form></main></body></html>"""


class LRU:
    def __init__(self, size):
        self.size, self.data, self.lock = size, collections.OrderedDict(), threading.Lock()

    def get(self, key):
        with self.lock:
            if key in self.data:
                self.data.move_to_end(key)
                return self.data[key]
        return None

    def put(self, key, value):
        with self.lock:
            self.data[key] = value
            self.data.move_to_end(key)
            while len(self.data) > self.size:
                self.data.popitem(last=False)


class App:
    def __init__(self, db_path):
        self.db_path = db_path
        self.local = threading.local()
        self.cache = LRU(CACHE_SIZE)
        self.queries()  # fail fast if the DB is missing

    def warm(self):
        """Precompute the landing view and every unfiltered node view (~1 min) so navigation is instant."""
        t0 = time.time()
        q = self.queries()
        keys = [("/api/meta", ""), ("/api/view", "")] + [("/api/view", f"node={quote(n)}") for n in q.nodes]
        for path, query in keys:
            key = path + "?" + query
            if self.cache.get(key) is None:
                payload = self.api(path, parse_qs(query))
                self.cache.put(key, json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        print(f"warmed {len(keys)} views in {time.time() - t0:.0f}s", flush=True)

    def queries(self):
        q = getattr(self.local, "q", None)
        if q is None:
            db = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, check_same_thread=False)
            db.execute("PRAGMA cache_size=-64000")
            db.execute("PRAGMA mmap_size=536870912")
            q = self.local.q = Queries(db)
        return q

    def api(self, path, params):
        q = self.queries()
        if path == "/api/meta":
            return q.meta_payload()
        if path == "/api/view":
            return q.view(q.filters(params))
        if path == "/api/artworks":
            f = q.filters(params)
            offset = max(0, int((params.get("offset") or ["0"])[0]))
            limit = min(100, max(1, int((params.get("limit") or ["40"])[0])))
            return q.artworks(f, offset, limit, (params.get("sort") or ["fame"])[0])
        if path == "/api/artwork":
            rec = q.artwork((params.get("id") or [""])[0])
            if rec is None:
                raise LookupError("artwork not found")
            return rec
        if path == "/api/atlas":
            return q.atlas(q.filters(params))
        if path == "/api/suggest":
            return q.suggest((params.get("q") or [""])[0])
        raise LookupError("no such endpoint")


class Handler(BaseHTTPRequestHandler):
    app = None
    server_version = "DaedalusThread/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.log_date_time_string()} {fmt % args}\n")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/healthz":  # for uptime checks; no data, no auth
            return self.send_bytes(200, b"ok", "text/plain")
        if SITE_PASSWORD and not self.authorized() and url.path not in PUBLIC_PATHS:
            if url.path.startswith("/api/"):  # no WWW-Authenticate header, so browsers never show their own prompt
                return self.send_bytes(401, b'{"error":"sign in required"}', "application/json", cache="no-store")
            return self.login_page(self.path)
        if url.path.startswith("/api/"):
            if not LIMITER.allow(self.client_ip()):
                return self.send_bytes(429, b'{"error":"too many requests, slow down"}', "application/json",
                                       cache="no-store", extra={"Retry-After": "10"})
            return self.handle_api(url)
        return self.handle_static(url.path)

    def do_POST(self):
        url = urlparse(self.path)
        if url.path != "/login" or not SITE_PASSWORD:
            return self.send_bytes(404, b"not found", "text/plain")
        if not LOGIN_LIMITER.allow(self.client_ip()):
            return self.send_bytes(429, b"Too many attempts. Wait a minute and try again.", "text/plain; charset=utf-8",
                                   extra={"Retry-After": "60"})
        length = min(int(self.headers.get("Content-Length") or 0), 4096)
        form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        nxt = (form.get("next") or ["/"])[0]
        if not nxt.startswith("/") or nxt.startswith("//") or "\\" in nxt:  # same-site paths only
            nxt = "/"
        if not hmac.compare_digest((form.get("password") or [""])[0], SITE_PASSWORD):
            time.sleep(0.6)  # slows guessing further
            return self.login_page(nxt, error=True)
        expiry = int(time.time()) + SESSION_DAYS * 86400
        cookie = (f"{SESSION_COOKIE}={session_token(expiry)}; Max-Age={SESSION_DAYS * 86400}; Path=/; HttpOnly; SameSite=Lax"
                  + ("; Secure" if TRUST_PROXY else ""))
        self.send_bytes(303, b"", "text/plain", cache="no-store", extra={"Location": nxt, "Set-Cookie": cookie})

    def login_page(self, nxt, error=False):
        body = LOGIN_PAGE.replace("{next}", html.escape(nxt, quote=True)).replace(
            "{error}", '<p class="err" role="alert">That password is not right.</p>' if error else "")
        self.send_bytes(401, body.encode("utf-8"), "text/html; charset=utf-8", cache="no-store",
                        extra={"X-Frame-Options": "DENY"})

    def authorized(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == SESSION_COOKIE and session_valid(value):
                return True
        header = self.headers.get("Authorization") or ""
        if not header.startswith("Basic "):
            return False
        try:
            user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
        except Exception:
            return False
        user_ok = hmac.compare_digest(user, SITE_USER) if SITE_USER else True  # no SITE_USER: any (or no) username
        return user_ok and hmac.compare_digest(pw, SITE_PASSWORD)

    def client_ip(self):
        if TRUST_PROXY:
            fwd = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            if fwd:
                return fwd
        return self.client_address[0]

    def handle_api(self, url):
        key = url.path + "?" + url.query
        body = self.app.cache.get(key)
        status = 200
        if body is None:
            t0 = time.time()
            try:
                payload = self.app.api(url.path, parse_qs(url.query))
            except BadRequest as e:
                status, payload = 400, {"error": str(e)}
            except LookupError as e:
                status, payload = 404, {"error": str(e)}
            except ValueError as e:
                status, payload = 400, {"error": str(e)}
            if status == 200:
                payload["_ms"] = round((time.time() - t0) * 1000, 1)
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if status == 200:
                self.app.cache.put(key, body)
        self.send_bytes(status, body, "application/json; charset=utf-8", cache="public, max-age=300")

    def handle_static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        full = os.path.realpath(os.path.join(WEB, path.lstrip("/")))
        if not full.startswith(os.path.realpath(WEB) + os.sep) or not os.path.isfile(full):
            full = os.path.join(WEB, "index.html") if "." not in os.path.basename(path) else None
        if not full:
            return self.send_bytes(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json", "image/svg+xml"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            self.send_bytes(200, fh.read(), ctype, cache="no-cache")

    def send_bytes(self, status, body, ctype, cache=None, extra=None):
        if len(body) > 1024 and "gzip" in (self.headers.get("Accept-Encoding") or ""):
            body = gzip.compress(body, 5)
            encoding = "gzip"
        else:
            encoding = None
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if encoding:
            self.send_header("Content-Encoding", encoding)
            self.send_header("Vary", "Accept-Encoding")
        if cache:
            self.send_header("Cache-Control", "private, " + cache if SITE_PASSWORD and "max-age" in cache else cache)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--db", default=os.environ.get("DAEDALUS_DB", os.path.join(ROOT, "data", "db", "daedalus.sqlite")))
    ap.add_argument("--no-warm", action="store_true", help="skip precomputing node views at startup")
    args = ap.parse_args()
    Handler.app = App(args.db)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    if not args.no_warm:
        threading.Thread(target=Handler.app.warm, daemon=True).start()
    print(f"Daedalus Thread on http://{args.host}:{args.port}  (db: {args.db})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
