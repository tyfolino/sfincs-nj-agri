# Tide gates on the farm dikes: what public sources say (2026-10-17)

Web search plus the repo's NLD copy. Table: `data/structures/tide_gates_public.csv` (25 rows,
one per structure or named lead). No modelling was done and no model file was changed.

## Short answer

- **No public inventory exists.** None turned up for the meadow-bank gates in these three counties.
  That covers NJDEP, NRCS, USACE and NAACC. Only one of the 18 farm areas has gates with
  coordinates: Gibbstown, from the National Levee Database (NLD).
- **NLD gates.** The repo's NLD copy has 13 pipe gates, but only 6 are in New Jersey, all at
  Gibbstown. The other 7 are at Chester, PA (checked against the repo's
  `nld_pipe_gates` layer).
- **Gates confirmed but not located.** For 2 more farm areas, Silver Lake and Locust Island, a
  federal record confirms tide gates but gives no site. They were built by USDA in 1957-62.
- **Gates named in county records.** For 3 more farm areas, county hazard plans or minutes name a
  gate or sluice nearby: Middle Neck, Mill Creek (Union Bank) and, less surely, Lighthouse.
  Their exact sites are not given.
- **Nothing found.** The other 13 areas turned up nothing gate-specific. Most are private banks in
  Lawrence, Fairfield and Lower Alloways Creek townships.
- **Gates are failing.** Salem County calls four of its sluice-gate structures "critically
  failing". They are in Lower Alloways Creek and Pennsville. The county has asked for $2.7M in
  federal funds; $1.0M is in the House FY27 bill (June 2026). Lower Alloways Creek put its
  sluice-gate project on hold in January 2026 for lack of a grant. This is direct support for
  a "gate fails" scenario.

## By model system

"Verified" means the source document was opened and read. Rows marked "snippet" were seen only
as search-result text.

| system | what public sources say | confidence |
|---|---|---|
| Gibbstown | 3 sluice gates at the Repaupo Creek mouth (Flood Gate Rd), plus 3 flap gates on 48 in pipes at the east end. Outlet inverts about −4.4 ft (datum not given). A Logan Twp report (DVRPC 2004) confirms the Repaupo tidegate; a DVRPC study (2023) mentions a storm-water pumping station. Already in the model, except the pump. | located precisely (gates); pump named only |
| Silver Lake | USDA watershed project (1957-62): 5,100 ft dike, 12 ft top, "elevation 10 ft", with "pipe sluiceways with tide gates" and one water control structure. Run by Thorofare Meadow Co.; gates repaired by 2004. Number and sizes of gates not stated. | named only |
| Locust Island | Same project: 7,300 ft dike, same section, tide gates plus one water control structure. Maintained by Locust Island Meadow Co. and the township. | named only |
| Locust Island / Hancocks Bridge Poplar | "Hancocks Bridge Sluice Gate": the township sought funds in 2024, and the project was on hold in 2026. Site not given. | named only |
| Middle Neck | Elsinboro hazard plan, under Sinnickson Landing Rd (CR 661): "New gates installed 2018". The county lists "sluice gate repairs on Ft Elfsborg Road" in 2018. The road crosses the Middle Neck bank. A NAACC-surveyed crossing sits exactly at model site 2; its record needs a login. | approximate |
| Mill Creek (Union Bank) | Greenwich hazard plan: "In 2014, gates were repaired at County dike parallel to Bridgeton–Greenwich Road". New flood gates are proposed. The model site is on that road. | approximate |
| Lighthouse | "Miles Creek sluice" (Pennsville) is one of the county's failing sluices. The creek is 0.7 km from this bank; the gate site is not given. | named only, system uncertain |
| Lower Alloways Creek | The Ft Elfsborg Rd sluice (above) is 0.4 km from this bank on one road segment. | named only, system uncertain |
| Silver Lake (maybe) | "West Branch sluice gate at Stow Neck Bridge" (county resolution 2025). Stow Neck Rd is 1-2 km from Silver Lake; the nearest NLD bank is the non-farm Long Bridge Road. | named only, system uncertain |
| Jones Island Road (maybe) | Lawrence Twp: "sluice and dikes repaired in 2019" where New Road crosses Fresh Creek. New Road is about 0.7 km from this bank. | approximate, system uncertain |
| Sunset Road | No gate found. The levee failed in Irene (2011) and was repaired by Salem County. A NAACC-surveyed crossing sits at the model site (record needs a login). | none |
| Henby Creek | No gate found. Carneys Point has a "Delaware Ave" sluice (repaired 2022) and a Bouton Creek tide gate and pump; both are probably town drainage, sites unknown. | none |
| Sayres Neck, Sheppard Davis, Back Neck, Sea Breeze Road, Durham, Richard Wood, County Hwy 623, Hancocks Bridge Poplar (except above) | Nothing gate-specific in public sources. | none |

Outside the 18 systems (in the CSV for completeness):
- **Commercial Twp (Port Norris and Bivalve).**
  - Sandy blew out the sluice gate of a dike at Bivalve.
  - The Peak of the Moon dike has one flood structure; two more are proposed (double flap gates).
  - Two other sluice gates were rebuilt or replaced around 2022.
- **Maurice River Cove.** A USDA watershed project from 1960 included tidegates for farm drainage.
- **Supawna Meadows refuge.** A refuge water-control structure on Lighthouse Road: 48 in riser, 30 in outlet.
- **Pennsville.** A stormwater pump station.

## One check the model can use now

The 1957 USDA design put both the Silver Lake and Locust Island dikes at "elevation 10 ft",
with no datum stated. If that is the old sea-level datum (NGVD29), it is about 2.7 m NAVD88;
I did not check the conversion here. The lidar crest in `dikes_built.gpkg` is lower: median
2.48 m at Silver Lake and 1.83 m at Locust Island. That fits settling or wear since 1962, but it
is a reading, not a measurement.

## What is missing

- **For every farm area: gate count, pipe size, invert and flap or sluice type.** The only
  inverts and sizes found are Gibbstown's six NLD gates.
- **Sites for the named gates.** Every county record names a road or creek, never a point.
- **Lawrence and Fairfield townships (Cumberland).** Nothing at all for these private banks:
  Jones Island Rd, Sayres Neck, Sheppard Davis, Back Neck, Durham and Sea Breeze Rd. Their hazard
  plans do not mention gates.

## Best leads for follow-up

1. **Salem County Engineer / Commissioners.** The FY27 joint application with Lower Alloways
   Creek should name and place the four failing sluice structures (West Branch, Miles Creek,
   Alloways Creek, plus one more). The county also repaired the Ft Elfsborg Rd gates (2018) and
   Delaware Ave gates (2022).
2. **NRCS New Jersey (Somerset state office, or the Salem field office).** Ask for the as-built
   plans and O&M records of the Silver Lake–Locust Island watershed project (work plan January
   1957). They should give gate count, pipe size and invert.
3. **NAACC (free account at naacc.org).** Read crossings 14207 (Middle Neck, Tilbury Rd) and
   13738 (Sunset Rd). NJDEP's NAACC layer has 431 surveyed crossings in the domain bounding box,
   but only these two are within 300 m of a farm bank.
4. **Cumberland County Engineering.** Ask about the Mill Creek dike gates repaired in 2014, and
   the Greenwich Township Levees Project designs.
5. **Lower Alloways Creek Township.** Ask about the sluice-gate evaluation (Resolution 2025-45)
   and the Hancocks Bridge sluice.
6. **South Jersey Levee Inventory (NRCS 2010).** Already requested. A 2010 DRBC summary lists its
   field criteria: sod, erosion, settlement, burrows and so on. It does not mention outlets, so
   it may not hold gate data.

## Sources

Opened and read:
- NRCS NJ, "Silver Lake-Locust Island" fact sheet, Oct 2004. The original host
  (corpora.tika.apache.org/base/docs/govdocs1/010/010451.pdf) is down; I read it from the
  govdocs1 mirror, digitalcorpora.s3.amazonaws.com/corpora/files/govdocs1/zipfiles/010.zip,
  member 010/010451.pdf.
- DRBC Comprehensive Plan 1962 (Silver Lake–Locust Island; Maurice River Cove):
  https://www.nj.gov/drbc/library/documents/comprehensive_plan1962.pdf
- DRBC Comprehensive Plan, later status:
  https://www.nj.gov/drbc/library/documents/comprehensive_plan.pdf
- USACE National Levee Database (repo copy `data/structures/structures.gpkg`):
  https://levees.sec.usace.army.mil/
- DVRPC, Environmental Resource Inventory for Logan Township (2004): https://www.dvrpc.org/reports/04018.pdf
- DVRPC TIP D2214, Floodgate Road bridge: https://www.dvrpc.org/tip/nj/map/notmapped/D2214
- Salem County Hazard Mitigation Plan Update 2025 (Jan 2025 appendices).
  Pennsville's appendix was not found online.
  - Salem County: https://www.salemcountysheriff.com/wp-content/uploads/2026/06/01-salem-co-appx-final-2025-0101.pdf
  - Carneys Point: https://www.salemcountysheriff.com/wp-content/uploads/2026/06/03-carneys-point-twp-appx-final-2025-0101.pdf
  - Elsinboro: https://www.salemcountysheriff.com/wp-content/uploads/2026/06/05-elsinboro-twp-appx-final-2025-0101.pdf
  - Lower Alloways Creek: https://www.salemcountysheriff.com/wp-content/uploads/2026/06/06-lower-alloways-creek-twp-appx-final-2025-0101.pdf
  - Mannington: https://www.salemcountysheriff.com/wp-content/uploads/2026/06/07-mannington-twp-appx-final-2025-0101-1.pdf
  - Base plan: https://www.salemcountysheriff.com/wp-content/uploads/2026/06/Base-Plan-final-2025_Optimized.pdf
- Salem County Commissioners agendas and minutes:
  - 2021-08-18: https://www.salemcountynj.gov/wp-content/uploads/2021/08/Agenda-Draft-8-18-21-min.pdf
  - 2025-03-05: https://www.salemcountynj.gov/wp-content/uploads/2025/03/Minutes-3-5-25-CC-Mtg-min.pdf
  - 2025-04-02: https://salemcountynj.gov/wp-content/uploads/2025/04/Minutes-4-2-25-CC-Mtg-Approved-min.pdf
  - 2026-03-04: https://www.salemcountynj.gov/wp-content/uploads/2026/03/Minutes-3-4-26-CC-Mtg-Approved.pdf
- Lower Alloways Creek Twp minutes:
  - 2024-07-16: https://www.lowerallowayscreek-nj.gov/sites/g/files/vyhlif3381/f/minutes/mtg_july16_2024.pdf
  - 2026-01-20: https://www.lowerallowayscreek-nj.gov/sites/g/files/vyhlif3381/f/minutes/jan202026_mtg.pdf
- Rep. Van Drew, community project funding requests:
  - FY26: https://vandrew.house.gov/community-project-funding-requests/community-project-funding-fy26.htm
  - FY27: https://vandrew.house.gov/services/community-project-funding-fy27.htm
  - House Appropriations release (2026-06-08): https://vandrew.house.gov/news/documentsingle.aspx?DocumentID=2052
- Cumberland County Hazard Mitigation Plan Update 2022 appendices:
  - Greenwich: https://www.cumberlandcountynj.gov/filestorage/22641/22643/22652/08-Greenwich-TWP-FINAL-2022-0822_PDF_R2_7.7.23.pdf
  - Lawrence: https://www.cumberlandcountynj.gov/filestorage/22641/22643/22652/10-Lawrence-TWP-FINAL-2022-0822_PDF_R2_7.7.23.pdf
  - Commercial: https://www.cumberlandcountynj.gov/filestorage/22641/22643/22652/04-Commercial-TWP-FINAL-2022-0822_PDF_R2_7.7.23.pdf
  - Fairfield, Downe and Hopewell were also read; no gates found in them.
- Cumberland County Delaware Bayshore Recovery Plan (Dec 2013):
  https://cumberlandcountynj.gov/filestorage/22641/22643/22956/22971/44901/Final_Recovery_Plan_1-14.pdf
- Cumberland County Historical Society, Greenwich timeline: https://cchistsoc.org/?p=1287
- Ducks Unlimited, Supawna Meadows NWR: https://www.ducks.org/conservation/conservation-projects/supawna-meadows-national-wildlife-refuge
- NJDEP NAACC crossings layer: https://mapsdep.nj.gov/arcgis/rest/services/Applications/DEP_CHANJ/MapServer/0
- DRBC Flood Advisory Committee minutes, Aug 2010 (South Jersey Levee Inventory summary):
  https://www.nj.gov/drbc/library/documents/FAC/flood_aug10.pdf
- OpenStreetMap (Overpass and Nominatim), used to place roads and creeks and find one pump station.

Seen only as search snippets (page blocked or not opened):
- NJDEP news release 03_0160 (2003): Repaupo Tide Gate Levee and sluice gates needed repair.
  https://www.nj.gov/dep/newsrel/releases/03_0160.htm
- A Logan Twp fishing-forum post about floodgate funding. Anecdotal, not used.

Checked, nothing useful found:
- NJDEP MS4 culvert and outfall layers: no gate, tide or flap comments in the domain.
- Supawna Meadows EA (2022): breakwater only.
- PSEG Estuary Enhancement Program pages: they say dikes were breached, with no gate detail.
- NPS, *From Marsh to Farm*: history only.
- Hackensack Meadowlands tide-gate report (wrong region).
