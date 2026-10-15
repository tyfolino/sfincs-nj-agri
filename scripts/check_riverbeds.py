"""Check the river-bed burn and write reports/riverbeds.md + profile figures.

    python scripts/check_riverbeds.py

Reads what ``build_riverbeds.py`` wrote (data/elevation/riverbed_burn.tif, river_table.csv,
riverbed_profiles.csv; data/channels/gauge_geometry.csv, tidal_datum_nodes.csv,
enc/cells.csv, enc_ring.gpkg) plus the gauge records in data/gauges/ and
data/channels/usgs_*.csv. No network.

Checks:
  * tidal gauges (Bivalve 01412150, Greenwich 01413038, Hancocks Bridge 01483050): the
    merged bed min(bed_merged, burn) within ``R_TIDAL_M`` of the gauge must sit BELOW the
    lowest water level observed in the two v0 event windows (72279, ft -> m; behaves as
    NAVD88 at Bivalve, FINDINGS §9) and below the CO-OPS MLLW used.
  * stream gauges with a gage-height record: gauge datum (monitoring-locations
    ``altitude``, NAVD88) + gage height = water surface. The merged bed within
    ``R_STREAM_M`` must sit below the lowest observed surface; and the gauge's own
    bed estimate (surface at each channel measurement - its mean depth) is compared.

Figures (reports/figs/): riverbed_profile_<river>.png for the Maurice, Cohansey, Salem
and Alloway — the tidal reach and, upstream of the head of tide, the non-tidal level
path that feeds it.
"""

from __future__ import annotations

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
import shapely
from pyproj import Transformer

from agri_sfincs import config, domain
from agri_sfincs.report import md_table

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

CH, ELEV = config.CHANNELS_DIR, config.ELEV_DIR
FIGS = config.REPORTS / "figs"
FT = 0.3048
R_TIDAL_M = 60.0
R_STREAM_M = 30.0
TIDAL_GAUGES = {"01412150": "maurice", "01413038": "cohansey", "01483050": "alloway"}
PLOT_RIVERS = ("maurice", "cohansey", "salem", "alloway")
EVENTS = ("sep2023", "may2025")
# categorical slots 1-3 of the dataviz reference palette (light) + neutral ink
C_BURN, C_V0, C_DATUM, C_SND, INK, MUTED = "#2a78d6", "#8a8984", "#1baf7a", "#eb6834", "#0b0b0b", "#52514e"


def _merged_min_near(burn, bed, lon, lat, r_m) -> tuple[float, float, float]:
    """(min merged bed, min v0 bed, min burn) over pixels within r_m of a point."""
    T = bed.transform
    dlon = r_m / (111_320 * np.cos(np.radians(lat)))
    dlat = r_m / 110_574
    win = rasterio.windows.from_bounds(lon - dlon, lat - dlat, lon + dlon, lat + dlat, T)
    win = win.round_offsets().round_lengths()
    b = bed.read(1, window=win, boundless=True, fill_value=-9999).astype(float)
    u = burn.read(1, window=win, boundless=True, fill_value=-9999).astype(float)
    b[b == -9999], u[u == -9999] = np.nan, np.nan
    wt = rasterio.windows.transform(win, T)
    rr, cc = np.mgrid[0 : b.shape[0], 0 : b.shape[1]]
    x = wt.c + (cc + 0.5) * wt.a
    y = wt.f + (rr + 0.5) * wt.e
    d = np.hypot((x - lon) * 111_320 * np.cos(np.radians(lat)), (y - lat) * 110_574)
    m = d <= r_m
    merged = np.fmin(b, u)
    f = lambda a: float(np.nanmin(a[m])) if np.isfinite(a[m]).any() else np.nan  # noqa: E731
    return f(merged), f(b), f(u)


def _event_series(site: str, pc: str) -> pd.Series:
    parts = []
    for ev in EVENTS:
        p = config.GAUGE_DIR / "usgs_events" / ev / f"{site}_{pc}.csv"
        if p.exists():
            parts.append(pd.read_csv(p, parse_dates=["time"]).set_index("time")["value"])
    return pd.concat(parts) if parts else pd.Series(dtype=float)


def tidal_checks(burn, bed, nodes, table) -> pd.DataFrame:
    sites = pd.read_csv(config.GAUGE_DIR / "usgs_series.csv", dtype={"site": str}).drop_duplicates("site").set_index("site")
    ng = gpd.GeoDataFrame(nodes, geometry=gpd.points_from_xy(nodes.lon, nodes.lat), crs=4326).to_crs(domain.EPSG)
    rows = []
    for s, reach in TIDAL_GAUGES.items():
        lon, lat = sites.loc[s, "lon"], sites.loc[s, "lat"]
        obs = _event_series(s, "72279") * FT
        p = gpd.GeoSeries([shapely.Point(lon, lat)], crs=4326).to_crs(domain.EPSG).iloc[0]
        k = ng.distance(p).idxmin()
        merged, v0, bu = _merged_min_near(burn, bed, lon, lat, R_TIDAL_M)
        lowest = float(obs.min()) if len(obs) else np.nan
        rows.append({"site": s, "name": sites.loc[s, "name"], "reach": reach,
                     "obs_min_m": lowest, "obs_p5_m": float(obs.quantile(0.05)) if len(obs) else np.nan,
                     "coops_mllw_m": float(ng.loc[k, "mllw_navd88_m"]),
                     "coops_node": f"{ng.loc[k, 'id']} ({ng.distance(p).min() / 1e3:.1f} km)",
                     "v0_bed_m": v0, "burn_m": bu, "merged_bed_m": merged,
                     "below_obs_min": bool(merged < lowest) if np.isfinite(lowest) else None})  # fmt: skip
    return pd.DataFrame(rows)


def stream_checks(burn, bed, gg, prof) -> pd.DataFrame:
    sites = pd.read_csv(CH / "usgs_sites.csv", dtype={"site": str}).set_index("site")
    series = pd.read_csv(config.GAUGE_DIR / "usgs_series.csv", dtype={"site": str})
    gh_sites = sorted(set(series.loc[series["what"] == "gage height", "site"]))
    fm = pd.read_csv(CH / "usgs_gage_heights.csv", dtype={"site": str}, low_memory=False)
    cm = pd.read_csv(CH / "usgs_channel_measurements.csv", dtype={"site": str}, low_memory=False)
    rows = []
    for s in gh_sites:
        if s not in sites.index:
            continue
        st = sites.loc[s]
        datum = st["altitude_ft"] * FT if st["altitude_datum"] == "NAVD88" else np.nan
        ev = _event_series(s, "00065")
        # surface at each discharge measurement (same field visit) - its mean depth
        f = fm[(fm["site"] == s) & (fm["unit_of_measure"] == "ft")][["field_visit_id", "value", "time"]]
        c = cm[cm["site"] == s][["field_visit_id", "channel_area", "channel_width", "channel_flow"]]
        j = f.merge(c, on="field_visit_id").dropna()
        j = j[(j["channel_width"] > 0) & (j["channel_area"] > 0)]
        j = j[j["time"] >= "2007"]  # gage heights since the 2007 records; older datums differ
        gauge_bed = (datum + j["value"] * FT - j["channel_area"] / j["channel_width"] * FT) if len(j) else pd.Series(dtype=float)
        merged, v0, bu = _merged_min_near(burn, bed, st["lon"], st["lat"], R_STREAM_M)
        wse_min = datum + ev.min() * FT if len(ev) else np.nan
        g = gg[gg["site"] == s]
        # the non-tidal profile station nearest the gauge (the burn pixels can sit > 30 m
        # from a gauge whose coordinates are off the NHD line)
        x, y = Transformer.from_crs(4326, domain.EPSG, always_xy=True).transform(st["lon"], st["lat"])
        nt = prof[prof["kind"] == "non-tidal"]
        d2 = (nt["x"] - x) ** 2 + (nt["y"] - y) ** 2
        k = d2.idxmin()
        near = np.sqrt(d2[k]) <= 100.0
        wse_meas = datum + j["value"] * FT if len(j) else pd.Series(dtype=float)
        rows.append({"site": s, "name": st["name"], "da_km2": st["drainage_area_mi2"] * 2.59,
                     "datum_navd88_m": datum,
                     "obs_wse_min_m": wse_min,
                     "gauge_bed_p50_m": float(gauge_bed.median()) if len(gauge_bed) else np.nan,
                     "n_paired": int(len(j)),
                     "mean_depth_m": float(g["depth_m"].iloc[0]) if len(g) else np.nan,
                     "wse_meas_p50_m": float(wse_meas.median()) if len(wse_meas) else np.nan,
                     "profile_surface_m": float(nt.loc[k, "surface_m"]) if near else np.nan,
                     "profile_bed_m": float(nt.loc[k, "bed_profile_m"]) if near else np.nan,
                     "v0_bed_m": v0, "burn_m": bu, "merged_bed_m": merged,
                     "below_obs_min": bool(min(merged, nt.loc[k, "bed_profile_m"] if near else np.inf) < wse_min)
                     if np.isfinite(wse_min) else None})  # fmt: skip
    out = pd.DataFrame(rows)
    out["surface_minus_wse_p50_m"] = out["profile_surface_m"] - out["wse_meas_p50_m"]
    out["profile_minus_gauge_bed_m"] = out["profile_bed_m"] - out["gauge_bed_p50_m"]
    return out


US_FT = 1200 / 3937


def ehydro_check(sid: str, line, t: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """An eHydro survey on a reach, read independently of the build: points within
    100 m of the centreline (the multibeam *_FULL.XYZ where present), ft below MLLW
    1983-2001, NJ State Plane ft (EPSG 3424), put on NAVD88 with the SAME MLLW line as the
    burn. Returns (running-median profile, burn - survey by source code)."""
    from agri_sfincs import riverbed

    d = CH / "ehydro" / sid
    files = {f.name.upper(): f for f in d.iterdir()}
    f = files.get(f"{sid}_FULL.XYZ") or files[f"{sid}.XYZ"]
    xyz = pd.read_csv(f, sep=r"\s+", header=None, usecols=[0, 1, 2]).to_numpy(dtype=float)
    x, y = Transformer.from_crs(3424, domain.EPSG, always_xy=True).transform(xyz[:, 0], xyz[:, 1])
    pts = shapely.points(x, y)
    m = shapely.distance(line, pts) <= 100.0
    s = shapely.line_locate_point(line, pts[m])
    z = np.interp(s, t["station_m"], t["mllw_navd88_m"]) - xyz[m, 2] * US_FT
    g = t["station_m"].values
    med = riverbed.running_median(s, z, g, 150.0, 3)
    p = pd.DataFrame({"s": g, "z": med})
    dd = pd.DataFrame({"src": t["src"].values, "diff": t["bed_profile_m"].values - med}).dropna()
    cmp_ = dd.groupby("src")["diff"].agg(["count", "median", lambda v: np.percentile(v, 10),
                                          lambda v: np.percentile(v, 90)])  # fmt: skip
    cmp_.columns = ["stations", "burn_minus_survey_p50_m", "p10_m", "p90_m"]
    cmp_["km"] = cmp_["stations"] * 0.025
    return p, cmp_


def profile_figure(river: str, prof: pd.DataFrame, table: pd.DataFrame, tchk: pd.DataFrame, enc_pts,
                   eh=None) -> str:
    t = prof[prof["reach"] == river].sort_values("station_m")
    row = table[table["reach"] == river].iloc[0]
    up = prof[prof["reach"] == f"lp{int(row['levelpathi'])}"].sort_values("station_m") if pd.notna(row.get("levelpathi")) else prof.iloc[0:0]
    fig, ax = plt.subplots(figsize=(11, 4.6), dpi=130)
    xt = t["station_m"] / 1e3
    ax.plot(xt, t["bed_merged_cl_m"], color=C_V0, lw=1, label="v0 bed (bed_merged) on the centreline")
    ax.plot(xt, t["mllw_navd88_m"], color=C_DATUM, lw=1.5, ls="--", label="MLLW (CO-OPS)")
    ax.plot(xt, t["bed_profile_m"], color=C_BURN, lw=2, label="burned bed profile")
    if eh is not None and len(eh):
        ax.plot(eh["s"] / 1e3, eh["z"], color=INK, lw=0.9, ls=":", zorder=2,
                label=f"USACE eHydro {row['ehydro_survey']}, running median")  # fmt: skip
    if len(enc_pts):
        ax.scatter(enc_pts["s"] / 1e3, enc_pts["z"], s=10, color=C_SND, zorder=3, label="ENC soundings used (NAVD88)")
    if len(up):
        L = up["station_m"].max()
        xu = (up["station_m"] - L) / 1e3
        ax.plot(xu, up["surface_m"], color=C_DATUM, lw=1.2, label="non-tidal: lidar surface (monotone)")
        ax.plot(xu, up["bed_profile_m"], color=C_BURN, lw=2)
        ax.plot(xu, up["surface_raw_m"], color=C_V0, lw=0.6, alpha=0.7)
        ax.axvline(0, color=MUTED, lw=0.8)
        ax.annotate("head of tide", (0, ax.get_ylim()[1]), xytext=(3, -12), textcoords="offset points",
                    fontsize=8, color=MUTED)  # fmt: skip
    for r in tchk[tchk["reach"] == river].itertuples():
        s = r.station_km
        ax.scatter([s], [r.obs_min_m], marker="v", s=40, color=INK, zorder=4)
        ax.annotate(f"{r.name.split(' at ')[-1].replace(' NJ', '')}: lowest observed {r.obs_min_m:+.2f}",
                    (s, r.obs_min_m), xytext=(5, 6), textcoords="offset points", fontsize=8, color=INK)  # fmt: skip
    ax.set_xlabel("km downstream of the head of tide (negative = non-tidal, upstream)")
    ax.set_ylabel("m NAVD88")
    ax.set_title(f"{row['river']}: burned bed profile", loc="left", fontsize=11)
    ax.grid(True, color="#e6e5e0", lw=0.6)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(fontsize=8, frameon=False, loc="lower left", ncol=2)
    FIGS.mkdir(parents=True, exist_ok=True)
    out = FIGS / f"riverbed_profile_{river}.png"
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out.relative_to(config.REPORTS).as_posix()


def main() -> None:
    table = pd.read_csv(ELEV / "river_table.csv")
    prof = pd.read_csv(ELEV / "riverbed_profiles.csv", low_memory=False)
    gg = pd.read_csv(CH / "gauge_geometry.csv", dtype={"site": str})
    nodes = pd.read_csv(CH / "tidal_datum_nodes.csv", dtype={"id": str})
    cells = pd.read_csv(CH / "enc" / "cells.csv")
    snd = gpd.read_file(CH / "enc_ring.gpkg", layer="SOUNDG")
    lines = gpd.read_file(ELEV / "riverbed_centrelines.gpkg").set_index("reach")

    burn = rasterio.open(ELEV / "riverbed_burn.tif")
    bed = rasterio.open(ELEV / "bed_merged.tif")
    src = rasterio.open(ELEV / "riverbed_source.tif")

    tchk = tidal_checks(burn, bed, nodes, table)
    # station of each tidal gauge on its reach, for the figure
    sites = pd.read_csv(config.GAUGE_DIR / "usgs_series.csv", dtype={"site": str}).drop_duplicates("site").set_index("site")
    st_km = []
    for r in tchk.itertuples():
        p = gpd.GeoSeries([shapely.Point(sites.loc[r.site, "lon"], sites.loc[r.site, "lat"])], crs=4326).to_crs(domain.EPSG).iloc[0]
        st_km.append(lines.loc[r.reach, "geometry"].project(p) / 1e3)
    tchk["station_km"] = st_km
    schk = stream_checks(burn, bed, gg, prof)

    # ENC inventory per cell in the ring
    snd_ring = snd.groupby("cell").size().rename("soundings_in_ring")
    inv = cells.set_index("cell")[["scale", "title", "issued"]].join(snd_ring).fillna({"soundings_in_ring": 0})
    inv["soundings_in_ring"] = inv["soundings_in_ring"].astype(int)
    inv = inv[inv["soundings_in_ring"] > 0].sort_values(["scale", "soundings_in_ring"], ascending=[True, False])

    figs, eh_cmp = [], []
    used = pd.read_csv(ELEV / "riverbed_soundings.csv")
    for river in PLOT_RIVERS:
        line = lines.loc[river, "geometry"]
        t = prof[prof["reach"] == river].sort_values("station_m")
        u = used[used["reach"] == river]
        code_at = np.interp(u["station_m"], t["station_m"], t["src"])
        u = u[np.isclose(code_at, 1)]  # plot only the soundings that are the source
        s_, z_ = u["station_m"].values, u["z_navd88_m"].values
        eh = None
        sid = table.set_index("reach").loc[river].get("ehydro_survey")
        if isinstance(sid, str) and sid:
            eh, c = ehydro_check(sid, line, t)
            eh_cmp.append(c.reset_index().assign(reach=river, survey=sid))
        figs.append((river, profile_figure(river, prof, table, tchk, pd.DataFrame({"s": s_, "z": z_}), eh)))

    # burned area per source code
    a = src.read(1)
    T = src.transform
    px = abs(T.a * T.e) * (111_320 * np.cos(np.radians(39.45))) * 110_574
    names = {int(k.split("_")[1]): v for k, v in src.tags().items() if k.startswith("src_")}
    area = pd.DataFrame({"code": list(names), "source": list(names.values())})
    area["km2"] = [float((a == c).sum() * px / 1e6) for c in area["code"]]
    del a

    tid = table[table["kind"] == "tidal"]
    nt = table[table["kind"] == "non-tidal"]
    eh_cmp = (pd.concat(eh_cmp, ignore_index=True).set_index(["reach", "survey", "src"])
              if eh_cmp else pd.DataFrame())  # fmt: skip
    cov = pd.read_csv(CH / "ehydro" / "coverage.csv")
    anchors = pd.read_csv(CH / "gauge_anchors.csv", dtype={"site": str})
    md = ["# River-bed burn (FINDINGS §11)", "",
          "Generated by `scripts/check_riverbeds.py` from `scripts/build_riverbeds.py` outputs. "
          "The burn is `data/elevation/riverbed_burn.tif` (m NAVD88, the bed grid) + "
          "`riverbed_source.tif`; merge as `min(bed_merged, burn)` (it is already never-raise).", "",
          "## Burned area by source", "", md_table(area.set_index("code"), "{:,.2f}"), "",
          "## NOAA ENC cells with soundings in the ring", "",
          "All cells are on MLLW (S-57 SDAT 12), depths in metres (DUNI 1).", "",
          md_table(inv, "{:,.0f}"), "",
          "## Tidal reaches", "",
          md_table(tid[["reach", "river", "length_km", "ehydro_survey", "km_ehydro", "n_soundings",
                        "soundings_to_km", "km_soundings",
                        "km_chart_area", "km_uncharted", "mllw_navd88_m", "bed_p50_m", "bed_min_m",
                        "bed_max_m", "channel_area_km2"]].set_index("reach"), "{:,.2f}"), "",
          "`soundings_to_km` = distance below the head of tide of the most upstream sounding. "
          "CO-OPS nodes behind each reach's MLLW line: "
          + "; ".join(f"{r.reach} {r.datum_nodes}" for r in tid.itertuples()) + " (all in "
          "`data/channels/tidal_datum_nodes.csv`).", "",
          "## USACE eHydro surveys (user, 2026-10-05: they replace the chart where they reach)", "",
          "Every survey of the two federal channels, its coverage of the reach (km of 25 m "
          "stations with >= 3 survey points within +-150 m) and the pick: the most recent "
          "survey covering >= 90% of the best one. All are ft below MLLW (1983-2001 epoch), "
          "US survey ft, NJ State Plane (checked in each survey's metadata); MLLW -> NAVD88 "
          "with the same CO-OPS line as the chart. The newest Maurice surveys (2024-2026) "
          "cover only the entrance channel (<= 5 km), so the full 2023 condition survey to "
          "Millville is used.", "",
          md_table(cov.set_index(["reach", "id"]), "{:,.2f}"), "",
          "Burned profile minus the picked survey's running median (read independently: "
          "points within 100 m of the centreline, +-150 m, >= 3 points), by burn source. The "
          "surveys cover the federal channel (Maurice 150 ft, Salem dredged channel), so where "
          "they are the source the whole NHD river polygon is painted with the channel's bed "
          "(conveyance on the high side).", "",
          md_table(eh_cmp, "{:,.2f}") if len(eh_cmp) else "(no survey)", "",
          "## Gauge anchors (non-tidal; user, 2026-10-05: Pitman and Swedesboro only)", "",
          "Bed = gauge datum (NAVD88, checked) + median gage height at the discharge "
          "measurements in the p25-p75 flow band since 2007 - mean depth; the correction "
          "tapers to 0 over +-1.5 km (src 7).", "",
          md_table(anchors.drop(columns=["x", "y", "levelpathi"]).set_index("site"), "{:,.2f}"), "",
          "## Tidal gauge check (bed must sit below the lowest observed water)", "",
          md_table(tchk.drop(columns=["station_km"]).set_index("site"), "{:,.2f}"), "",
          "## Stream gauge check", "",
          "Water surface = gauge datum (NAVD88) + gage height. `gauge_bed_p50` = surface at each "
          "discharge measurement since 2007 minus its mean depth (area / width); `wse_meas_p50` = "
          "median surface at those measurements. `profile_*` = the non-tidal profile station "
          "nearest the gauge (<= 100 m). `burn_m` / `merged_bed_m` = lowest pixel within 30 m. "
          "`below_obs_min`: the lower of the profile bed and the merged pixel is below the lowest "
          "surface seen in the two event windows.", "",
          md_table(schk.set_index("site"), "{:,.2f}"), "",
          "## Gauge hydraulic geometry (USGS channel measurements, p25-p75 measured-flow band)", "",
          md_table(gg[["site", "name", "da_km2", "n", "n_band", "q_lo_cms", "q_hi_cms", "depth_m",
                       "depth_p10_m", "depth_p90_m", "width_m", "first", "last", "on_path"]].set_index("site"),
                   "{:,.2f}"), "",
          "## Non-tidal level paths", "",
          f"{len(nt)} paths, {nt['length_km'].sum():,.0f} km, of which {nt['km_in_lakes'].sum():,.0f} km "
          f"in lakes (not painted); {int((nt['src'] == 4).sum())} anchored to a gauge on the path.", "",
          md_table(nt.sort_values("da_km2_max", ascending=False).head(30)[
              ["reach", "river", "length_km", "da_km2_min", "da_km2_max", "gauges", "depth_m", "width_m",
               "km_in_lakes", "km_low_surface_unburned", "anchored", "surface_drop_m", "bed_p50_m"]].set_index("reach"), "{:,.2f}"), "",
          "(30 largest by drainage area; all rows in `data/elevation/river_table.csv`.)", "",
          "## Caveats", "",
          "- ENC soundings stop near every creek mouth: inside the Cohansey there are none, the "
          "Maurice has them only below ~13.6 km from Millville (now replaced by the 2023 survey), "
          "and Stow / Oldmans have none at all. Most other tidal length is the chart's "
          "\"0-1.8 m\" depth area or uncharted: 1.2 m below MLLW for both (user, 2026-10-05).",
          "- MLLW in NAVD88 comes from CO-OPS: datum sheets with a NAVD88 tie, and subordinate "
          "tide-prediction stations whose MTL is borrowed from the nearest tied station (no "
          "geodetic tie exists for them; +-~0.1 m). VDatum's API returns 412 / -999999 on "
          "these creeks.",
          "- Non-tidal beds sit on the lidar flight-day water surface; at gauges with a NAVD88 "
          "datum that surface is -0.1 to +0.15 m from the median measured stage, except Pitman "
          "and Swedesboro (+0.4 m), which are now anchored to the gauge (above).",
          "- Salem River at Woodstown 01482500: gauge datum + gage height = ~12.0 m, but the lidar "
          "lake surface above the dam is 8.7 m and the tailwater 6.3 m: the published datum "
          "(28.32 ft NAVD88) does not match; that gauge cannot check absolute levels. Manumuskin "
          "01412080 is the opposite: lidar 1.0 m BELOW the measured stage.",
          f"- {nt['km_low_surface_unburned'].sum():.0f} km of 'non-tidal' profile (above an NJDEP "
          "head-of-tide point) has a lidar surface below 1 m NAVD88 (most on the Salem River "
          "level path and Still Run): tidal elevations, likely diked / tide-gated meadow. It is "
          "LEFT UNBURNED (user, 2026-10-05; handled with the drainage structures).",
          "- NHDPlus HR lakes / reservoirs >= 1 ha are not painted (Union Lake etc. keep the "
          "fake flat bed; that is a separate fix).", "",
          "## Profiles", ""]  # fmt: skip
    md += [f"![{r}]({p})" for r, p in figs]
    out = config.REPORTS / "riverbeds.md"
    out.write_text("\n".join(md) + "\n")
    print(tchk.to_string())
    print(schk.to_string())
    print(area.to_string())
    print(f"wrote {out} and {len(figs)} figures")


if __name__ == "__main__":
    main()
