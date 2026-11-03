# What it costs to fix a farm dike or tide gate: public figures (2026-11-03)

This report comes from a web search plus the repo's copy of the National Levee Database (NLD).
No model was run and no model file was changed. Every figure below gives its source. "Opened"
means the document itself was read. "Snippet" means the figure was seen only in search-result
text. Dollar amounts are in the dollars of the year shown, not adjusted, unless a line says
otherwise.

## Summary

- **Only 5 of the 18 farm areas have any public cost figure.** They are Middle Neck, Gibbstown,
  Mill Creek (Union Bank), Silver Lake and Locust Island. Most of these figures are for gates,
  not for the bank itself. The other 13 have none.
- **Best figure tied to one area:** Middle Neck's four sluice gates (48-inch pipes, under
  Sinnickson's Landing Road). Salem County authorised **$630,100** for emergency repairs in
  2018-19, which is about $158,000 per gate.
- **Gates are the expensive part.** A full rebuild of one sluice costs about **$0.7-1.8 M**:
  Salem County's request for four structures, its 2026 West Branch contract, and the Army Corps
  national range all fall there. The figures for whole projects (bank plus gates) run to
  millions.
- **Best cost per length of bank:** the Army Corps national range for an earthen levee 5 ft
  high is **$34-520 per foot**, whole project, in March 2023 prices. It is a guide, not a
  measurement: it comes from river levees, not marsh banks. The few local checks sit near the
  top of that range or above it: a 2024 dike raise in Salem County at about $620/ft, and
  2013 Cumberland estimates of about $630-1,250/ft. A breach repair costs more per foot:
  Matt's Landing (2013) cost about $1,900/ft.
- **The 2010 "South Jersey Levee Inventory" has been found** (Wayback Machine copy). It gives
  lengths for most of the 18 areas, but it has only three cost figures.

## How to read the tables

- **Kind:** *actual* = money spent or authorised under a contract; *award* = a contract award;
  *estimate* = an engineer's or planner's figure; *request* = money asked for, not yet given.
- **Bank lengths:** "NLD km" is from the repo's NLD copy (`data/structures/structures.gpkg`,
  layer `nld_alignment`). "Inventory ft" is from the 2010 inventory, Table 7. They differ
  because they were measured differently.
- **Inflation (rough):** CPI-U 2024 ÷ year. Multiply by about 24 for 1933, 13 for 1950,
  12 for 1955, 11 for 1957, 1.35 for 2013 and 1.25 for 2018.

## Table A. Costs matched to the 18 NLD farm areas

Where each area is (township and sponsor) comes from the NLD copy. The 2010 inventory uses
the same levee names.

| System (township; NLD km / inventory ft) | Work | Quantity | Year ($ year) | Amount | Kind | Match | Source |
|---|---|---|---|---|---|---|---|
| **Middle Neck** (Elsinboro; 3.17 km / 3,810 ft) | Emergency repair of 4 sluice gates: cofferdam, sheet piles, plugs, pumps, "duckbill" valves on pipes 1-2, aluminium tide gates on pipes 3-4, pipe lining | 4 gates, 48-in pipes | 2018-19 | **$630,100** in total ($250,000 + $250,000 + $86,000 change order 1 + $44,100 change order 2) | actual (not-to-exceed authorisations) | strong: inventory calls it "Middle Neck/Sinnickson Landing Levee"; the county keeps the dike as a county road | [S3] Res. 2018-286, 2018-287, 2018-342, 2018-360, 2019-282 |
| Middle Neck | Tidegate structure built by the federal PL-566 program | 1 structure | 1965 | not given | — | strong | [S1] Table 24 |
| **Gibbstown** (Greenwich and Logan, Gloucester; 7.85 km / 22,656 ft) | Rebuild the Repaupo tide gate, then re-armour and rebuild 3,400 ft of levee next to it to the 100-year storm | gate + 3,400 ft | listed 2013 | **$12.5 M** for both phases. If all of it were levee, about $3,700/ft; the gate's share is not given | actual (financing listed by the county improvement authority) | strong | [S6] GCIA |
| Gibbstown | Replace the Repaupo Creek tidegate system | gate system | about 2004-10 | **$2.5 M** in state bond money (2003 Bond Act) | actual (grant) | strong; probably part of the $12.5 M | [S1] p.130 |
| Gibbstown | Repair of the flood gates | not given | 2020 | **$405,000** | estimate | strong: Greenwich Twp, Gloucester (minutes mention the GCIA and Delaware River Partners) | [S7] |
| Gibbstown | Corps emergency repair of the Repaupo tidegate | — | 1999 | not given | — | strong | [S1] p.130 |
| **Mill Creek (Union Bank)** (Greenwich and Hopewell, Cumberland; 1.51 km / 4,552 ft) | Replace two tidegate structures, plus levee repair and stabilisation | 2 gates + levee | about 2009 | **> $500,000** | listed as an O&M cost; whether spent or estimated is unclear | strong: "Greenwich Mill Creek Dike" | [S1] Table 23 |
| Mill Creek (Union Bank) | Rebuild, strengthen and raise the levees on "Mill Creek, Molly Wheaton Run and Mounces Creek" | 3 levees together; lengths not given | 2013 | **$1.5-3 M** for all three | estimate | probable but bundled: all three creeks feed the Cohansey at Greenwich | [S2] p.113 |
| Mill Creek (Union Bank) | "Gates were repaired at County dike parallel to Bridgeton–Greenwich Road" | gates | 2014 | not given | — | approximate | [S10] |
| **Silver Lake** (Lower Alloways Creek; 3.19 km / 9,617 ft) | Breach repairs | 3 breaches of about 60 ft (1933); 810 ft washed out (1950); 90-ft breach (1955) | 1933 / 1950 / 1955 | $1,256 (about $7/ft); **$12,157** (about $15/ft); **$16,221** (about $180/ft) | actual | strong | [S1] p.115, quoting USDA SCS 1957 |
| **Silver Lake + Locust Island** (Locust Island: 2.47 km / 8,934 ft) | Federal watershed plan: repair and rebuild 5,100 ft (Silver Lake) and 7,300 ft (Locust Island) of dike, with pipe sluiceways and tide gates, plus farm conservation work | 12,400 ft + gates | 1957 plan, built by 1962 | **$350,000** for the whole plan (no more than about $28/ft for the dike) | estimate (plan total) | strong | [S11] DRBC 1962, p.20 |
| Silver Lake + Locust Island | Yearly repairs, on top of normal upkeep | per year | about 1957 | $300-500 per year | actual (as reported) | strong | [S1] p.115 |
| Silver Lake (maybe) | West Branch sluice repair and rebuild, Stow Neck Rd (Block 53 Lot 19) | 1 sluice | 2026 | **$1,804,447.72** | award (on a draft agenda; adoption not confirmed) | uncertain: Stow Neck Rd is 1-2 km from the Silver Lake bank (`reports/tide_gates_public.md`) | [S4], [S5] |
| Lighthouse (maybe) (Pennsville; 5.14 km / 624 ft) | Miles Creek sluice: one of three sluices in a $2.7 M request | 1 of 3 | FY26 request | share not given | request | uncertain: the creek is 0.7 km from the bank | [S8] |
| Locust Island, Hancocks Bridge Poplar, Lower Alloways Creek (maybe) | "Two Sluice Gates ... on the banks of the Alloways Creek" (Lower Alloways Creek Twp application) | 2 gates | FY26 request; on hold in Jan 2026 | amount not given | request | uncertain: the gate sites are not given | [S3] Res. 2025-117; [S9] |
| Jones Island Road / Sayres Neck (Lawrence) | Sheppard Farms, Cedarville: "we raised the dikes two feet" after a Sandy breach | not given | after 2012 | **none given** | — | likely one of these two: their NLD sponsors are "G Erwin & Donna M Sheppard" and "SF Systems CO" | [S20] snippet |
| Sunset Road (Mannington; 0.46 km / 1,584 ft) | Failed in Irene (2011); Salem County repaired it | — | 2011 | none found | — | — | `reports/tide_gates_public.md` |
| **No public cost found** | Durham, Back Neck, Sea Breeze Road (Fairfield); Sheppard Davis (Lawrence); County Hwy 623, Richard Wood (Lower Alloways Creek); Henby Creek (Carneys Point); plus Hancocks Bridge Poplar, Lower Alloways Creek, Lighthouse, Jones Island Road and Sayres Neck apart from the "maybe" rows above | | | | | | |

Notes on Table A:
- **The two Salem County requests are for the same projects.** FY26 asked for $2.7 M for "the
  West Branch, Miles Creek, and Alloways Creek sluices". FY27 asked for $2.7 M to replace "four
  critically failing ... sluice gate water control structures" in Lower Alloways Creek and
  Pennsville. The House FY27 bill carries $1.0 M. The West Branch contract alone ($1.80 M) is
  two-thirds of the request, so $2.7 M will not cover four rebuilds.
- **A "Fairfield agricultural levee" in the 2010 inventory has gate costs (Table B, row G4).**
  Three of the 18 areas are in Fairfield: Durham, Back Neck and Sea Breeze Road. The source
  does not say which levee it is, so it is listed as a proxy.

## Table B. Proxy costs, for scaling

"Comparable?" says how well the item stands in for a NJ farm bank or its gate.

### B1. Cost per length of bank

| # | Site (state) | Work | Length | Year ($) | Amount | $/ft | Kind | Comparable? | Source |
|---|---|---|---|---|---|---|---|---|---|
| L1 | Army Corps national guide | New earthen levee 5 ft high (1:3 slopes, 10-ft crest), whole project including design, land, permits and a 35-55% contingency | per ft | Mar 2023 | — | **$34-520** (construction only $19-204) | estimate (national) | **Medium.** It is systematic, with low and high ends, but it comes from river levees. Low end: fill dug on site. High end: fill hauled in, which is likely for marsh banks. 15 ft high: $200-3,100/ft | [S12] |
| L2 | Army Corps national guide | Repairing an embankment slope with riprap | per ft | Mar 2023 | — | $180-450 | estimate | Medium: for armouring a creek-side face | [S12] |
| L3 | Matt's Landing impoundment dike, Maurice River Twp (NJ) | Repair of a 130-yard breach (Sandy, then a Dec 2012 storm) | 390 ft | 2013 | $750,000 | **~1,900** | actual | **Good for a breach.** Same bay and same kind of bank. Rebuilt only to its old height | [S2] (Sandy impacts section) |
| L4 | Repaupo / Gibbstown levee (NJ) | Gate rebuild plus re-armouring of 3,400 ft to the 100-year storm | 3,400 ft | 2013 | $12.5 M | ≤ 3,700 | actual | Upper bound only: the gate is included and the standard is high | [S6] |
| L5 | Pedricktown North disposal site, Salem County (NJ) | Raising the dikes of a dredged-material site (Army Corps contract) | about 25,000 ft (from a listing, not verified) | 2024 | $15,504,300 | ~620 | award | **Low-medium.** Local contractor and soils, but these are tall dikes, not a farm bank | [S13], [S14] |
| L6 | Peak of the Moon dike, Commercial Twp (NJ) | Strengthen a mile-long dike: sheet piles, stone sill and marsh plants, 2 water control structures | about 1 mile | 2013 | $3,343,900 | ~630 | estimate | Low-medium: a hardened, living-shoreline design | [S2] p.113 |
| L7 | "Maple Avenue Levee", Downe Twp (NJ) | Rebuild, strengthen and raise | 2,809 ft if it is the inventory's "Maple Street" levee in Downe | 2013 | $3.5 M | ~1,250 if the same levee | estimate | Medium if the names match: same bayshore, raised for flood protection | [S2] p.113; [S1] Table 7 |
| L8 | "Market Lane Levee", Greenwich Twp, Cumberland (NJ) | Same project list | 855 ft if it is the inventory's "Market Street" levee in Greenwich | 2013 | $750,000 | ~880 if the same levee | estimate | Low-medium: the name match is uncertain | [S2] p.113; [S1] Table 7 |
| L9 | Pine Mount Creek Levee, Greenwich, Cumberland (NJ) | New levee and flood gates | not given | 2013 | $2.4-14 M | — | estimate | Length unknown | [S2] p.113; [S10] |
| L10 | Delaware Ave levee, Greenwich Twp, Cumberland (NJ) | Repair or build a new levee | not given | 2022 | $600,000 | — | estimate | Length unknown | [S10] p.7-25 |
| L11 | Heislerville dike, Maurice River Twp (NJ) | Permanent repairs after Tropical Storm Isaias (FEMA) | inventory length 14,984 ft; how much is repaired is not given | 2026 | ~$4.9 M | ≤ ~330 if the whole length | award (one news source) | Low: wildlife impoundment; scope unknown | [S15] |
| L12 | Red Lion dike, New Castle (DE) | Rebuild after Sandy | not found | 2013 | ~$7 M | — | estimate | Delaware; length not found | [S16] |
| L13 | Gambacorta Marsh dike, New Castle (DE) | Sandy damage | not given | 2012 | $940,000 | — | damage estimate | Delaware; not a repair cost | [S17] |
| L14 | 19th-century Salem and Cumberland meadow banks | Banks built from ditch mud | per rod (16.5 ft) | 1800s-1866 | $1/rod (early 1800s), $3/rod (1866); $2/rod on the Maurice River including drains | $0.06-0.18 | actual (historical) | Background only | [S19] snippet |

### B2. Cost per gate or sluice structure

| # | Site (state) | Work | Quantity | Year ($) | Amount | Per structure | Kind | Comparable? | Source |
|---|---|---|---|---|---|---|---|---|---|
| G1 | Middle Neck (NJ, one of the 18) | Emergency repair, 48-in pipes (Table A) | 4 | 2018-19 | $630,100 | **~$158,000** | actual | **Best local repair figure** | [S3] |
| G2 | West Branch sluice, Stow Neck Rd, Lower Alloways Creek (NJ) | Repair and rebuild | 1 | 2026 | $1,804,447.72 | **$1.8 M** | award (draft agenda) | Good for a full rebuild of a large county sluice | [S4] |
| G3 | Salem County request (NJ) | Replace 4 failing sluice structures | 4 | FY27 | $2.7 M | ~$675,000 | request | Medium: the request is below cost (see G2) | [S8] |
| G4 | "Fairfield agricultural levee" (NJ) | Replace 2 tidegate structures, fill the dike, clean ditches, reseed | 2 | about 2009 | #1: $17,435 labour + $3,245 materials; #2: $11,118.50 labour + $3,734.24 materials | **~$15,000-21,000** | listed as an O&M cost | **Good for small farm gates**; possibly Durham, Back Neck or Sea Breeze Road | [S1] Table 23 |
| G5 | "Greenwich agricultural levee" (NJ; Greenwich in Cumberland or Gloucester, not stated) | Dike rehab, a water control structure, reseeding | 1 | about 2009 | $29,945.40 labour + $17,785.60 materials | ~$47,700 (dike included) | O&M cost | Good, small farm scale | [S1] Table 23 |
| G6 | Mill Creek dike (NJ, one of the 18) | 2 tidegate structures plus levee repair | 2 | about 2009 | > $500,000 | < $250,000 each | O&M cost | Good | [S1] Table 23 |
| G7 | Fenwick Creek, Salem City (NJ) | Refurbish 1 tide gate and replace the mounting bracket on another (7 gates in all) | 1-2 | 2019 | $101,000 | ~$50,000-100,000 | actual (not-to-exceed) | Good for a part repair | [S3] Res. 2019-410 |
| G8 | Gibbstown flood gates (NJ, one of the 18) | Repairs | not given | 2020 | $405,000 | — | estimate | Good, but the count is unknown | [S7] |
| G9 | Peak of the Moon, Commercial Twp (NJ) | Ductile iron pipe, tide gate and trash rack (listed as "48-foot"); 2 aluminium water control structures | 1 + 2 | 2013 | $70,000; $100,000 | $50,000-70,000 (items only) | estimate | Good for parts; add mobilisation and contingency | [S2] p.113 |
| G10 | Army Corps national guide | New drainage pipe through a levee: 150 ft of concrete pipe, sluice gate, flap gate, gate well | 1 pipe | Mar 2023 | — | **48-in: $1.2-2.2 M** whole project ($0.70-0.86 M construction); 72-in: $2.1-3.5 M | estimate | Medium: a full federal standard. Brackets G2 well | [S12] |
| G11 | Army Corps national guide | Lining damaged pipes with HDPE | per ft | Mar 2023 | — | $70-750/ft | estimate | Fits Middle Neck-style repairs | [S12] |
| G12 | Little Creek main impoundment (DE) | Replace one water control structure and restore a 1.3-mile ditch | 1 + ditch | construction 2026 | $859,374 | — | funded | Low: the ditch is included | [S18] |
| G13 | Stave Landing Rd tide gate, Townsend (DE) | Tide gate site work (New Castle Conservation District) | 1 | 2023 | ~$1.0 M | — | estimated value (bid listing) | Low: listing figure only | [S21] |

### B3. Upkeep (maintenance) costs

| Item | Amount | Year | Source |
|---|---|---|---|
| Yearly repairs at Silver Lake–Locust Island | $300-500 per year, on top of normal upkeep | about 1957 | [S1] p.115 |
| Meadow company dues | 50¢-$1 per acre per year; Finn's Point averaged $2 per acre per year | 1866 | [S19] snippet |
| Army Corps routine upkeep for levees: mowing $65-500 per acre; burrow repair $350-2,500 each; minor repairs to the crest and sides $1-2 per sq ft; slide repair $19-68 per cu yd; upkeep of a drainage structure $530-22,000 per structure per year | as listed | Mar 2023 | [S12] |
| Permit fees: Army Corps nationwide permit $100; NJDEP waterfront permit $3,500 + 1.2% of construction (up to $50,000 of work); coastal wetlands permit $600 | as listed | 2009 | [S1] App. E |

### Which proxy to use

- **Bank rebuild or raise, per foot:** use the Army Corps 5-ft range, $34-520/ft (L1). The local
  figures sit at or above its top end: $620/ft at Pedricktown, about $630/ft at Peak of the Moon,
  and about $1,250/ft for Maple Ave if the names match. A NJ bayshore bank probably costs
  **$300-1,000/ft** to rebuild. That band is my reading, not a published figure.
- **Raising a bank by 2 ft.** This is my own arithmetic, not a published figure. Take a bank 5 ft
  high with a 10-ft crest and 1:3 slopes. Raising it 2 ft adds about 3.4 cubic yards of fill per
  foot of bank. At the Army Corps fill price of $3.80-40.80 per cubic yard, that is about
  $13-140/ft to build, or about $25-360/ft once design, permits and contingency are added.
- **Breach repair:** about $1,900 per foot of breach (Matt's Landing, 2013).
- **Gates:**
  - A small farm flap gate costs about $15,000-50,000 (G4, G5, around 2009).
  - Emergency repair of a county sluice gate costs about $150,000 each (Middle Neck, 2018).
  - A full rebuild of a county sluice costs about $0.7-1.8 M each (G2, G3, G10).

## Leads that need a person

1. **NRCS New Jersey, Somerset state office.** Ask the State Conservation Engineer or the
   watershed planner, and the Vineland Service Center, for four things:
   - **The 1950s-60s watershed work plans and as-built costs:** Silver Lake–Locust Island
     (January 1957), Pine Mount–Mill Creek (1964), Middle Neck (1965) and Repaupo "White Sluice"
     (1964). These give costs per structure and per foot of dike for 4 of the 18 areas.
   - **The Access database behind the 2010 South Jersey Levee Inventory.** It holds levee
     height, crest width and condition per levee.
   - **Which levees Table 23 refers to:** the "Fairfield" and "Greenwich" agricultural levees.
   - **The current NJ EQIP payment schedule,** which gives unit costs for practice 356 (Dike)
     and 587 (Structure for Water Control). The NRCS website timed out during this search.
2. **Salem County Engineer and Purchasing, (856) 935-7510.** Ask for:
   - **Bid #26-16 (West Branch):** the bid tab and engineer's estimate, from salempurchasing.org.
   - **The FY26/FY27 sluice-gate application,** with estimates for each structure.
   - **Final paid totals** for the Middle Neck gates (W. J. Castle / Hydro-Marine, 2018-19)
     and the Fenwick Creek gates (2019).
   - **The cost of the Sunset Road levee repair** after Irene (2011).
3. **Lower Alloways Creek Township clerk.** Ask for the estimate behind Res. 2025-45 (two
   Alloways Creek sluices) and for the site of the Hancocks Bridge sluice.
4. **Gloucester County Improvement Authority, and Greenwich Twp (Gloucester).** Ask for:
   - **The Repaupo $12.5 M split:** how much went to the gate (Phase I) and how much to the
     3,400 ft of levee (Phase II), with the bid tabs. The designer was T&M Associates.
   - **The final cost of the 2020 flood-gate repair.**
5. **Cumberland County Planning and Engineering.** Ask for:
   - **What the 2013 Recovery Plan levee estimates were based on:** the lengths and target
     heights for Maple Ave, Market Lane, Mill Creek and Pine Mount.
   - **The cost of the 2014 Mill Creek gate repair.**
   - **The Greenwich Township Levees Project design.**
6. **NJDEP Fish & Wildlife.** Ask for the FEMA project scope for the Heislerville dike
   (disaster DR-4574): how many feet are being repaired.
7. **Tom Sheppard, Sheppard Farms, Cedarville.** Ask what raising the dikes 2 ft after Sandy
   cost, and which banks were raised. It may have been cost-shared through NRCS.
8. **Delaware.** Ask:
   - **DNREC Wildlife Section, 302-739-9912:** the cost per foot of the Little Creek and Ted
     Harvey dike work (2023-24).
   - **DNREC Shoreline & Waterway:** the final cost and length of the Red Lion and other
     New Castle dike rebuilds.
9. **PSEG Estuary Enhancement Program.** Ask what it cost to breach and remove dikes at the
   Alloway Creek and Commercial Township sites, and to repair the half-mile of upland dike
   damaged in Sandy.
10. **Army Corps National Levee Safety Program, LeveeCosts@usace.army.mil.** Ask whether there
    is a coastal or tidal adjustment to the national ranges in L1 and G10.

## Sources

Opened and read:
- [S1] USDA NRCS, *South Jersey Levee Inventory*, July/November 2010 (for NJDEP Bureau of
  Dam Safety and Flood Control). The original URL is dead. Read from the Wayback copy of
  http://www.nrcs.usda.gov/Internet/FSE_DOCUMENTS/nrcs141p2_018319.pdf (snapshot 2022-10-14).
  Table 7 (lengths), Table 23 (O&M costs), Table 24 (PL-566 projects), pp.109-131.
- [S2] Cumberland County, *Delaware Bayshore Recovery Plan*, Dec 2013:
  https://cumberlandcountynj.gov/filestorage/22641/22643/22956/22971/44901/Final_Recovery_Plan_1-14.pdf
- [S3] Salem County Board of Chosen Freeholders / Commissioners resolutions:
  - 2018-286: https://www.salemcountynj.gov/wp-content/uploads/2018/08/2018-286-Resolution-Declaring-Emergency-to-make-repairs-to-sluice-gates-on-sinnickson-landing-road-elsinboro.pdf
  - 2018-287: https://www.salemcountynj.gov/wp-content/uploads/2018/08/2018-287-Resolution-for-Emergency-Appropriation-Sluice-Gates-on-Sinnickson-Landing-Road-Elsinboro.pdf
  - 2018-342: https://www.salemcountynj.gov/wp-content/uploads/2018/10/2018-342ResolutionAmendingResolution2018-286DeclaringEmergencySinnickson27sLandingRoad.pdf
  - 2018-360: https://www.salemcountynj.gov/wp-content/uploads/2018/11/Resolution-2018-360-Resolution-Authorizing-Change-Order-1-Sluice-Gates-Sinnickson-Landing-Road.pdf
  - 2019-282: https://www.salemcountynj.gov/wp-content/uploads/2019/08/282-min-1.pdf
  - 2019-410 (Fenwick Creek): https://www.salemcountynj.gov/wp-content/uploads/2019/11/410-min.pdf
  - 2025-117: https://www.salemcountynj.gov/wp-content/uploads/2025/03/117-Supporting-Lower-Alloways-Creek-Township-Resolution-2025-45-In-Support-of-An-Application-To-Congressman-Van-Drew-FY26-Community-Project-Fund-min.pdf
- [S4] Salem County Commissioners, draft agenda for 19 Aug 2026, item A6:
  https://www.salemcountynj.gov/wp-content/uploads/2026/08/8.19.26Agenda-Draft.pdf
- [S5] Salem County bid notice #26-16, West Branch Sluice:
  https://www.salemcountynj.gov/public-notice-specifications-for-west-branch-sluice-repair-and-rehabilitation-project-stow-neck-road-salem-county-new-jerset-bid-26-16/
- [S6] Gloucester County Improvement Authority:
  - "Previous Projects": https://www.gcianj.com/project-financing/previous-projects/
  - Board agenda, 20 Jan 2011: https://www.gcianj.com/meeting-agendas/1-20-11A.pdf
- [S7] Greenwich Township (Gloucester County), closed-session minutes, 18 Feb 2020:
  https://www.greenwichtwp.com/DocumentCenter/View/1349/Minutes---021820-Closed-Session
- [S8] Rep. Van Drew, community project funding:
  - FY26: https://vandrew.house.gov/community-project-funding-requests/community-project-funding-fy26.htm
  - FY27: https://vandrew.house.gov/services/community-project-funding-fy27.htm
  - FY27 disclosure letter, 1 Mar 2026 (no amounts): https://vandrew.house.gov/UploadedFiles/DISCLOSURE_-_Salem_County_Sluice_Gates.pdf
  - House bill release, 8 Jun 2026 ($1,000,000): https://vandrew.house.gov/news/documentsingle.aspx?DocumentID=2052
- [S9] Lower Alloways Creek Twp minutes, 16 Jul 2024 and 20 Jan 2026 (no amounts):
  - https://www.lowerallowayscreek-nj.gov/sites/g/files/vyhlif3381/f/minutes/mtg_july16_2024.pdf
  - https://www.lowerallowayscreek-nj.gov/sites/g/files/vyhlif3381/f/minutes/jan202026_mtg.pdf
- [S10] Cumberland County Multi-Hazard Mitigation Plan Update 2022:
  - Greenwich Twp appendix: https://cumberlandcountynj.gov/filestorage/22641/22643/22652/08-Greenwich-TWP-FINAL-2022-0822_PDF_R2_7.7.23.pdf
  - County volume (no levee costs): https://www.cumberlandcountynj.gov/filestorage/22641/22643/22652/02-Cumberland-CO-FINAL-2022-0822_PDF_R2_7.7.23.pdf
- [S11] Delaware River Basin Commission, Comprehensive Plan Phase I, 28 Mar 1962, item 17:
  https://www.nj.gov/drbc/library/documents/comprehensive_plan1962.pdf
  Later status ("3.5 miles of dike"): https://www.nj.gov/drbc/library/documents/comprehensive_plan.pdf
- [S12] USACE National Levee Safety Program, *Summary of Costs Associated with Levee-Related
  Activities*, Nov 2023 (March 2023 prices). The original URL returns 403; read from the
  Wayback copy of
  https://mmc.sec.usace.army.mil/NLSP_website/NLSP_LeveeCostBrochure_FINAL_NOV2023.pdf
  (snapshot 2024-06-28).
- [S13] USAspending, contract W912BU24C0010, "Dike raising at Pedricktown North Disposal Area,
  Salem County, NJ", Richard E. Pierson Construction, $15,504,300, 14 Jun 2024. Read through the
  API; award page:
  https://www.usaspending.gov/award/CONT_AWD_W912BU24C0010_9700_-NONE-_-NONE-
- [S14] ConstructConnect listing (gives the "approximately 25,000 linear feet"):
  https://projects.constructconnect.com/details/6216285-rfq-contractor-pedricktown-north-dredged-material-placement-facility-dike-raising-construction&find_loc=NJ-08079
- [S15] FingerLakes1, "FEMA awards nearly $117 million for New York, New Jersey recovery",
  1 Sep 2026. This is secondary; no FEMA release was found.
  https://www.fingerlakes1.com/2026/09/01/fema-awards-nearly-117-million-for-new-york-new-jersey-recovery/
- [S16] Delaware Public Media, "Work begins to address storm damage to New Castle dike system",
  6 Aug 2013: https://www.delawarepublic.org/2013-08-06/work-begins-to-address-storm-damage-to-new-castle-dike-system
- [S17] Delmarva Public Media, "Beefing up storm infrastructure along Delaware coast",
  10 Dec 2012: https://www.delmarvapublicmedia.org/local-news/2012-12-10/beefing-up-storm-infrastructure-along-delaware-coast
- [S18] NOAA Restoration Atlas (RCDB) project 201, Army Creek / Little Creek (DE):
  https://www.habitat.noaa.gov/apps/rcdb_services/rcdb/project/201
- [S21] ConstructConnect, "Delaware Wild Lands Tide Gate - Stave Landing Road" (DE):
  https://projects.constructconnect.com/details/6348094-delaware-wild-lands-tide-gate-stave-landing-road%26find_loc=delaware-19734
- USACE National Levee Database, the repo's copy (`data/structures/structures.gpkg`): townships,
  sponsors and bank lengths for the 18 systems. https://levees.sec.usace.army.mil/

Seen only in search snippets, or behind a paywall:
- [S19] Sebold, K., *From Marsh to Farm: The Landscape Transformation of Coastal New Jersey*,
  National Park Service, 1992, chapter 4. The page reset the connection and the NPS mirror
  page held no text.
  https://npshistory.com/publications/new-jersey/marsh-farm/chap4.htm
- [S20] Civil Eats, "Sea Level Rise Is Already Changing What Farmers Can Grow", 15 Jan 2024
  (Sheppard quote; paywalled):
  https://civileats.com/2024/01/15/as-saltwater-encroaches-on-farms-solutions-emerge-from-the-marshes/

Checked, but no cost found:
- NJDEP news release 03/160, 28 Oct 2003: Repaupo levee eligible for bond money; no amount.
  Read from the Wayback copy of https://www.nj.gov/dep/newsrel/releases/03_0160.htm
- NJ Fish & Wildlife, Heislerville impoundments (2022):
  https://www.nj.gov/dep/fgw/news/2022/05-20_heislerville_wma_impoundments.htm
- DNREC, New Castle resilient community page:
  https://dnrec.delaware.gov/coastal-programs/planning-training/resilient-communities/new-castle
- DNREC, Little Creek dike repair releases (2023):
  https://news.delaware.gov/2023/07/18/partial-closures-of-little-creek-wildlife-area-to-begin-aug-1-for-main-impoundment-dike-restoration-project
- Cumberland County contract databases (2023, 2024): no dike or gate contracts.
- NRCS NJ payment schedule page: timed out.
- Salem County Commissioners minutes and agendas, 2014, 2019, 2022 and 2025: no other sluice amounts.
