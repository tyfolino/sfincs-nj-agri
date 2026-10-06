"""Resume a preempted SFINCS solve from its newest restart file, and stitch the pieces.

Copied from nj_bight_sfincs ``nj_sfincs/restart.py`` (2026-09-10; ported 2026-10-05) and
adapted; never imported from there. Changes: a restart file must be COMPLETE (its
Fortran record chain is checked) and the map must hold a valid ``zsmax`` block ending at
its stamp; an unreadable output file means a fresh start, never a resume onto a hole;
the cumulative map fields (``cumprcp`` / ``cuminf``) are offset across segments; the
stitch is idempotent if a job dies mid-stitch; ``finish`` keeps the restart file AT
``tstop`` (the state a following year could start from) and refuses to clean up a run
that has not reached ``tstop``.

WHY: the Amarel ``main`` partition preempts and ``--requeue`` re-runs the batch script
from the top. A year-long run is 5-7 h on 16 threads; without this a requeue starts over.

HOW SFINCS RESTARTS (main branch, the engine in config.SFINCS_BIN; source
~/nj_sandy_sfincs/SFINCS-src-main/source/src, the build commit a9b7580 differs from HEAD
only in snapwave_boundaries.f90)
-------------------------------------------------------------------------------------
* ``dtrstout = <s>`` writes ``sfincs.YYYYMMDD.HHMMSS.rst`` every ``<s>`` s from ``tstart``
  (sfincs_output.f90:39-43, sfincs_lib.f90:447-456), the last one AT ``tstop``. It is
  written AFTER that step's map and max output (sfincs_output.f90 ``write_output``).
* The file (``write_rst_file``, sfincs_output.f90:657-725) is Fortran unformatted
  sequential: rsttype, then zs (real*4), q, uvmean and, for ``cnb`` infiltration,
  ``scs_Se`` (rsttype 4, sfincs_output.f90:693-700). The reader
  (sfincs_initial_conditions.F90:185-263) restores zs, q, uvmean and, for rsttype 4,
  ``scs_Se`` (l.237-241), after the infiltration init has read ``seff`` from the
  quadtree file, so the restart value wins. There is NO clock in it: resuming rewrites
  ``sfincs.inp`` with ``tstart`` = the stamp and ``rstfile`` = the file.
* NOT restored: the rest of the cnb state, ``scs_P1 / scs_F1 / scs_S1 / scs_rain /
  rain_T1`` (allocated to 0 in sfincs_infiltration.f90:382-391, updated at l.724-821).
  So (a) a resume during rain starts a NEW SCS event (initial abstraction applied again
  to the remaining Se: more infiltration, less runoff for the rest of that storm), and
  (b) the recovery clock ``rain_T1`` restarts at 0, which delays recovery by
  0.06 / kr hours (l.802) = at most 0.06 x smax of Se per resume per cell. Also not
  restored: ``cumprcp`` / ``cuminf`` (output accumulators, restart at 0: offset by
  ``stitch``), and drainage gate state ``drainage_status`` (only for gate types 4/5,
  sfincs_discharges.f90:194-201; check valves, type 3, are stateless). A resume is
  therefore close to, not bit-identical with, a straight run (FINDINGS §18). To keep it
  close, ``plan`` prefers a stamp with no rain anywhere in the forcing over the
  ``DRY_HOURS`` before it (no cnb event to split), up to ``DRY_LOOKBACK_S`` behind the
  newest usable one; 70% of the daily stamps of 2023 qualify.
* ``tspinup`` ramps the BOUNDARY from ``zsini`` over the first ``tspinup`` s after
  ``tstart`` (sfincs_boundaries.f90:851-853, sfincs_input.f90:381). A resume sets it to 0.
* SFINCS creates ``sfincs_map.nc`` / ``sfincs_his.nc`` afresh at start (NF90_CLOBBER,
  sfincs_ncoutput.F90:239, 805), so the earlier segment's output is moved aside first.
  The map file is synced after each MAP record (l.1272) but not after a MAX record, so
  a killed run's last ``zsmax`` block may be missing: ``written_until`` checks it.

STITCHING RULES
---------------
Segments are the retired outputs, in order, plus the final run dir. Each segment owns
the records from its own ``tstart`` up to AND including the next segment's ``tstart``
(the record at the resume instant is the one a straight run writes: SFINCS samples
output at the first step at or after each output time, and the resumed run's first
record is the restart state itself); a later segment owns only records after the last
one already taken. ``zsmax`` blocks carry the time they END (``timemax``): a segment
owns the blocks with ``start < timemax <= next_start``.
Unwritten blocks (netCDF float fill) are dropped. Cumulative fields (``CUMULATIVE``)
restart at 0 in each segment, so each later segment gets the previous segment's value at
its last record at or before the resume instant added.

🔴 ``dtmaxout`` MUST DIVIDE ``dtrstout`` (both 86400 s in agri_sfincs.events), or a
resume point falls inside a max block; ``plan`` refuses stamps off the dtmaxout lattice.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

INP_FMT = "%Y%m%d %H%M%S"
RST_RE = re.compile(r"^sfincs\.(\d{8})\.(\d{6})\.rst$")
SEG_DIR = "restart_segments"
ORIG_INP = "sfincs.inp.orig"
HISTORY = "restart_history.txt"
#: Moved into a segment on resume. sfincs_log.txt is hpc/sfincs_run.slurm's stdout.
OUTPUTS = ("sfincs_map.nc", "sfincs_his.nc", "sfincs.log", "sfincs_log.txt")
STITCHED = ("sfincs_map.nc", "sfincs_his.nc")
LOGS = ("sfincs.log", "sfincs_log.txt")
#: Accumulated since the solver started: restart at 0 in a resumed segment.
CUMULATIVE = ("cumprcp", "cuminf", "point_cumprcp", "point_cuminf")
NC_FLOAT_FILL = 9.96e36  # netCDF default float fill; an unwritten zsmax block reads this
#: Prefer a restart stamp with no rain anywhere in the forcing over the hours before it
#: (a resume during rain splits the cnb event: FINDINGS §18), going back at most this far
#: behind the newest usable stamp. A day of a year run costs ~1 min of compute.
DRY_HOURS = 3.0
DRY_LOOKBACK_S = 5 * 86400.0
#: Records per rsttype (sfincs_output.f90 write_rst_file): rsttype + zs + q + uvmean (+ ...)
RST_RECORDS = {1: 4, 2: 3, 3: 2, 4: 5, 5: 6, 6: 5}

# ── sfincs.inp text helpers ──────────────────────────────────────────────────


def inp_get(text: str, key: str) -> str | None:
    for line in text.splitlines():
        if "=" in line and line.split("=", 1)[0].strip() == key:
            return line.split("=", 1)[1].strip()
    return None


def inp_set(text: str, values: dict[str, str]) -> str:
    """Replace or append ``key = value`` lines (SFINCS' 20-column layout)."""
    lines = text.splitlines()
    done = set()
    for i, line in enumerate(lines):
        if "=" not in line:
            continue
        k = line.split("=", 1)[0].strip()
        if k in values:
            lines[i] = f"{k:<20} = {values[k]}"
            done.add(k)
    for k, v in values.items():
        if k not in done:
            lines.append(f"{k:<20} = {v}")
    return "\n".join(lines) + "\n"


def inp_datetime(text: str, key: str) -> datetime:
    v = inp_get(text, key)
    if v is None:
        raise KeyError(f"{key!r} not in sfincs.inp")
    return datetime.strptime(v, INP_FMT)


def resume_inp(text: str, rst_name: str, t_resume: datetime) -> str:
    """The ORIGINAL inp rewritten to start at ``t_resume`` from ``rst_name``."""
    return inp_set(text, {"tstart": t_resume.strftime(INP_FMT), "tspinup": "0.0",
                          "rstfile": rst_name})  # fmt: skip


# ── discovery ────────────────────────────────────────────────────────────────


def rst_stamp(name: str) -> datetime | None:
    m = RST_RE.match(name)
    return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S") if m else None


def restart_files(model_dir: Path) -> list[tuple[datetime, Path]]:
    out = [(rst_stamp(p.name), p) for p in Path(model_dir).iterdir() if rst_stamp(p.name)]
    return sorted(out)


def rst_type(path: Path) -> int | None:
    """rsttype of a COMPLETE restart file, else None.

    Walks the Fortran sequential record chain (4-byte length, payload, same length):
    it must end exactly at EOF with the record count of its rsttype. A file the solver
    was writing when it was killed fails this."""
    try:
        b = Path(path).read_bytes()
    except OSError:
        return None
    pos, lens = 0, []
    while pos < len(b):
        if pos + 4 > len(b):
            return None
        n = int.from_bytes(b[pos : pos + 4], "little", signed=True)
        end = pos + 4 + n
        if n < 0 or end + 4 > len(b) or b[end : end + 4] != b[pos : pos + 4]:
            return None
        lens.append((pos + 4, n))
        pos = end + 4
    if not lens or lens[0][1] != 4:
        return None
    rtype = int.from_bytes(b[lens[0][0] : lens[0][0] + 4], "little", signed=True)
    return rtype if RST_RECORDS.get(rtype) == len(lens) else None


def _nc_axis(nc: Path, var: str) -> np.ndarray | None:
    import netCDF4

    with netCDF4.Dataset(nc) as ds:
        if var not in ds.variables:
            return np.array([])
        v = np.ma.filled(np.ma.asarray(ds.variables[var][:], dtype="float64"), np.nan)
    v = v.ravel()
    return v[np.isfinite(v) & (v < NC_FLOAT_FILL)]


def written_until(model_dir: Path, dtmax: float) -> float | None:
    """Seconds since tref up to which the run dir's outputs are complete: the last map
    record, the last VALID zsmax block (when ``dtmax`` > 0) and the last his record,
    whichever is earliest. None when the map is absent, empty or unreadable."""
    ends = []
    for fn, var in (("sfincs_map.nc", "time"), ("sfincs_map.nc", "timemax"),
                    ("sfincs_his.nc", "time")):  # fmt: skip
        p = Path(model_dir) / fn
        if var == "timemax" and dtmax <= 0:
            continue
        if not p.is_file():
            if fn == "sfincs_map.nc":
                return None
            continue  # no obs points / structures -> no his file
        try:
            t = _nc_axis(p, var)
        except (OSError, RuntimeError):
            return None  # a file the solver was writing when it died can be unreadable
        if t is None or len(t) == 0:
            return None
        ends.append(float(t.max()))
    return min(ends) if ends else None


def segments(model_dir: Path) -> list[Path]:
    d = Path(model_dir) / SEG_DIR
    return sorted(p for p in d.iterdir() if p.is_dir()) if d.is_dir() else []


# ── plan / prepare ───────────────────────────────────────────────────────────


@dataclass
class Plan:
    action: str  # "fresh" | "resume" | "finish"
    reason: str
    rst: Path | None = None
    t_resume: datetime | None = None
    #: False = re-run the CURRENT segment from its own restart file: its outputs are
    #: empty or unreadable (preempted before its first record), so nothing is parked
    retire: bool = True


def choose_restart(rsts: list[tuple[datetime, Path]], tstart: datetime, tstop: datetime,
                   tref: datetime, end_s: float, dtmax: float,
                   is_complete=lambda p: rst_type(p) is not None,
                   is_dry=None, lookback_s: float = DRY_LOOKBACK_S):  # fmt: skip
    """The restart file to resume from: strictly inside (tstart, tstop), no later than
    ``end_s`` (s since tref; older-trajectory files beyond it would leave a hole), on
    the dtmaxout lattice from ``tstart``, and complete. Of those, the newest for which
    ``is_dry(t)`` holds, within ``lookback_s`` of the newest; else the newest. None if
    there is none."""
    ok = []
    for t, p in rsts:
        if not (tstart < t < tstop) or (t - tref).total_seconds() > end_s + 1e-6:
            continue
        if dtmax > 0:
            k = (t - tstart).total_seconds() / dtmax
            if abs(k - round(k)) > 1e-6:
                continue
        ok.append((t, p))
    newest = None
    for t, p in reversed(ok):  # completeness is checked lazily: files are ~5 MB each
        if newest is not None and (newest[0] - t).total_seconds() > lookback_s:
            break
        if not is_complete(p):
            continue
        newest = newest or (t, p)
        if is_dry is None or is_dry(t):
            return t, p
    return newest


def rain_free(model_dir: Path, text: str, t: datetime, hours: float = DRY_HOURS) -> bool:
    """True when the run's gridded precipitation (``netamprfile``) is 0 everywhere over
    the ``hours`` before ``t``. SFINCS uses each value as a block over the interval that
    STARTS at its time (``amprblock`` = 1, sfincs_input.f90:549), so those are the values
    labelled [t - hours, t). Runs without the file count as dry."""
    import xarray as xr

    f = inp_get(text, "netamprfile")
    if not f or not (Path(model_dir) / f).is_file():
        return True
    with xr.open_dataset(Path(model_dir) / f) as ds:
        v = ds[next(iter(ds.data_vars))]
        w = v.sel(time=slice(np.datetime64(t) - np.timedelta64(int(hours * 3600), "s"),
                             np.datetime64(t) - np.timedelta64(1, "s")))  # fmt: skip
        return bool(w.size == 0 or float(np.nanmax(w.values)) <= 0.0)


def plan(model_dir: Path) -> Plan:
    model_dir = Path(model_dir)
    inp = model_dir / "sfincs.inp"
    orig = model_dir / ORIG_INP
    text = (orig if orig.is_file() else inp).read_text()
    tref = inp_datetime(text, "tref")
    tstart = inp_datetime(text, "tstart")
    tstop = inp_datetime(text, "tstop")
    dtmax = float(inp_get(text, "dtmaxout") or 0.0)

    end_s = written_until(model_dir, dtmax)
    stop_s = (tstop - tref).total_seconds()
    if end_s is not None and end_s >= stop_s - 1.0:
        return Plan("finish", f"outputs already reach tstop ({end_s / 86400:.2f} d)")
    if end_s is None:
        # A resumed segment killed before its first record: run it again from its own
        # restart file rather than throwing the parked segments away.
        cur = inp.read_text()
        rst = inp_get(cur, "rstfile")
        if orig.is_file() and segments(model_dir) and rst and rst_type(model_dir / rst):
            return Plan("resume", f"current segment re-run from {rst} (its output is empty)",
                        rst=model_dir / rst, t_resume=inp_datetime(cur, "tstart"),
                        retire=False)  # fmt: skip
        if not (model_dir / "sfincs_map.nc").exists():
            return Plan("fresh", "no output yet")
        return Plan("fresh", "no readable output to resume onto")
    rsts = restart_files(model_dir)
    pick = choose_restart(rsts, tstart, tstop, tref, end_s, dtmax,
                          is_dry=lambda t: rain_free(model_dir, text, t))  # fmt: skip
    if pick is None:
        return Plan("fresh", "no usable restart file inside the written window")
    t, p = pick
    newest = choose_restart(rsts, tstart, tstop, tref, end_s, dtmax, lookback_s=0)[0]
    why = "newest complete restart file" if t == newest else (
        f"newest rain-free restart file ({(newest - t).total_seconds() / 86400:.0f} d before the newest)")
    if t == newest and not rain_free(model_dir, text, t):
        why += " (raining before it: the cnb event is split, FINDINGS §18)"
    return Plan("resume", f"{why} {p.name}", rst=p, t_resume=t)


def prepare(model_dir: Path) -> Plan:
    """Retire the current outputs into a segment and rewrite sfincs.inp to resume.

    Only ``action == "resume"`` moves outputs. A ``fresh`` plan restores the original
    inp (a stale resume inp must not run from the wrong start) and discards parked
    segments of the abandoned trajectory."""
    model_dir = Path(model_dir)
    pl = plan(model_dir)
    inp = model_dir / "sfincs.inp"
    orig = model_dir / ORIG_INP
    if pl.action != "resume":
        if pl.action == "fresh":
            if orig.is_file():
                shutil.copy2(orig, inp)
            if (model_dir / SEG_DIR).is_dir():
                shutil.rmtree(model_dir / SEG_DIR)
                _history(model_dir, "fresh start: parked segments discarded")
        return pl

    if not pl.retire:
        for fn in OUTPUTS:
            (model_dir / fn).unlink(missing_ok=True)
        _history(model_dir, f"re-run of the current segment from {pl.rst.name}")
        return pl
    if not orig.is_file():
        shutil.copy2(inp, orig)
    seg_start = inp_datetime(inp.read_text(), "tstart")  # the inp that PRODUCED the outputs
    n = len(segments(model_dir))
    seg = model_dir / SEG_DIR / f"seg{n:02d}_{seg_start:%Y%m%d.%H%M%S}"
    seg.mkdir(parents=True, exist_ok=False)
    for fn in OUTPUTS:
        if (model_dir / fn).is_file():
            shutil.move(str(model_dir / fn), str(seg / fn))
    (seg / "segment_start.txt").write_text(seg_start.strftime(INP_FMT) + "\n")
    inp.write_text(resume_inp(orig.read_text(), pl.rst.name, pl.t_resume))
    _history(model_dir, f"resume from {pl.rst.name}: segment {seg.name} retired")
    return pl


def _history(model_dir: Path, msg: str) -> None:
    with (Path(model_dir) / HISTORY).open("a") as fh:
        fh.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


# ── stitch ───────────────────────────────────────────────────────────────────


def owned_records(times: np.ndarray, start_s: float, next_s: float | None,
                  after_s: float = -np.inf) -> np.ndarray:  # fmt: skip
    """Records of a part starting at ``start_s``: from its start (and after ``after_s``,
    the last record an earlier part supplied) up to and including ``next_s``."""
    m = (times >= start_s - 1e-6) & (times > after_s + 1e-6) & (times < NC_FLOAT_FILL)
    if next_s is not None:
        m &= times <= next_s + 1e-6
    return np.flatnonzero(m)


def owned_blocks(tmax: np.ndarray, start_s: float, next_s: float | None,
                 stop_s: float) -> np.ndarray:  # fmt: skip
    m = (tmax > start_s + 1e-6) & (tmax <= stop_s + 1e-6) & (tmax < NC_FLOAT_FILL)
    if next_s is not None:
        m &= tmax <= next_s + 1e-6
    return np.flatnonzero(m)


def offset_record(times: np.ndarray, at_s: float) -> int | None:
    """Index of the last valid record at or before ``at_s`` (the cumulative value a
    resumed segment must be offset by), or None."""
    ok = np.flatnonzero((times <= at_s + 1e-6) & (times < NC_FLOAT_FILL))
    return int(ok[-1]) if len(ok) else None


def stitch(parts: list[tuple[float, Path]], out: Path, stop_s: float) -> dict:
    """Concatenate one output file across segments.

    ``parts`` are ``(start_seconds, file)`` in time order; the last is the final run's.
    Static variables come from the last file. Written via a temp name, then atomically
    replaced: a half-written stitched map must never look like a run."""
    import netCDF4

    out = Path(out)
    tmp = out.with_name(out.name + ".stitching")
    sel = {"time": [], "timemax": []}
    offs = {"time": [], "timemax": []}  # per part: record of the PREVIOUS part to add
    taken = -np.inf  # last record time supplied so far
    for i, (s0, fn) in enumerate(parts):
        nxt = parts[i + 1][0] if i + 1 < len(parts) else None
        with netCDF4.Dataset(fn) as ds:
            for axis in sel:
                if axis not in ds.variables:
                    continue
                t = np.asarray(np.ma.filled(ds.variables[axis][:], NC_FLOAT_FILL),
                               dtype="float64").ravel()  # fmt: skip
                if axis == "time":
                    ix = owned_records(t, s0, nxt, taken)
                    sel[axis].append((fn, ix))
                    taken = max(taken, float(t[ix].max())) if len(ix) else taken
                else:
                    sel[axis].append((fn, owned_blocks(t, s0, nxt, stop_s)))
                if nxt is not None:
                    offs[axis].append((fn, offset_record(t, nxt)))
    n_m = sum(len(ix) for _, ix in sel["timemax"])

    with netCDF4.Dataset(parts[-1][1]) as src, netCDF4.Dataset(tmp, "w", format="NETCDF4") as dst:
        dst.setncatts({k: src.getncattr(k) for k in src.ncattrs()})
        for name, dim in src.dimensions.items():
            size = None if name == "time" else (n_m if name == "timemax" else len(dim))
            dst.createDimension(name, size)
        for name, v in src.variables.items():
            filt = v.filters() or {}
            kw = dict(zlib=bool(filt.get("zlib")), complevel=int(filt.get("complevel") or 4),
                      shuffle=bool(filt.get("shuffle")))  # fmt: skip
            chunks = v.chunking()
            if isinstance(chunks, list):
                kw["chunksizes"] = [c if d == "time" else min(c, len(dst.dimensions[d]) or 1)
                                    for c, d in zip(chunks, v.dimensions)]  # fmt: skip
            fill = v.getncattr("_FillValue") if "_FillValue" in v.ncattrs() else None
            nv = dst.createVariable(name, v.dtype, v.dimensions, fill_value=fill, **kw)
            nv.setncatts({k: v.getncattr(k) for k in v.ncattrs() if k != "_FillValue"})
            if "time" not in v.dimensions and "timemax" not in v.dimensions:
                nv[...] = v[...]
        for axis in ("time", "timemax"):
            names = [n for n, v in src.variables.items() if axis in v.dimensions]
            if not names or not sel[axis]:
                continue
            cum = {n: None for n in names if n in CUMULATIVE}
            k = 0
            for ipart, (fn, idx) in enumerate(sel[axis]):
                with netCDF4.Dataset(fn) as part:
                    for i in idx:
                        for name in names:
                            pv = part.variables[name]
                            ax = pv.dimensions.index(axis)
                            sl = [slice(None)] * pv.ndim
                            sl[ax] = i
                            data = pv[tuple(sl)]
                            if name in cum and cum[name] is not None:
                                data = data + cum[name]
                            osl = [slice(None)] * pv.ndim
                            osl[ax] = k
                            dst.variables[name][tuple(osl)] = data
                        k += 1
                    # the cumulative total at the next segment's start, for its offset
                    if ipart < len(offs[axis]):
                        j = offs[axis][ipart][1]
                        for name in cum:
                            if j is None:
                                continue
                            pv = part.variables[name]
                            ax = pv.dimensions.index(axis)
                            sl = [slice(None)] * pv.ndim
                            sl[ax] = j
                            val = pv[tuple(sl)]
                            cum[name] = val if cum[name] is None else val + cum[name]
    tmp.replace(out)
    return {"records": sum(len(ix) for _, ix in sel["time"]), "blocks": n_m,
            "parts": len(parts)}  # fmt: skip


def finish(model_dir: Path, keep_final_rst: bool = True) -> dict:
    """After a solve: stitch parked segments (if any), restore sfincs.inp, delete the
    restart files (except the one AT tstop, unless ``keep_final_rst`` is False).

    Does nothing (and says so) when the outputs do not reach ``tstop``: the restart
    files are what a resubmission resumes from."""
    model_dir = Path(model_dir)
    segs = segments(model_dir)
    inp = model_dir / "sfincs.inp"
    orig = model_dir / ORIG_INP
    text = (orig if orig.is_file() else inp).read_text()
    tref = inp_datetime(text, "tref")
    tstop = inp_datetime(text, "tstop")
    stop_s = (tstop - tref).total_seconds()
    dtmax = float(inp_get(text, "dtmaxout") or 0.0)
    end_s = written_until(model_dir, dtmax)
    if end_s is None or end_s < stop_s - 1.0:
        msg = (f"NOT finished: outputs end at {'nothing' if end_s is None else f'{end_s / 86400:.2f} d'}"
               f", tstop is {stop_s / 86400:.2f} d; restart files kept for a resubmission")  # fmt: skip
        _history(model_dir, msg)
        return {"finished": False, "reason": msg}
    report: dict = {"finished": True, "segments": len(segs)}

    if segs:
        starts = [(datetime.strptime((s / "segment_start.txt").read_text().strip(), INP_FMT)
                   - tref).total_seconds() for s in segs]  # fmt: skip
        final_start = (inp_datetime(inp.read_text(), "tstart") - tref).total_seconds()
        for fn in STITCHED:
            marker = model_dir / SEG_DIR / f"{fn}.stitched"
            if marker.is_file():  # an earlier finish died after this file: never twice
                continue
            parts = [(s, seg / fn) for s, seg in zip(starts, segs) if (seg / fn).is_file()]
            if (model_dir / fn).is_file():
                parts.append((final_start, model_dir / fn))
            if len(parts) >= 2:
                report[fn] = stitch(parts, model_dir / fn, stop_s)
            marker.write_text(f"{datetime.now():%Y-%m-%d %H:%M:%S}\n")
        for lg in LOGS:  # segments first, then the final run, in time order
            body = ""
            for seg in segs:
                if (seg / lg).is_file():
                    body += f"===== {seg.name} (preempted segment) =====\n" + (seg / lg).read_text()
            if body:
                final = model_dir / lg
                body += "===== resumed run =====\n" + (final.read_text() if final.is_file() else "")
                final.write_text(body)
        shutil.rmtree(model_dir / SEG_DIR)

    if orig.is_file():
        shutil.copy2(orig, inp)
        orig.unlink()
    removed = 0
    for t, p in restart_files(model_dir):
        if keep_final_rst and t == tstop:
            continue
        p.unlink()
        removed += 1
    report["rst_removed"] = removed
    if segs or removed:
        _history(model_dir, f"finish: {report}")
    return report


__all__ = ["Plan", "choose_restart", "finish", "inp_get", "inp_set", "plan", "prepare",
           "restart_files", "resume_inp", "rst_type", "stitch", "written_until"]  # fmt: skip
