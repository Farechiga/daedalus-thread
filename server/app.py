#!/usr/bin/env python3
"""Daedalus Thread server: static frontend + small JSON API over SQLite. Stdlib only.

    python3 server/app.py [--port 8000] [--db data/db/daedalus.sqlite]

Endpoints (GET, all JSON):
  /api/meta                      segments, object types, sources, build info
  /api/view?<filters>            everything the single pane needs for one filter state
  /api/artworks?<filters>&offset&limit&sort
  /api/artwork?id=<icarus id>    drill-down detail
  /api/suggest?q=<text>          grouped autocomplete
Filters: node (repeatable, AND), century, creator, type, source, code (Iconclass, incl. descendants), q (title text), repro=1
"""
import argparse
import base64
import collections
import gzip
import hmac
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
#   SITE_USER / SITE_PASSWORD  -> every request needs HTTP Basic auth (the browser shows a login prompt)
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
        if SITE_PASSWORD and not self.authorized():
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Daedalus Thread", charset="UTF-8"')
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", "21")
            self.end_headers()
            self.wfile.write(b"Password required.\r\n\r\n"[:21])
            return
        if url.path.startswith("/api/"):
            if not LIMITER.allow(self.client_ip()):
                return self.send_bytes(429, b'{"error":"too many requests, slow down"}', "application/json",
                                       cache="no-store", extra={"Retry-After": "10"})
            return self.handle_api(url)
        return self.handle_static(url.path)

    def authorized(self):
        header = self.headers.get("Authorization") or ""
        if not header.startswith("Basic "):
            return False
        try:
            user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
        except Exception:
            return False
        return hmac.compare_digest(user, SITE_USER) and hmac.compare_digest(pw, SITE_PASSWORD)

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
