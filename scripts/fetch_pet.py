"""gridMET daily grass reference evapotranspiration (``pet``) over the study box.

Source (probed 2026-10-05): gridMET (Abatzoglou 2013, doi:10.1002/joc.3413), the
aggregated THREDDS OPeNDAP dataset, anonymous, subset server side:
  http://thredds.northwestknowledge.net:8080/thredds/dodsC/
      agg_met_pet_1979_CurrentYear_CONUS.nc
  variable ``daily_mean_reference_evapotranspiration_grass`` (mm/day, uint16 x 0.1):
  ASCE standardized Penman-Monteith grass reference ET (ETo), 1/24 deg (~4 km) grid,
  1979-01-01 -> ~3 days ago. Its note5: "Days correspond approximately to calendar
  days ending at midnight, Mountain Standard Time (7 UTC the next calendar day)", so
  day D covers D 07Z .. D+1 07Z, which holds the whole NJ daylight period.
  Recent days are "provisional"/"early" (notes 3-4) and may change.

Clip: domain.RAIN_BBOX (lon -75.64..-74.80, lat 38.98..39.94): the 20 x 23 cells whose
centres lie inside it. ~3 s per year from Amarel.

Writes data/evap/gridmet_pet_<y0>_<y1>.nc (config.EVAP_DIR):
  pet(time, lat, lon)  float32 mm/day, grass reference ET for the gridMET day starting
                       at ``time`` (the date; see the 07Z note above). Raw ETo: the
                       open-water factor is applied in agri_sfincs/evap.py, not here.

Usage:  python scripts/fetch_pet.py [--years 2002-2025]
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import xarray as xr

from agri_sfincs import config, domain

URL = (
    "http://thredds.northwestknowledge.net:8080/thredds/dodsC/"
    "agg_met_pet_1979_CurrentYear_CONUS.nc"
)
VAR = "daily_mean_reference_evapotranspiration_grass"


def fetch_year(ds: xr.Dataset, year: int) -> xr.DataArray:
    w, s, e, n = domain.RAIN_BBOX
    da = ds[VAR].sel(
        lon=slice(w, e), lat=slice(n, s), day=slice(f"{year}-01-01", f"{year}-12-31")
    )
    for attempt in range(4):
        try:
            return da.load()
        except Exception as exc:  # transient OPeNDAP failures
            if attempt == 3:
                raise
            print(f"  {year}: {exc!r}; retrying", flush=True)
            time.sleep(10 * (attempt + 1))
    raise AssertionError


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--years", default="2002-2025")
    args = ap.parse_args()
    y0, y1 = (int(v) for v in args.years.split("-"))
    out = config.EVAP_DIR / f"gridmet_pet_{y0}_{y1}.nc"
    out.parent.mkdir(parents=True, exist_ok=True)

    ds = xr.open_dataset(URL)
    parts = []
    for year in range(y0, y1 + 1):
        t = time.time()
        da = fetch_year(ds, year)
        n_days = da.sizes["day"]
        print(f"{year}: {n_days} days, mean {float(da.mean()):.2f} mm/d, "
              f"NaN {int(da.isnull().sum())} ({time.time() - t:.1f} s)", flush=True)  # fmt: skip
        parts.append(da)
    pet = xr.concat(parts, "day").rename(day="time").astype(np.float32)
    pet = pet.sortby("lat")  # ascending lat
    pet.name = "pet"
    pet.attrs = {
        "units": "mm/day",
        "long_name": "gridMET daily grass reference evapotranspiration (ASCE PM ETo)",
        "day_definition": "gridMET day: approx. D 07Z .. D+1 07Z (midnight MST)",
        "source": URL + f" :: {VAR}",
        "citation": "Abatzoglou, J.T., 2013, Int. J. Climatol., doi:10.1002/joc.3413",
    }
    dsout = pet.to_dataset()
    dsout.attrs["bbox_w_s_e_n"] = list(domain.RAIN_BBOX)
    enc = {"pet": {"zlib": True, "complevel": 4}}
    dsout.drop_vars([c for c in dsout.coords if c not in ("time", "lat", "lon")]).to_netcdf(
        out, encoding=enc
    )
    print(f"wrote {out}  {dict(pet.sizes)}")


if __name__ == "__main__":
    main()
