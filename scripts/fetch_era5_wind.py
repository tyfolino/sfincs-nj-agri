"""ERA5 hourly 10 m wind over the bay and both shores: one NetCDF per year.

Dataset: reanalysis-era5-single-levels (Copernicus C3S, doi 10.24381/cds.adbb2d47;
Copernicus licence, attribution required), via ``cdsapi`` and ~/.cdsapirc. Request shape
copied from nj_bight_sfincs scripts/download_era5_cds.py (2026-10-27), without pressure:
the boundary is observed water level, so the inverse-barometer effect is already in it.

Box (N, W, S, E): ``BOX``, the NJ and DE grids (C&D Canal to Lewes, Philadelphia to Cape
May) plus a cell either side, 0.25 deg native grid.

Writes config.WIND_DIR/era5/era5_wind_<year>.nc: ``u10``, ``v10`` (m/s, the vector the air
moves TOWARD) on ``time`` (UTC) x ``latitude`` x ``longitude``, as served. Existing years
are skipped. config.WIND_DIR is a symlink into DATA_BULK (rebuild: rerun this).

Usage:  python scripts/fetch_era5_wind.py --years 2011 2018 2020 2022-2025
"""

from __future__ import annotations

import argparse

from agri_sfincs import config

#: [North, West, South, East], degrees.
BOX = [40.25, -76.0, 38.5, -74.5]


def years_arg(v: list[str]) -> list[int]:
    out = []
    for s in v:
        a, _, b = s.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return sorted(set(out))


def main() -> None:
    import cdsapi
    import xarray as xr

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--years", nargs="+", required=True, help="years or ranges, e.g. 2011 2022-2025")
    a = ap.parse_args()
    out_dir = config.WIND_DIR / "era5"
    out_dir.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client()
    for y in years_arg(a.years):
        out = out_dir / f"era5_wind_{y}.nc"
        if out.exists():
            print(f"{out.name}: exists")
            continue
        raw = out.with_suffix(".raw.nc")
        client.retrieve("reanalysis-era5-single-levels", {
            "product_type": ["reanalysis"],
            "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind"],
            "year": [str(y)], "month": [f"{m:02d}" for m in range(1, 13)],
            "day": [f"{d:02d}" for d in range(1, 32)], "time": [f"{h:02d}:00" for h in range(24)],
            "data_format": "netcdf", "download_format": "unarchived", "area": BOX,
        }, str(raw))  # fmt: skip
        with xr.open_dataset(raw) as ds:
            ds = ds.rename({"valid_time": "time"}) if "valid_time" in ds.coords else ds
            ds = ds.drop_vars([v for v in ("number", "expver") if v in ds.variables]).load()
        ds.attrs.update(source="ERA5 hourly single levels, doi 10.24381/cds.adbb2d47", box_NWSE=str(BOX))
        ds.to_netcdf(out)
        raw.unlink()
        print(f"{out.name}: {ds.sizes['time']} hours, {ds.sizes['latitude']} x {ds.sizes['longitude']} cells")


if __name__ == "__main__":
    main()
