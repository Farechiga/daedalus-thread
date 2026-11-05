# Deployment

The app is one process: `server/app.py` (Python stdlib) serves the static frontend from `web/` and a JSON API over a
read-only SQLite database (`data/db/daedalus.sqlite`, about 470 MB, rebuilt from source in about 25 s). It needs about
600 MB of disk and 256–512 MB of RAM. There are no other services, accounts or secrets.

## Run locally

```sh
scripts/fetch_sources.sh                # once: source data into data/raw/
python3 scripts/build_db.py             # data/db/daedalus.sqlite
python3 server/app.py                   # http://127.0.0.1:8000 (precomputes all theme views in ~10 s)
python3 tests/test_search.py            # autocomplete golden queries
```

## Live host: Hetzner VPS (chosen 2026-11-05)

The site runs on a flat-price Hetzner Cloud VPS (Ashburn, Ubuntu 26.04, 5.161.194.133 / 2a01:4ff:f0:e872::1). A fixed
monthly price means traffic can never run up per-query costs, which is why Fly.io and Cloudflare D1 were not used.

- `deploy/setup.sh` provisions a fresh server: key-only SSH, ufw (22/80/443), fail2ban, unattended upgrades, the
  `daedalus` user, source data and the database build.
- `deploy/daedalus-thread.service` runs the app on 127.0.0.1:8000. Caddy (`deploy/Caddyfile`) serves HTTPS with a Let's
  Encrypt certificate, renewed automatically.
- The site is password-protected: `SITE_PASSWORD` in `/etc/daedalus-thread.env` on the server, never in git. Visitors leave
  the username blank. `RATE_PER_MIN` limits requests per client.
- Ship changes by pushing to `main` and then running `deploy/update.sh` on the server. It pulls, rebuilds the database and
  restarts the app, in about 2 minutes.

GitHub Pages was released from the domain. The `Dockerfile` and `fly.toml` remain for a container host, but are unused.

## Pointing daedalus-thread.com (Squarespace Domains)

The domain is **daedalus-thread.com**, registered at Squarespace Domains. It currently uses Squarespace nameservers and
parking A records (198.49.23.144/145, 198.185.159.144/145).

Once a host is chosen, go to Squarespace → **Domains → daedalus-thread.com → DNS → Custom records**:

1. **Delete the Squarespace Defaults** record group. These are the parking A records and the `www` CNAME to Squarespace.
2. Add the records your host gives you. Typically:
   - **Current (Hetzner):** `A @ 5.161.194.133`, `AAAA @ 2a01:4ff:f0:e872::1` and `CNAME www daedalus-thread.com`. Caddy then
     obtains HTTPS automatically. Run `systemctl restart caddy` to retry at once instead of waiting for its back-off.
3. Wait for DNS to propagate (minutes to a few hours), then check that `https://daedalus-thread.com` serves the app with a valid certificate.

Do not set up Squarespace "domain forwarding". It redirects instead of serving, and breaks deep links.
