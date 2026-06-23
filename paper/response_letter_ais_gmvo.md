# AIS GMVO — response-letter material + verification checklist

Auxiliary note for the HESS submission. **Not part of the manuscript.** Holds the
administrative provenance of the AIS GMVO data source for a reviewer who asks why the
source link is dead, plus the items a fresh session must verify before this text is used.

The **manuscript itself** states only the qualitative, safe timeline (portal operated by
Rosvodresursy, decommissioned September 2025, migrated to GIS CP "Voda" behind domestic
auth, static subset DOI-archived). The granular order numbers below are kept **out of the
paper** and live here for the response letter only.

## 1. Administrative claims to VERIFY (author-provided, UNVERIFIED)

These came from the author's recollection and are checkable against Russian government /
Rosvodresursy sources. **Confirm each before sending the response letter** — a wrong order
number is worse than omitting it. If a number can't be confirmed, drop it and keep the
qualitative timeline.

| Claim | What to confirm | Status |
|-------|-----------------|--------|
| Rosvodresursy **Order No. 97**, **August 2013** | AIS GMVO inception / pilot | ⬜ unverified |
| Rosvodresursy **Order No. 297** | Digital Transformation Program → GIS CP "Voda" | ⬜ unverified |
| Rosvodresursy **Order No. 222** | formalizes decommission, **Sept/Oct 2025** | ⬜ unverified |
| Trial operation **2023–2024** | GIS CP "Voda" trial segments | ⬜ unverified |
| Decommission **9 September 2025** | last public access to AIS GMVO | ⬜ unverified |
| Replacement **gis.favr.ru / sslgis.favr.ru** | closed-circuit, ESIA/Gosuslugi auth | ⬜ unverified |
| Last successful data pull: **summer 2025** | author's extraction date (refine if exact known) | ⬜ refine |

## 2. Draft response-letter paragraph (deploy only confirmed facts)

> The discharge and water-level records were obtained from the Automated Information
> System for State Monitoring of Water Objects (AIS GMVO, gmvo.skniivh.ru), the public
> portal of the Federal Agency for Water Resources (Rosvodresursy), which had served as the
> primary open repository for Russian hydrological monitoring since its inception
> (Rosvodresursy Order No. 97, August 2013). Under Rosvodresursy's Digital Transformation
> Program (Order No. 297), AIS GMVO was superseded by the State Information System "Water
> Data" (GIS CP "Voda"); after trial operation in 2023–2024, the legacy infrastructure was
> decommissioned in September 2025 (Order No. 222). The replacement platform (gis.favr.ru /
> sslgis.favr.ru) uses a closed-circuit architecture requiring domestic authentication via
> ESIA/Gosuslugi, so the URLs active during our data extraction (summer 2025) are no longer
> publicly resolvable. To preserve reproducibility, the exact static subset used in this
> study is permanently archived under DOI [Zenodo DOI] as part of the CAMELS-RU v1.0 release.

## 3. Figure / temporal-consistency audit (manuscript)

Cross-check that every date/temporal label in and around the figures matches the corrected
timeline (study coverage **2008–2023**; AIS GMVO public operation 2008 → **Sept 2025**):

- [ ] Figure captions and axis ranges in `paper/overleaf/sections/` + `images/` — any year
      labels, time axes, or coverage statements consistent with 2008–2023.
- [ ] `\years` macro and every inline "2008–2023" / "16-year" statement agree.
- [ ] No residual "2024"/"2025" access or coverage dates that contradict §3.1 (portal
      operated 2008 → closed to public 2025) or the corrected refs.bib (`AIS_GMVO`, last
      access summer 2025; `GRDC`, last access 2025).
- [ ] precip-comparison / Budyko / signature-map period labels match the analysis window.
- [ ] `pixi run python scripts/verify_macros.py` stays green after any change.
