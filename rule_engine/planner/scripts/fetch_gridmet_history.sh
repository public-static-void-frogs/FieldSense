#!/bin/bash
# Daily gridMET weather at the sample fields for earlier years, one year at a time:
# download the four yearly CONUS files (about 0.5 GB), sample them, delete them.
#
#   bash rule_engine/planner/scripts/fetch_gridmet_history.sh 1981 2014
#
# Output: data/local/planner/gridmet/<year>.parquet (same schema as the national sample).
set -u
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
CACHE="$REPO/data/local/planner/cache/gridmet"
OUT="$REPO/data/local/planner/gridmet"
PY="${PYTHON:-$REPO/.venv/bin/python}"
mkdir -p "$CACHE" "$OUT"
for year in $(seq "$1" "$2"); do
  [ -s "$OUT/$year.parquet" ] && continue
  for v in tmmx tmmn pr pet; do
    echo "http://thredds.northwestknowledge.net:8080/thredds/fileServer/MET/$v/${v}_$year.nc"
  done | (cd "$CACHE" && xargs -P 4 -n 1 wget -q -c --tries=5)
  if "$PY" "$REPO/data/usa_sample/gridmet.py" --fields "$REPO/data/local/usa_sample/fields.csv" \
      --cache "$CACHE" --out "$OUT" --years "$year"; then
    rm -f "$CACHE"/*_"$year".nc
    echo "$year done"
  else
    echo "$year FAILED"
  fi
done
