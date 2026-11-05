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

## Hosting options

GitHub Pages can't run the API, so it only works for the static frontend.

| Option | Fits the stack? | Cost | Notes |
|---|---|---|---|
| **Fly.io / Render / Railway** (container) | Yes. Uses the `Dockerfile` as-is. | about $5–7/month for an always-on small instance | The database is built inside the image. Deploys from GitHub. **Recommended.** |
| Small VPS (Hetzner, DigitalOcean) + Caddy | Yes | about $5/month | Most control. You run OS updates yourself. |
| Cloudflare Pages + Workers + D1 (SQLite) | Partly. The API would need porting to JS (about 300 lines; the SQL carries over). | Free tier likely sufficient | Fastest worldwide. Leaves the "Python backend" design. |

The `Dockerfile` has **not been test-built yet**, because Docker isn't installed on the development machine. The first deploy
will exercise it.

## Pointing daedalus-thread.com (Squarespace Domains)

The domain is **daedalus-thread.com**, registered at Squarespace Domains. It currently uses Squarespace nameservers and
parking A records (198.49.23.144/145, 198.185.159.144/145).

Once a host is chosen, go to Squarespace → **Domains → daedalus-thread.com → DNS → Custom records**:

1. **Delete the Squarespace Defaults** record group. These are the parking A records and the `www` CNAME to Squarespace.
2. Add the records your host gives you. Typically:
   - **Fly.io:** run `fly certs add daedalus-thread.com` and `fly certs add www.daedalus-thread.com`. Then add `A @ <fly IPv4>`,
     `AAAA @ <fly IPv6>` and `CNAME www <app>.fly.dev`.
   - **Render:** `A @ 216.24.57.1` and `CNAME www <service>.onrender.com`. Check the dashboard for the current values.
   - **VPS:** `A @ <server IP>` and `CNAME www daedalus-thread.com`. Caddy then obtains HTTPS automatically.
3. Wait for DNS to propagate (minutes to a few hours), then check that `https://daedalus-thread.com` serves the app with a valid certificate.

Do not set up Squarespace "domain forwarding". It redirects instead of serving, and breaks deep links.
