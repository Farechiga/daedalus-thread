#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 server for Daedalus Thread. Run as root:
#   ssh root@SERVER 'bash -s' < deploy/setup.sh
# Then put SITE_USER / SITE_PASSWORD in /etc/daedalus-thread.env (see deploy/README.md).
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
REPO=https://github.com/Farechiga/daedalus-thread.git
APP=/opt/daedalus-thread

apt-get update -q
apt-get upgrade -yq
apt-get install -yq python3 git curl unzip caddy unattended-upgrades ufw fail2ban

# security: automatic security updates, key-only SSH, firewall (Hetzner's firewall also filters)
dpkg-reconfigure -f noninteractive unattended-upgrades
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/; s/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl reload ssh
ufw allow 22/tcp; ufw allow 80/tcp; ufw allow 443/tcp; ufw --force enable
systemctl enable --now fail2ban

# app user and code
id daedalus >/dev/null 2>&1 || useradd --system --create-home --home-dir /home/daedalus --shell /usr/sbin/nologin daedalus
if [ -d $APP/.git ]; then git -C $APP pull -q --ff-only; else git clone -q $REPO $APP; fi
chown -R daedalus:daedalus $APP

# source data needed to build the database (~0.7 GB; Getty/ULAN are not needed: enrichment is committed)
sudo -u daedalus bash -s <<'BUILD'
set -euo pipefail
cd /opt/daedalus-thread
mkdir -p data/raw/icarus data/raw/iconclass data/raw/naturalearth
ZEN=https://zenodo.org/api/records/18980670/files
for f in data.jsonl train.txt val.txt test.txt; do
  [ -s data/raw/icarus/$f ] || curl -fsSL --retry 5 -o data/raw/icarus/$f "$ZEN/$f/content"
done
echo "92cbffa484f5e4607ba94d215cee88eb  data/raw/icarus/data.jsonl" | md5sum -c -
if [ ! -d data/raw/iconclass/data/.git ]; then
  git init -q data/raw/iconclass/data
  git -C data/raw/iconclass/data fetch -q --depth 1 https://github.com/iconclass/data.git 737ce365e3e6ab5302bafc22428ee37e57becee1
  git -C data/raw/iconclass/data checkout -q FETCH_HEAD
fi
git -C data/raw/iconclass/data log -1 --format='%H %cI' > data/raw/iconclass/SOURCE_COMMIT.txt
[ -s data/raw/naturalearth/ne_10m_admin_0_countries.geojson ] || curl -fsSL --retry 5 -o data/raw/naturalearth/ne_10m_admin_0_countries.geojson \
  https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries.geojson
python3 scripts/build_db.py
BUILD

# configuration (password filled in afterwards), service and web server
[ -f /etc/daedalus-thread.env ] || install -m 640 -o root -g daedalus /dev/null /etc/daedalus-thread.env
grep -q TRUST_PROXY /etc/daedalus-thread.env || printf 'TRUST_PROXY=1\nRATE_PER_MIN=240\n#SITE_USER=\n#SITE_PASSWORD=\n' >> /etc/daedalus-thread.env
install -m 644 $APP/deploy/daedalus-thread.service /etc/systemd/system/daedalus-thread.service
install -m 644 $APP/deploy/Caddyfile /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl enable --now daedalus-thread
systemctl restart daedalus-thread
systemctl reload caddy || systemctl restart caddy
echo "setup done"
