#!/usr/bin/env python3
"""SMAP L4 SPL4SMGP (v8) soil moisture etc. for the field coordinates in csb_bounds output (Parquet).

Product: SMAP L4 Global 3-hourly 9 km EASE-Grid Surface and Root Zone Soil Moisture, NSIDC DAAC, short name SPL4SMGP,
version 8 (earthaccess version string "008", unverified), HDF5, EASE-Grid 2.0 Global (EPSG:6933), 1624 x 3856,
8 files per UTC day (centre times 01:30, 04:30 ... 22:30), from 2015-03-31. Model output with assimilated SMAP
brightness temperatures, NOT a measurement at the field; 9 km is the grid spacing.

NOTE: NSIDC reports a geolocation issue for L4 products from 2026-05-14 to 2026-07-28 (being reprocessed). Treat that
period with caution and re-download after reprocessing.

Same two-table design as the other csb_* scripts (all fields in one 9 km cell get identical values):
  field_cell_map.parquet   CSBID -> cell_id
  cells.parquet            cell_id, row, col, cell_lat, cell_lon, n_fields
  smap_daily.parquet       cell_id, date, n_files, <variables>        (--resolution daily, default: mean of the day's files)
  smap_3hourly.parquet     cell_id, timestamp, <variables>            (--resolution 3hourly)

Steps (resumable)
  plan     snap centroids to the EASE-Grid 2.0 9 km grid (row, col), write cells + map
  extract  per window of days: download files, read only the planned cells, write a part file per day, delete the download
  merge    stream the parts into one Parquet file

Grid assumption: upper-left corner x=-17367530.445 m, y=7314540.83 m, cell size 9008.055 m (EASE-Grid 2.0 9 km).
The extractor compares the row/col cell centres with the file's own cell_lat/cell_lon and stops on mismatch.
Daily mean = mean of the available files of the UTC day; n_files tells how many (8 = complete); incomplete days are retried on re-run.
Fill values (file attribute _FillValue, else -9999) become NaN.

Access: NASA Earthdata Login through `earthaccess` (EARTHDATA_USERNAME / EARTHDATA_PASSWORD or interactive). The NSIDC
application may need approving in your Earthdata profile (Applications > Authorized Apps). Files already in --cache are used as is.

Examples
  python csb_smap.py plan    --bounds ./csb_bounds --out ./smap --county 19015
  python csb_smap.py extract --out ./smap --start 2018-01-01 --end 2025-12-31 --cache ./smap_files
  python csb_smap.py merge   --out ./smap

Not tested against the live service (blocked in the build sandbox); tested on synthetic HDF5 files.
Deps: pip install pandas pyarrow numpy h5py pyproj earthaccess
"""
import argparse, datetime as dt, os, re, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

SHORT_NAME = "SPL4SMGP"
NROW, NCOL = 1624, 3856
X0, Y0, DX = -17367530.445, 7314540.83, 9008.055
DEFAULT_VARS = ["sm_surface", "sm_rootzone", "sm_profile", "sm_surface_wetness", "sm_rootzone_wetness",
                "sm_profile_wetness", "sm_rootzone_pctl", "sm_profile_pctl", "surface_temp", "soil_temp_layer1",
                "snow_mass", "snow_depth", "land_evapotranspiration_flux", "overland_runoff_flux",
                "baseflow_flux", "leaf_area_index"]


# ------------------------------------------------------------------ grid
def _tr():
    from pyproj import Transformer
    return (Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True),
            Transformer.from_crs("EPSG:6933", "EPSG:4326", always_xy=True))


def lonlat_to_rowcol(lon, lat):
    to_m, _ = _tr()
    x, y = to_m.transform(np.asarray(lon, "float64"), np.asarray(lat, "float64"))
    col = np.floor((x - X0) / DX).astype(int)
    row = np.floor((Y0 - y) / DX).astype(int)
    return np.clip(row, 0, NROW - 1), np.clip(col, 0, NCOL - 1)


def rowcol_to_lonlat(row, col):
    _, to_deg = _tr()
    x = X0 + (np.asarray(col) + 0.5) * DX
    y = Y0 - (np.asarray(row) + 0.5) * DX
    lon, lat = to_deg.transform(x, y)
    return lon, lat


# ------------------------------------------------------------------ field selection (duplicated on purpose)
def load_fields(a):
    if a.points:
        p = pd.read_csv(a.points)
        low = {c.lower(): c for c in p.columns}
        pick = lambda *names: next((low[n] for n in names if n in low), None)
        ic, lo, la = pick("id", "csbid"), pick("lon", "longitude", "centroid_lon"), pick("lat", "latitude", "centroid_lat")
        if not (ic and lo and la):
            sys.exit(f"--points CSV needs id, lon, lat columns; found {list(p.columns)}")
        return pd.DataFrame({"CSBID": p[ic].astype(str), "centroid_lon": p[lo].astype(float), "centroid_lat": p[la].astype(float)})
    if not a.bounds:
        sys.exit("give --bounds DIR or --points CSV")
    ids = None
    if a.ids:
        raw = Path(a.ids).read_text().splitlines()
        if raw and "CSBID" in raw[0].split(","):
            col = raw[0].split(",").index("CSBID")
            ids = {ln.split(",")[col].strip() for ln in raw[1:] if ln.strip()}
        else:
            ids = {ln.split(",")[0].strip() for ln in raw if ln.strip()}
    files = sorted(Path(a.bounds).glob("batch_*.parquet"))
    if not files:
        sys.exit(f"no batch_*.parquet in {a.bounds}")
    parts, n = [], 0
    for f in files:
        have = set(pq.read_schema(f).names)
        cols = ["CSBID", "centroid_lon", "centroid_lat"] + [c for c in ("STATEFIPS", "CNTYFIPS") if c in have and (a.state or a.county)]
        df = pd.read_parquet(f, columns=cols)
        if a.state:
            df = df[df["STATEFIPS"] == str(a.state).zfill(2)]
        if a.county:
            df = df[df["CNTYFIPS"] == str(a.county).zfill(5)]
        if ids is not None:
            df = df[df["CSBID"].isin(ids)]
        if a.limit:
            df = df.head(a.limit - n)
        if len(df):
            parts.append(df[["CSBID", "centroid_lon", "centroid_lat"]]); n += len(df)
        if a.limit and n >= a.limit:
            break
    if not parts:
        sys.exit("no fields matched the selection")
    return pd.concat(parts, ignore_index=True)


# ------------------------------------------------------------------ plan
def cmd_plan(a):
    f = load_fields(a)
    row, col = lonlat_to_rowcol(f["centroid_lon"].to_numpy(), f["centroid_lat"].to_numpy())
    f["row"], f["col"] = row, col
    f["cell_id"] = [f"r{r:04d}c{c:04d}" for r, c in zip(row, col)]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    cells = f.groupby(["cell_id", "row", "col"]).size().rename("n_fields").reset_index()
    lon, lat = rowcol_to_lonlat(cells["row"].to_numpy(), cells["col"].to_numpy())
    cells["cell_lon"], cells["cell_lat"] = np.round(lon, 5), np.round(lat, 5)
    f[["CSBID", "cell_id"]].to_parquet(out / "field_cell_map.parquet", compression="zstd", index=False)
    cells.to_parquet(out / "cells.parquet", compression="zstd", index=False)
    print(f"{len(f):,} fields -> {len(cells):,} SMAP 9 km cells")


# ------------------------------------------------------------------ extract
FN = re.compile(r"_(\d{8})T(\d{6})_")


def stamp_of(path):
    m = FN.search(Path(str(path)).name)
    return dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S") if m else None


def check_h5(p):
    """True if the file starts with the HDF5 signature. Otherwise move it aside (name + '.invalid') and say what it holds."""
    p = Path(p)
    try:
        with open(p, "rb") as f:
            head = f.read(512)
    except OSError:
        return False
    if head[:8] == b"\x89HDF\r\n\x1a\n":
        return True
    snippet = head[:200].decode("utf-8", "replace").replace("\n", " ")
    bad = p.with_name(p.name + ".invalid")
    try:
        bad.unlink(missing_ok=True); p.rename(bad)
    except OSError:
        pass
    print(f"INVALID (not HDF5): {p.name} ({p.stat().st_size if p.exists() else bad.stat().st_size:,} bytes), starts with: {snippet!r}\n"
          f"  moved to {bad.name}. This is usually an HTML login/authorization page or a truncated download: check the Earthdata "
          f"credentials and that the NSIDC DAAC application is approved in your Earthdata profile.", file=sys.stderr)
    return False


def local_files(cache):
    d = {}
    for p in Path(cache).glob("*.h5"):
        if stamp_of(p) and check_h5(p):
            d[stamp_of(p)] = p
    return d


_LOGGED = False


def ea_login():
    global _LOGGED
    if _LOGGED:
        return
    import earthaccess
    if os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD") and os.environ.get("EARTHDATA_TOKEN"):
        # earthaccess prefers EARTHDATA_TOKEN when it is set; a bearer token sent on to the pre-signed S3 URL gives "400 Bad Request"
        os.environ.pop("EARTHDATA_TOKEN")
        print("EARTHDATA_TOKEN ignored in this process (username/password are used for downloads)", file=sys.stderr)
    if not (os.environ.get("EARTHDATA_USERNAME") and os.environ.get("EARTHDATA_PASSWORD")) and not os.environ.get("EARTHDATA_TOKEN"):
        import getpass                                  # ask once ourselves, so the same credentials can be used by the fallback downloader
        os.environ["EARTHDATA_USERNAME"] = input("Enter your Earthdata Login username: ").strip()
        os.environ["EARTHDATA_PASSWORD"] = getpass.getpass("Enter your Earthdata password: ")
    earthaccess.login(strategy="environment")
    _LOGGED = True


class EDLSession:
    """NASA's documented recipe: a requests session that keeps the Earthdata credentials on the hops to/from urs.earthdata.nasa.gov
    but drops the Authorization header when leaving for another host (e.g. the pre-signed S3 URL)."""

    def __new__(cls, user, password, auth_host="urs.earthdata.nasa.gov"):
        import requests
        from urllib.parse import urlparse

        class _S(requests.Session):
            def rebuild_auth(self, prepared_request, response):
                h = prepared_request.headers
                if "Authorization" in h:
                    orig, red = urlparse(response.request.url).netloc, urlparse(prepared_request.url).netloc
                    if orig != red and red != auth_host and orig != auth_host:
                        del h["Authorization"]
        sess = _S()
        sess.auth = (user, password)
        return sess


def edl_download(url, dst, session):
    """GET with automatic redirects through an EDLSession. Returns (path or None, diagnostics)."""
    dst = Path(dst); part = Path(str(dst) + ".part")
    r = session.get(url, stream=True, timeout=300)
    if r.status_code != 200:
        info = f"HTTP {r.status_code} {r.url.split('?')[0]}: {r.text[:200]!r} headers={ {k: v for k, v in r.headers.items() if k.lower() in ('www-authenticate', 'server', 'x-amz-request-id', 'content-type')} }"
        r.close(); return None, info
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(part, "wb") as fh:
        for chunk in r.iter_content(1 << 20): fh.write(chunk)
    part.replace(dst)
    return dst, "ok"


def clean_download(url, dst, user, password, auth_host="urs.earthdata.nasa.gov", session=None):
    """Earthdata download where credentials go ONLY to the login host.
    NSIDC answers 400 (empty JSON body) when a request to data.nsidc.earthdatacloud.nasa.gov already carries an Authorization header
    (bearer token or basic auth sent up front). Here the first request is anonymous, the 302 to urs.earthdata.nasa.gov gets the basic
    credentials, the cookies of the session carry the login back, and the final pre-signed URL is fetched without any header.
    Returns (path or None, diagnostics)."""
    import requests
    from urllib.parse import urljoin, urlparse
    dst = Path(dst); part = Path(str(dst) + ".part")
    s = session or requests.Session()
    s.headers.update({"User-Agent": "csb_smap/1.0 (+earthdata)"})
    cur = url
    for _ in range(15):
        host = urlparse(cur).netloc
        kw = {"auth": (user, password)} if host == auth_host else {}
        r = s.get(cur, allow_redirects=False, stream=True, timeout=300, **kw)
        if r.status_code in (301, 302, 303, 307, 308):
            cur = urljoin(cur, r.headers["Location"]); r.close(); continue
        if r.status_code != 200:
            info = f"HTTP {r.status_code} at {host}{urlparse(cur).path[:60]}: {r.text[:200]!r}"
            r.close(); return None, info
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(part, "wb") as fh:
            for chunk in r.iter_content(1 << 20): fh.write(chunk)
        part.replace(dst)
        return dst, "ok"
    return None, "too many redirects"


def fetch_urls(urls, cache, workers=4):
    """Download .h5 URLs with clean_download in a thread pool (one session per file). Existing valid files are kept.
    Returns (list of paths, list of 'url: diagnostics' failures)."""
    from concurrent.futures import ThreadPoolExecutor
    user, pw = os.environ.get("EARTHDATA_USERNAME"), os.environ.get("EARTHDATA_PASSWORD")
    if not (user and pw):
        sys.exit("EARTHDATA_USERNAME and EARTHDATA_PASSWORD must be set for this downloader")
    Path(cache).mkdir(parents=True, exist_ok=True)

    def one(u):
        dst = Path(cache) / u.rsplit("/", 1)[-1]
        if dst.exists() and check_h5(dst):
            return dst, "cached"
        for attempt in range(3):                    # transient errors: short retry
            try:
                p, info = clean_download(u, dst, user, pw)
            except Exception as e:
                p, info = None, f"{type(e).__name__}: {str(e)[:120]}"
            if p: return p, info
            if info.startswith("HTTP 4") and not info.startswith("HTTP 429"): break
            time.sleep(2 * (attempt + 1))
        return None, info
    ok, bad = [], []
    with ThreadPoolExecutor(workers) as ex:
        for u, (p, info) in zip(urls, ex.map(one, urls)):
            (ok if p else bad).append(str(p) if p else f"{u.rsplit('/', 1)[-1]}: {info}")
    return ok, bad


def manual_download(url, dst, session, internal=lambda netloc: netloc.endswith(".nasa.gov"), plain_get=None, max_hops=10):
    """Download following redirects by hand: the authenticated session is used only for NASA hosts (Earthdata login included); the final
    pre-signed storage URL (S3) is fetched WITHOUT any Authorization header or cookies - S3 answers 400 when a second auth mechanism is present.
    Returns (path or None, 'status/body snippet' for diagnostics)."""
    import requests
    from urllib.parse import urljoin, urlparse
    plain_get = plain_get or requests.get
    dst = Path(dst); part = Path(str(dst) + ".part")
    cur = url
    for _ in range(max_hops):
        host = urlparse(cur).netloc
        r = (session.get(cur, allow_redirects=False, stream=True, timeout=300) if internal(host)
             else plain_get(cur, allow_redirects=False, stream=True, timeout=300))
        if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
            cur = urljoin(cur, r.headers["Location"]); r.close(); continue
        if r.status_code != 200:
            body = r.text[:300] if hasattr(r, "text") else ""
            hd = {k: v for k, v in r.headers.items() if k.lower() in ("www-authenticate", "server", "x-amz-request-id", "content-type")}
            r.close()
            return None, f"HTTP {r.status_code} from {host}: {body!r} {hd}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(part, "wb") as fh:
            for chunk in r.iter_content(1 << 20): fh.write(chunk)
        part.replace(dst)
        return dst, "ok"
    return None, "too many redirects"


def download_days(a, days):
    import earthaccess
    ea_login()
    days = sorted(days)
    res = earthaccess.search_data(short_name=SHORT_NAME, version=a.version,
                                  temporal=(days[0].isoformat(), (days[-1] + dt.timedelta(days=1)).isoformat()))
    want = set(days)
    sel = []
    for g in res:
        try:
            s = stamp_of(g.data_links()[0])
        except Exception:
            s = None
        if s is None or s.date() in want:
            sel.append(g)
    print(f"search {days[0]}..{days[-1]}: {len(res)} granules found, {len(sel)} wanted", flush=True)
    if not sel:
        print("  no granules (not published yet, or wrong short name/version)", file=sys.stderr)
        return {}
    paths, left = [], []
    urls = {}
    for g in sel:
        try:
            urls[g] = [l for l in g.data_links() if l.endswith(".h5")][0]
        except Exception:
            left.append(g)
    ok, bad = fetch_urls(list(urls.values()), str(a.cache), workers=a.workers)
    paths += ok
    bad_names = {b.split(":", 1)[0] for b in bad}
    left += [g for g, u in urls.items() if u.rsplit("/", 1)[-1] in bad_names]
    print(f"  clean Earthdata download: {len(ok)} ok, {len(bad)} failed" + (f"; first failure: {bad[0]}" if bad else ""), flush=True)
    if left:
        sel = left
        try:
            paths += earthaccess.download(sel, str(a.cache))
        except Exception as e:
            if type(e).__name__ == "EulaNotAccepted":
                sys.exit("Earthdata account has not approved the data provider application (EULA).\n"
                         "https://urs.earthdata.nasa.gov -> Applications -> Authorized Apps -> Approve More Applications "
                         "-> approve the NSIDC DAAC application, then re-run.\n" f"Details: {e}")
            print(f"  earthaccess bulk download failed ({type(e).__name__}: {str(e)[:200]}); trying granule by granule", file=sys.stderr)
            failed = []
            for g in sel:
                try:
                    paths += earthaccess.download([g], str(a.cache), threads=1)
                except Exception as e2:
                    try:
                        url = [l for l in g.data_links() if l.endswith(".h5")][0]
                        p, info = manual_download(url, Path(a.cache) / url.rsplit("/", 1)[-1], earthaccess.get_requests_https_session())
                    except Exception as e3:
                        p, info = None, f"{type(e3).__name__}: {str(e3)[:160]}"
                    if p: paths.append(str(p))
                    else: failed.append(f"earthaccess: {type(e2).__name__}: {str(e2)[:120]} | manual: {info}")
            print(f"  {len(paths)} granules available after fallbacks, {len(failed)} failed", file=sys.stderr)
            if sel and not paths:
                sys.exit("No granule could be downloaded.\n"
                         + (f"  clean download: {bad[0]}\n" if bad else "")
                         + (f"  fallbacks: {failed[0]}\n" if failed else "")
                         + "Check: NSIDC DAAC application approved in the Earthdata profile; system clock; VPN/proxy; pip install -U earthaccess.\n"
                         "Workaround: order the files in Earthdata Search, save the list of links to a text file and run\n"
                         "  python csb_smap.py fetch --urls-file links.txt --cache ./smap_files   (or download them in the browser into --cache).")
    return {stamp_of(p): Path(p) for p in paths if stamp_of(p)}


def find_dataset(h5, name):
    hit = []
    h5.visititems(lambda n, o: hit.append(n) if n.split("/")[-1] == name and hasattr(o, "shape") else None)
    return hit[0] if hit else None


def read_cells(path, cells, variables, verify):
    import h5py
    rows, cols = cells["row"].to_numpy(), cells["col"].to_numpy()
    with h5py.File(path, "r") as h:
        if verify:
            la, lo = find_dataset(h, "cell_lat"), find_dataset(h, "cell_lon")
            if la and lo:
                k = np.unique(np.linspace(0, len(rows) - 1, min(len(rows), 200)).astype(int))
                flat, flon = h[la][()][rows[k], cols[k]], h[lo][()][rows[k], cols[k]]
                clon, clat = rowcol_to_lonlat(rows[k], cols[k])
                bad = (np.abs(flat - clat) > 0.05) | (np.abs(flon - clon) > 0.05)
                if bad.any():
                    sys.exit(f"grid mismatch in {path}: {bad.sum()} of {len(k)} sampled cells differ from the file's cell_lat/cell_lon by >0.05 deg. "
                             "The assumed EASE-Grid constants are wrong for this product; stop and report.")
            else:
                print("WARNING: no cell_lat/cell_lon in file; grid not verified", file=sys.stderr)
        out, missing = {}, []
        for v in variables:
            p = find_dataset(h, v)
            if p is None:
                missing.append(v); continue
            ds = h[p]
            arr = ds[()].astype("float64")
            fv = ds.attrs.get("_FillValue", -9999.0)
            fv = float(np.asarray(fv).ravel()[0])
            arr[arr == fv] = np.nan
            out[v] = arr[rows, cols].astype("float32")
    return out, missing


def cmd_extract(a):
    out = Path(a.out)
    cells = pd.read_parquet(out / "cells.parquet")
    sub = "daily" if a.resolution == "daily" else "hourly"
    (out / sub).mkdir(exist_ok=True); Path(a.cache).mkdir(parents=True, exist_ok=True)
    s, e = dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end)
    days = [s + dt.timedelta(days=k) for k in range((e - s).days + 1)]

    def done(d):
        f = out / sub / f"{d:%Y%m%d}.parquet"
        if not f.exists():
            return False
        if a.resolution != "daily":
            return True
        t = pq.read_table(f, columns=["n_files"]).slice(0, 1).to_pylist()
        return bool(t) and t[0]["n_files"] >= 8                  # incomplete days are redone
    todo = [d for d in days if not done(d)]
    print(f"{len(todo)} of {len(days)} days to extract; {len(cells):,} cells", flush=True)
    verified, warned, nwritten, nmissing = False, False, 0, 0
    for c0 in range(0, len(todo), a.window):
        chunk = todo[c0:c0 + a.window]
        files = local_files(a.cache)
        need = [d for d in chunk if sum(1 for t in files if t.date() == d) < 8]
        downloaded = set()
        if need and not a.no_download:
            got = download_days(a, need)
            got = {t: p for t, p in got.items() if check_h5(p)}      # drop HTML error pages saved as .h5
            files.update(got); downloaded = set(got.values())
        for d in chunk:
            fl = sorted((t, p) for t, p in files.items() if t.date() == d)
            if not fl:
                nmissing += 1; print(f"{d}: no files", file=sys.stderr); continue
            frames = []
            for t, p in fl:
                vals, miss = read_cells(p, cells, a.variables, verify=not verified)
                verified = True
                if miss and not warned:
                    print(f"WARNING: variables not found in file, skipped: {miss}", file=sys.stderr); warned = True
                frames.append(pd.DataFrame({"cell_id": cells["cell_id"].to_numpy(), "timestamp": pd.Timestamp(t), **vals}))
            df = pd.concat(frames, ignore_index=True)
            if a.resolution == "daily":
                vcols = [c for c in df.columns if c not in ("cell_id", "timestamp")]
                g = df.groupby("cell_id", sort=False)[vcols].mean().reset_index()
                g.insert(1, "date", pd.Timestamp(d)); g.insert(2, "n_files", len(fl))
                df = g
            dst = out / sub / f"{d:%Y%m%d}.parquet"
            tmp = Path(str(dst) + ".tmp"); df.to_parquet(tmp, compression="zstd", index=False); tmp.rename(dst)
            nwritten += 1
            if not a.keep_files:
                for _, p in fl:
                    if p in downloaded:
                        p.unlink(missing_ok=True)
        print(f"{min(c0 + a.window, len(todo))}/{len(todo)} days processed", flush=True)
    print(f"extract finished: {nwritten} days written, {nmissing} days without files. Re-run to retry missing/incomplete days.")


def cmd_fetch(a):
    """Download the .h5 links of a list (Earthdata Search 'Download Data' page / links file) into --cache."""
    urls = [ln.strip() for ln in Path(a.urls_file).read_text(encoding="utf-8").splitlines() if ln.strip().startswith("http")]
    urls = [u for u in urls if u.split("?")[0].endswith(".h5")]
    if not urls: sys.exit("no .h5 links found in --urls-file")
    print(f"{len(urls)} .h5 links", flush=True)
    ok, bad = fetch_urls(urls, a.cache, workers=a.workers)
    print(f"downloaded/kept {len(ok)}, failed {len(bad)} -> {a.cache}")
    for b in bad[:10]: print("  FAILED", b, file=sys.stderr)
    if bad and not ok:
        sys.exit("all downloads failed (see above). If the same links work in the browser, save them from there into --cache.")


def cmd_merge(a):
    out = Path(a.out)
    sub, name = ("daily", "smap_daily") if a.resolution == "daily" else ("hourly", "smap_3hourly")
    parts = sorted((out / sub).glob("*.parquet"))
    if not parts:
        sys.exit("no parts; run extract first")
    dst = out / f"{name}.parquet"
    w, n = None, 0
    for f in parts:
        t = pq.read_table(f)
        w = w or pq.ParquetWriter(dst, t.schema, compression="zstd")
        w.write_table(t.cast(w.schema)); n += t.num_rows
    w.close()
    print(f"wrote {dst}: {n:,} rows from {len(parts)} days")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    pl = sp.add_parser("plan")
    pl.add_argument("--bounds"); pl.add_argument("--points"); pl.add_argument("--state"); pl.add_argument("--county")
    pl.add_argument("--ids"); pl.add_argument("--limit", type=int); pl.add_argument("--out", required=True)
    pl.set_defaults(fn=cmd_plan)
    ex = sp.add_parser("extract")
    ex.add_argument("--out", required=True)
    ex.add_argument("--start", required=True, help="YYYY-MM-DD (UTC)")
    ex.add_argument("--end", default=(dt.date.today() - dt.timedelta(days=7)).isoformat(), help="YYYY-MM-DD (default today-7d)")
    ex.add_argument("--version", default="008", help="earthaccess version string for SPL4SMGP v8 (unverified)")
    ex.add_argument("--variables", nargs="+", default=DEFAULT_VARS)
    ex.add_argument("--resolution", choices=["daily", "3hourly"], default="daily")
    ex.add_argument("--cache", default="./smap_files")
    ex.add_argument("--window", type=int, default=3, help="days downloaded, processed and deleted per round (8 files per day)")
    ex.add_argument("--workers", type=int, default=4, help="parallel downloads")
    ex.add_argument("--no-download", action="store_true"); ex.add_argument("--keep-files", action="store_true")
    ex.set_defaults(fn=cmd_extract)
    fe = sp.add_parser("fetch", help="download the .h5 links listed in a text file (e.g. saved from Earthdata Search)")
    fe.add_argument("--urls-file", required=True); fe.add_argument("--cache", default="./smap_files"); fe.add_argument("--workers", type=int, default=4)
    fe.set_defaults(fn=cmd_fetch)
    me = sp.add_parser("merge"); me.add_argument("--out", required=True); me.add_argument("--resolution", choices=["daily", "3hourly"], default="daily"); me.set_defaults(fn=cmd_merge)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()