# Daedalus Thread: builds the SQLite database from source data, then serves it. Stdlib Python only.
#   docker build -t daedalus-thread . && docker run -p 8080:8080 daedalus-thread
# The build downloads ICARUS metadata (~630 MB, MD5-verified), Iconclass and Natural Earth borders.
# Getty ULAN/TGN are not needed: artist geography comes from the committed data/enrichment/ output.

FROM python:3.13-slim AS build
ARG ICONCLASS_COMMIT=737ce365e3e6ab5302bafc22428ee37e57becee1
RUN apt-get update && apt-get install -y --no-install-recommends curl git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN mkdir -p data/raw/icarus data/raw/iconclass \
 && for f in data.jsonl train.txt val.txt test.txt; do \
      curl -fsSL --retry 5 -o "data/raw/icarus/$f" "https://zenodo.org/api/records/18980670/files/$f/content"; done \
 && echo "92cbffa484f5e4607ba94d215cee88eb  data/raw/icarus/data.jsonl" | md5sum -c - \
 && git init -q data/raw/iconclass/data \
 && git -C data/raw/iconclass/data fetch -q --depth 1 https://github.com/iconclass/data.git "$ICONCLASS_COMMIT" \
 && git -C data/raw/iconclass/data checkout -q FETCH_HEAD \
 && git -C data/raw/iconclass/data log -1 --format='%H %cI' > data/raw/iconclass/SOURCE_COMMIT.txt \
 && mkdir -p data/raw/naturalearth \
 && curl -fsSL --retry 5 -o data/raw/naturalearth/ne_10m_admin_0_countries.geojson \
      https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries.geojson
COPY etl etl
COPY scripts scripts
COPY taxonomy taxonomy
# artist geography is a committed batch output (scripts/enrich_creators.py); the build needs no Getty data or network
COPY data/enrichment data/enrichment
COPY web/assets/basemap.json web/assets/basemap.json
RUN python3 scripts/build_db.py

FROM python:3.13-slim
WORKDIR /app
COPY server server
COPY web web
COPY --from=build /app/data/db/daedalus.sqlite data/db/daedalus.sqlite
ENV HOST=0.0.0.0 PORT=8080 PYTHONUNBUFFERED=1
EXPOSE 8080
USER nobody
CMD ["python3", "server/app.py"]
