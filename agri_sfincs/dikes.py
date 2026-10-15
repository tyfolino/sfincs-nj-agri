"""Dikes as SFINCS weirs, tide gates as one-way drainage structures.

Why (FINDINGS §10): a 100 m subgrid face averages its pixels half-strip by half-strip
(hydromt_sfincs ``subgrid_q_table``), so a 10–20 m meadow bank never blocks flow and the
tide fills the diked farmland behind it. A ``weirfile`` polyline blocks every u/v face it
crosses below its crest, at any resolution (bight FINDINGS §38: the quadtree engine
honours it). Behind a closed bank rain must still leave, so each farm dike gets a check
valve (drainage type 3: q = C·sqrt(Δh), intake → outfall only; sfincs_discharges.f90).

File formats (SFINCS main, ``read_structure_file`` / ``read_drainage_file``):
  weir   per polyline: a name line, "<nrows> 4", then rows "x y z_crest cd"
  drn    one row per structure: "x_in y_in x_out y_out type C". The FIRST point is the
         intake (water leaves it), the second the outfall; type 3 flows only that way.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds
from shapely.geometry import LineString, MultiLineString

from agri_sfincs import config, domain

#: Broad-crested weir coefficient (bight's Keansburg weir, FINDINGS §38 there).
WEIR_CD = 0.6
#: A notch = a stretch more than NOTCH_DROP_M below the running median crest of
#: NOTCH_WINDOW_M of bank. Gates, culverts and creek crossings are 5–30 m wide in the
#: lidar; a 200 m window keeps the real rise and fall of a bank.
NOTCH_WINDOW_M = 200.0
NOTCH_DROP_M = 0.3
#: Check-valve coefficients (m^2.5/s): C_LO ≈ one 0.8 m (30") pipe, C_HI ≈ four of them or
#: one 1.4 m box (scripts/build_dikes.py).
C_LO, C_HI = 1.5, 6.0


def running_median(z: np.ndarray, s: np.ndarray, window_m: float) -> np.ndarray:
    """Median of ``z`` over |s - s_i| <= window_m / 2, ignoring NaN (s ascending)."""
    out = np.full(z.shape, np.nan)
    lo = np.searchsorted(s, s - window_m / 2, side="left")
    hi = np.searchsorted(s, s + window_m / 2, side="right")
    for i, (a, b) in enumerate(zip(lo, hi)):
        w = z[a:b]
        w = w[np.isfinite(w)]
        if w.size:
            out[i] = np.median(w)
    return out


def fill_notches(z: np.ndarray, s: np.ndarray, window_m: float = NOTCH_WINDOW_M,
                 drop_m: float = NOTCH_DROP_M) -> tuple[np.ndarray, np.ndarray]:  # fmt: skip
    """Raise notch points to the running median; returns (crest, is_notch).

    Never lowers a point. NaN ridge samples (no lidar) take the running median too.
    """
    med = running_median(z, s, window_m)
    notch = np.isfinite(med) & (~np.isfinite(z) | (z < med - drop_m))
    crest = np.where(notch, med, z)
    return crest, notch


def write_weir(path: Path, lines: list[tuple[str, np.ndarray, np.ndarray, np.ndarray]],
               cd: float = WEIR_CD) -> int:  # fmt: skip
    """Write (name, x, y, z_crest) polylines; returns the vertex count. Skips any
    polyline with fewer than 2 finite vertices."""
    n = 0
    with open(path, "w") as f:
        for name, x, y, z in lines:
            ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
            if ok.sum() < 2:
                continue
            f.write(f"{name}\n{int(ok.sum())} 4\n")
            for xi, yi, zi in zip(x[ok], y[ok], z[ok]):
                f.write(f"{xi:.1f} {yi:.1f} {zi:.3f} {cd:.2f}\n")
            n += int(ok.sum())
    return n


def write_drn(path: Path, rows: list[tuple[float, float, float, float]], coef: float,
              dtype: int = 3) -> None:  # fmt: skip
    """Write (x_in, y_in, x_out, y_out) structures, all of one type and coefficient."""
    with open(path, "w") as f:
        for xi, yi, xo, yo in rows:
            f.write(f"{xi:.1f} {yi:.1f} {xo:.1f} {yo:.1f} {dtype:d} {coef:.3f}\n")


def ensure_inp_key(root: Path, key: str, filename: str) -> bool:
    """Make ``sfincs.inp`` carry ``key = filename`` when ``root/filename`` exists.

    hydromt's writer drops keys it does not model (bight ``model._ensure_weirfile_key``),
    and a structure file without its key is silently ignored by SFINCS. Returns whether
    the key is now present."""
    inp = Path(root) / "sfincs.inp"
    if not (Path(root) / filename).is_file():
        return False
    lines = [ln for ln in inp.read_text().splitlines() if ln.split("=")[0].strip() != key]
    lines.append(f"{key:<21}= {filename}")
    inp.write_text("\n".join(lines) + "\n")
    return True


def read_weir(path: Path) -> list[tuple[str, np.ndarray, np.ndarray, np.ndarray]]:
    """Polylines of a SFINCS weir file written by ``write_weir``: (name, x, y, z_crest)."""
    out, lines = [], Path(path).read_text().splitlines()
    i = 0
    while i < len(lines):
        name = lines[i].strip()
        n = int(lines[i + 1].split()[0])
        a = np.array([[float(v) for v in ln.split()[:3]] for ln in lines[i + 2 : i + 2 + n]])
        out.append((name, a[:, 0], a[:, 1], a[:, 2]))
        i += 2 + n
    return out


def cap_crests(lines, cap) -> list:
    """Crest = min(crest, cap(x, y)): a bank worn down to ``cap`` (scalar or callable)."""
    out = []
    for name, x, y, z in lines:
        c = cap(x, y) if callable(cap) else np.full_like(z, float(cap))
        out.append((name, x, y, np.minimum(z, c)))
    return out


def breach(x: np.ndarray, y: np.ndarray, z: np.ndarray, at: int, length_m: float,
           z_breach: float) -> np.ndarray:  # fmt: skip
    """Crests with a breach: vertices within ``length_m`` / 2 (along the line) of vertex
    ``at`` lowered to ``z_breach`` (never raised)."""
    s = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
    out = z.copy()
    hit = np.abs(s - s[at]) <= length_m / 2
    out[hit] = np.minimum(out[hit], z_breach)
    return out


def leveed_areas(crs=None):
    """NLD leveed areas (data/structures/structures.gpkg, scripts/fetch_structures.py), in
    ``crs`` if given."""
    import geopandas as gpd

    la = gpd.read_file(config.STRUCTURES, layer="nld_leveed_areas")
    return la if crs is None else la.to_crs(crs)


class Bed:
    """Window reads of the pre-merged bed (EPSG:4326, ~3.9 m) at UTM points."""

    def __init__(self):
        self.src = rasterio.open(config.ELEV_DIR / "bed_merged.tif")
        self.to_ll = Transformer.from_crs(domain.EPSG, self.src.crs, always_xy=True)

    def sample(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        lon, lat = self.to_ll.transform(x, y)
        pad = 1e-4
        win = from_bounds(lon.min() - pad, lat.min() - pad, lon.max() + pad, lat.max() + pad,
                          self.src.transform).round_offsets().round_lengths()  # fmt: skip
        a = self.src.read(1, window=win, boundless=True, fill_value=np.nan).astype("float64")
        nd = self.src.nodata
        if nd is not None:
            a[a == nd] = np.nan
        tr = self.src.window_transform(win)
        c, r = ~tr * (lon, lat)
        r, c = np.floor(r).astype(int), np.floor(c).astype(int)
        ok = (r >= 0) & (r < a.shape[0]) & (c >= 0) & (c < a.shape[1])
        out = np.full(x.shape, np.nan)
        out[ok] = a[r[ok], c[ok]]
        return out


def lines_of(geom) -> list[LineString]:
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, LineString)]


def slug(system: str) -> str:
    """A dike system's name as a file-name stem ("Middle Neck" -> "middle_neck")."""
    return re.sub(r"[^a-z0-9]+", "_", system.lower()).strip("_")
