"""Creek tides in a calm-window run: the yardstick for the creek fixes (FINDINGS §40).

Two scores, kept apart on purpose:
  TUNING (the fixes may be adjusted to these): observed high and low tides at the three USGS
    creek gauges, Bivalve (Maurice), Greenwich (Cohansey), Hancocks Bridge (Alloway), against
    the model's highest / lowest level within +-3 h (agri_sfincs.waterlevel.match_extremes),
    over the scoring days of the calm window.
  HELD OUT (never tuned to): the published mean tide range at the CO-OPS datum stations up
    the creeks (data/channels/coops_offsets.csv, type R ratios to Reedy Point 8551910,
    Philadelphia 8545240 or Lewes 8557380). Expected range = the station's long-term mean
    range (ratio x the reference's published MN, 1983-2001) x the scoring week's fraction of
    MN, interpolated (inverse distance) between the two nearest observed gauges in WEEK_GAUGES
    (FINDINGS §41: the fraction runs from ~0.74 at Lewes to ~0.95 at Philadelphia in
    2023-05-24..31, so the reference's own week overstated lower-bay targets by 5-8%). Week
    ranges from the observed hourly gauge files (data/gauges/noaa/<id>_hourly_mllw.csv.gz);
    model range = mean high - mean low of the station's observation point, resampled hourly
    like the gauges. A station whose cell bed is above
    OFF_CHANNEL_M sits on the marsh or bank beside the channel (its coordinates are given to
    ~150 m): it is listed but left out of the per-creek medians.
The storm peaks (scripts/validate_storm_gauges.py) and Landsat (validate_storm_landsat.py)
are further held-out checks, run after a fix is chosen.

Runs are named as in config.MODELS/<model>/runs (``<model>/<run>`` or a bare run of v1_100m),
staged on the tidecal2023may event (agri_sfincs.events) with the datum stations as
observation points.
Writes reports/creek_tides.md (every run given, side by side).
Usage:  python scripts/check_creek_tides.py RUN [RUN ...] [--start 2023-05-24] [--stop 2023-06-01]
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
import xarray as xr
from scipy.signal import find_peaks

from agri_sfincs import config, domain, runs, waterlevel
from agri_sfincs.report import md_table

GAUGES = {"01412150": "Bivalve (Maurice)", "01413038": "Greenwich (Cohansey)", "01483050": "Hancocks Bridge (Alloway)"}
OBS_EVENT = "storm2023jun"  # its fetched gauge files cover the calm window
REFS = {"8551910": "Reedy Point", "8545240": "Philadelphia", "8557380": "Lewes"}
#: Published mean range MN = MHW - MLW (m, CO-OPS datums, epoch 1983-2001, fetched 2026-10-20)
#: of the observed gauges whose scoring-week fraction of MN is interpolated to each station.
WEEK_GAUGES = {"8557380": 1.242, "8536110": 1.478, "8537121": 1.698, "8551910": 1.628,
               "8540433": 1.712, "8545240": 1.859}
OFF_CHANNEL_M = -0.3  # cell bed above this: the point is not in a channel cell


def mean_range(s: pd.Series) -> tuple[float, float]:
    """(mean high, mean low) of an hourly series: peaks at least 8 h apart."""
    v = s.dropna()
    hi = v.values[find_peaks(v.values, distance=8)[0]]
    lo = v.values[find_peaks(-v.values, distance=8)[0]]
    return float(hi.mean()), float(lo.mean())


def week_fraction(t0, t1) -> dict[str, tuple[float, float, float]]:
    """{gauge: (lon, lat, observed mean range over t0..t1 / published MN)} for WEEK_GAUGES."""
    ll = {s["id"]: (s["lon"], s["lat"]) for s in domain.NOAA_STATIONS}
    out = {}
    for g, mn in WEEK_GAUGES.items():
        f = config.GAUGE_DIR / "noaa" / f"{g}_hourly_mllw.csv.gz"
        o = pd.read_csv(f, index_col=0, parse_dates=True)["wl_m_mllw"][t0:t1]
        if o.notna().sum() < 24:
            continue
        hi, lo = mean_range(o)
        out[g] = (*ll[g], (hi - lo) / mn)
    return out


def local_fraction(lon: float, lat: float, frac: dict) -> float:
    """Inverse-distance blend of the two nearest gauges' week fractions (degrees scaled by
    cos(lat) for distance; the gauges are within ~1.2 degrees of each other)."""
    c = np.cos(np.radians(lat))
    d = {g: np.hypot((v[0] - lon) * c, v[1] - lat) for g, v in frac.items()}
    a, b = sorted(d, key=d.get)[:2]
    return (frac[a][2] * d[b] + frac[b][2] * d[a]) / (d[a] + d[b])


def creek_of() -> dict[str, str]:
    """CO-OPS station id -> tidal reach (river_table.csv's datum_nodes)."""
    t = pd.read_csv(config.ELEV_DIR / "river_table.csv")
    out = {}
    for r in t[t.kind == "tidal"].itertuples():
        for sid in str(r.datum_nodes).split():
            out[sid] = r.reach
    return out


def score(run, t0, t1) -> tuple[pd.DataFrame, pd.DataFrame]:
    zs = waterlevel.his_series(run)
    with xr.open_dataset(run / "sfincs_his.nc") as h:
        zb = dict(zip([s.strip() for s in h["station_name"].values.astype(str)], h["point_zb"].values))
    g = []
    for site, name in GAUGES.items():
        o = waterlevel.usgs_event_series(OBS_EVENT, site)[t0:t1]
        m = zs[f"usgs_{site}"][t0:t1]
        hi, lo = waterlevel.match_extremes(o, m), waterlevel.match_extremes(o, m, lows=True)
        g.append({"gauge": name, "high bias": hi.diff_m.mean(), "high rmse": float(np.sqrt((hi.diff_m**2).mean())),
                  "low bias": lo.diff_m.mean(), "n": len(hi)})  # fmt: skip
    frac = week_fraction(t0, t1)
    off = pd.read_csv(config.CHANNELS_DIR / "coops_offsets.csv", dtype={"id": str, "ref": str})
    off = off[off.ref.isin(list(REFS))]
    creek = creek_of()
    rows = []
    for r in off.itertuples():
        name = f"coops_{r.id}"
        if name not in zs:
            continue
        s = zs[name][t0:t1].resample("1h").first()
        if s.notna().sum() < 24:
            continue
        hi, lo = mean_range(s)
        exp = (r.h_high + r.h_low) / 2 * WEEK_GAUGES[r.ref] * local_fraction(r.lon, r.lat, frac)
        rows.append({"station": r.name[:40], "id": r.id, "creek": creek.get(r.id, ""), "expected_m": exp,
                     "model_m": hi - lo, "ratio": (hi - lo) / exp, "off_channel": bool(zb[name] > OFF_CHANNEL_M)})  # fmt: skip
    return pd.DataFrame(g).set_index("gauge"), pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--start", default="2023-05-24")
    ap.add_argument("--stop", default="2023-06-01")
    a = ap.parse_args()
    t0, t1 = pd.Timestamp(a.start), pd.Timestamp(a.stop)
    gauges, stations = {}, {}
    for spec in a.runs:
        gauges[spec], stations[spec] = score(runs.resolve(spec), t0, t1)
    g = pd.concat(gauges, names=["run"]).reset_index()
    st = pd.concat(stations, names=["run"]).reset_index(level=0)
    st["creek"] = st.creek.replace("", "(bay shore / other)")
    st.loc[st.off_channel, "station"] += " *"
    wide = st.pivot_table(index=["creek", "station"], columns="run", values="ratio").reindex(columns=a.runs)
    exp = st.groupby(["creek", "station"]).expected_m.first()
    wide.insert(0, "expected range, m", exp)
    by_creek = st[~st.off_channel].groupby(["run", "creek"]).ratio.median().unstack(0).reindex(columns=a.runs)
    md = f"""# Creek tides: tuning gauges and held-out tide stations

Generated by `scripts/check_creek_tides.py` (method in its docstring), {t0:%Y-%m-%d} to
{t1:%Y-%m-%d}. Runs: {', '.join(f'`{r}`' for r in a.runs)}.

## Tuning: USGS creek gauges (model − observed, m)

{md_table(g, floatfmt="{:+.2f}")}

## Held out: CO-OPS tide stations, model range / published range

Median per creek (1.00 = right), stations in channel cells only:

{md_table(by_creek, floatfmt="{:.2f}")}

All stations (* = the point's cell is not a channel cell, left out above):

{md_table(wide, floatfmt="{:.2f}")}
"""
    out = config.REPORTS / "creek_tides.md"
    out.write_text(md)
    print(md_table(g, floatfmt="{:+.2f}"))
    print(md_table(by_creek, floatfmt="{:.2f}"))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
