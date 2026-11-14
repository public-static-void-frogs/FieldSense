#!/bin/bash
# download gridMET yearly files (tmmx, tmmn, pr, pet) into the cache dir given as $1
# usage: download_gridmet.sh <cache dir> [first year, default 2021] [last year, default 2025]
cd "$1" || exit 1
for y in $(seq "${2:-2021}" "${3:-2025}"); do for v in tmmx tmmn pr pet; do
  echo "http://thredds.northwestknowledge.net:8080/thredds/fileServer/MET/$v/${v}_$y.nc"
done; done | xargs -P 4 -n 1 wget -q -c
ls | wc -l
du -sh .
