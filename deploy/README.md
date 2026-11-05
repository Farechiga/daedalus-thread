# Server deployment (Hetzner Cloud, Ubuntu 24.04)

A flat-price VPS (CPX11, 2 GB RAM) runs the Python server behind Caddy, which handles HTTPS automatically.
There are no per-request charges.

| File | Purpose |
|---|---|
| `setup.sh` | One-time setup on a fresh server: updates, key-only SSH, firewall, fail2ban, app user, data download (~0.7 GB), database build, service, Caddy |
| `update.sh` | Deploy the latest `main`: pull, rebuild the database (~30 s), restart |
| `daedalus-thread.service` | systemd unit (restarts automatically, read-only filesystem) |
| `Caddyfile` | HTTPS for daedalus-thread.com and www, plus plain HTTP on the IP address for testing |

```sh
ssh -i ~/.ssh/daedalus_hetzner root@SERVER_IP 'bash -s' < deploy/setup.sh   # first time
ssh -i ~/.ssh/daedalus_hetzner root@SERVER_IP /opt/daedalus-thread/deploy/update.sh   # later deploys
```

**Password and limits** are set in `/etc/daedalus-thread.env` on the server (never in git). After editing it, run
`systemctl restart daedalus-thread`:

```
SITE_PASSWORD=...        # remove to make the site public
#SITE_USER=...           # optional; without it visitors leave the username box empty
RATE_PER_MIN=240         # API requests per visitor per minute
TRUST_PROXY=1            # visitor IP comes from Caddy
```

**DNS (Squarespace):** `A @` → server IPv4, `AAAA @` → server IPv6, `CNAME www` → `daedalus-thread.com`.
Remove the GitHub Pages custom domain first. Caddy obtains the certificates as soon as DNS points here.
