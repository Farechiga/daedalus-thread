#!/usr/bin/env bash
# Deploy the latest main: pull, rebuild the database, restart. Run as root on the server:
#   ssh root@SERVER /opt/daedalus-thread/deploy/update.sh
set -euo pipefail
cd /opt/daedalus-thread
sudo -u daedalus git pull -q --ff-only
sudo -u daedalus python3 scripts/build_db.py
install -m 644 deploy/daedalus-thread.service /etc/systemd/system/daedalus-thread.service
install -m 644 deploy/Caddyfile /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl restart daedalus-thread
systemctl reload caddy
echo "updated to $(sudo -u daedalus git log -1 --format='%h %s')"
