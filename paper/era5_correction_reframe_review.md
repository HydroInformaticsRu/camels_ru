# ERA5-Land over-accumulation correction — coordinated manuscript reframe (REVIEW DRAFT)

**Status:** APPLIED (framing A, demote). Macros + §5 + abstract + §4 + discussion + conclusions edited;
5 figures regenerated; `verify_macros` green.

> **FINAL-STATE CORRECTION (post figure-regeneration):** the regenerated cited figure
> (`fig_coldregion_gradient` panel C) **refuted** the "AET>PET co-locates with snow" claim —
> the corrected rate is single-digit and *non-monotonic* in snow (highest at LOW snow, ~17.6%,
> likely arid southern catchments). Per your call, the **snow-concentration story was dropped
> entirely**: removed from abstract/§5/§4/discussion/conclusions, the §4→§5 snow bridge removed,
> and panel C's AET>PET bars dropped (melt-timing line kept, title de-claimed). The forcing
> result now reads "a modest, several-fold forcing-dependence (6.9 vs 1.5/2.9%)" with no snow
> gradient. The §5 prose blocks below that mention "snow-concentrated" are SUPERSEDED by this.
**Data layer already corrected (local):** scripts repointed → `era5land_tp_new`; `budyko_aet_table.csv`,
`precip_dataset_comparison.csv`, `precip_inter_dataset_corr.csv`, `water_balance_strata*`, and
`data/CAMELS_RU/statistics/` signatures all regenerated on corrected precip.

---

## 1. The corrected scientific story (one paragraph)

The three precipitation products **broadly agree** (MSWEP 609 < GPCP 657 < ERA5-Land 705 mm yr⁻¹, within ~16 %).
ERA5-Land is **modestly wettest** (+96 vs MSWEP, +48 vs GPCP), consistent with a known cold-season wet bias.
Daily agreement is actually **good** (ERA5–MSWEP daily *r* = 0.92). The water-balance diagnostics that were the
manuscript's headline are **no longer extreme**: ERA5 water-balance AET now equals GLEAM AET to within 4 %
(ratio 1.40 → **0.96**); AET\_wb > PET drops 44.8 % → **6.9 %** (vs MSWEP 1.5 %, GPCP 2.9 %); the closure residual
goes from a large positive lobe (+175 mm yr⁻¹, 91 % positive) to **near-zero** (−19, 42 % positive), like GPCP.
The forcing-choice signal **survives but is modest**: ERA5 still yields ~2–4× more AET>PET cases than the
gauge-based products, weakly concentrated in snow basins (4 → 7 %). The prior "physically implausible across
~half the domain" headline was an over-accumulation artifact.

---

## 2. ⚑ KEY DECISION — how prominent should the forcing result remain?

Currently the abstract bills forcing as **"The clearest result"** and the discussion as **"The most transferable
finding."** At 6.9 % vs 1.5/2.9 %, those superlatives are no longer defensible. Two honest options:

- **(A) Demote (recommended).** Forcing becomes a *quantified, modest, snow-concentrated* forcing-dependence and a
  practical "choose your precipitation product" caution — still worth reporting, but not the paper's headline. The
  **cold-region permafrost–BFI non-monotonicity** (unaffected by this bug) becomes the lead scientific finding.
- **(B) Keep but soften.** Forcing stays a co-headline, reworded to "a several-fold forcing-dependence (6.9 vs
  1.5/2.9 %), concentrated in snow basins," dropping "physically implausible / half the domain."

The §5 *numbers* are identical either way; only the billing language in abstract ¶3 / discussion heading /
conclusions item 3 differs. **Prose below is drafted for (A)**, with (B) alternatives noted for the headline
sentences.

---

## 3. Macro changes (`paper/overleaf/macros.tex`)

| Macro | Old | **New** | Note |
|---|---|---|---|
| `\erafiveannual` | 904 mm yr⁻¹ | **705 mm yr⁻¹** | recompute, n=3201 |
| `\mswepannual` | 609 | 609 | unchanged ✓ |
| `\gpcpannual` | 657 | 657 | unchanged ✓ |
| `\eramsweprcorr` | 0.83 | **0.92** | daily *r* (0.915) |
| `\eragpcpcorr` | 0.57 | **0.66** | daily *r* (0.664) |
| `\mswepgpcpcorr` | 0.73 | 0.73 | unchanged ✓ (anchor) |
| `\aetgtpeterafive` | 44.8 % | **6.9 %** | budyko table (124/1789) |
| `\aetgtpetmswep` | 1.5 % | 1.5 % | unchanged ✓ |
| `\aetgtpetgpcp` | 2.9 % | 2.9 % | unchanged ✓ |
| `\nwaterbalgauges` | 1,844 | **1,845** | valid-index count |
| `\nwbpairgauges` | ~2,070 | **~2,090** | Q/P paired n=2090 |
| `\nwaterbaldamfree` | 1,799 | **1,800** | confirm at edit (Task 3) |

> Verify `\eragpcpcorr`/`\mswepgpcpcorr` macro names exist (only `\eramsweprcorr` showed in grep — the other two
> may be hardcoded in §5). I'll reconcile at edit time.

---

## 4. `scripts/verify_macros.py` expectation updates (script, not manuscript)

- `expected_precip`: ERA5-Land (3201, **705**, **225**), MSWEP (3201, 609, 217), GPCP (3201, **657**, **206**).
- `expected_corr`: ERA5-Land vs MSWEP (3201, **0.915**, **0.265**), ERA5-Land vs GPCP (3201, **0.664**, **0.126**),
  MSWEP vs GPCP (3201, 0.725, −0.138). *(N was 3194 → now 3201.)*
- in-text energy-viol E/M/G: 48.9/2.0/3.4 → **8.1/2.0/3.4**
- in-text aridity E/M/G: 0.71/1.02/0.92 → **0.91/1.02/0.92**
- in-text evaporative E/M/G: 0.74/0.61/0.66 → **0.67/0.61/0.66**
- `\nwaterbalgauges` 1844 → 1845.

**Signature-derived dam-free medians stay blocked on Task 3** (`mediandamfreerunoffratio` 0.258 → ~0.33, etc.):
they verify against the *release* `signatures.csv`, which we don't overwrite until you approve the release refresh.
Until then verify_macros will (correctly) flag those as pending-release.

---

## 5. Reframed prose — section by section (OLD → NEW)

### 5a. `00_abstract.tex` ¶3 — option (A)

**OLD:** "The clearest result concerns the forcing. … exceeding potential evapotranspiration in `\aetgtpeterafive`
of catchments under ERA5-Land --- physically implausible in the long-term mean --- against … with the failure rate
highest in the snowiest basins. We therefore release MSWEP…"

**NEW (A):**
> A third result concerns the forcing. The choice of precipitation product measurably shifts the apparent water
> balance of the same catchments: a Budyko / GLEAM actual-evapotranspiration adequacy diagnostic finds inferred
> long-term actual evapotranspiration exceeding potential evapotranspiration in `\aetgtpeterafive` of catchments
> under ERA5-Land, against `\aetgtpetmswep` under MSWEP and `\aetgtpetgpcp` under GPCP --- a several-fold,
> snow-concentrated forcing-dependence that, though modest in absolute terms, is large enough to matter for
> cold-region water-balance studies. We release MSWEP as the primary precipitation forcing and treat
> forcing-product choice as a hydrological decision rather than an interchangeable input.

**(B) alt opener:** "A second headline result concerns the forcing. … a several-fold forcing-dependence (6.9 % vs
1.5–2.9 %) concentrated in the snowiest basins…" (drop "physically implausible / half the domain").

### 5b. `03_data_methods.tex:98` — macro only
"ERA5-Land precipitation (mean annual `\erafiveannual`)…" → renders **705** automatically once the macro changes.
No prose edit. ✓

### 5c. `05_forcing_uncertainty.tex` (full section)

**¶4 (intro, line 4):** keep the framing but soften "the spread is largest in exactly the cold, snow-dominated
basins." Suggest: "…the choice of precipitation product shifts the apparent water balance --- runoff ratios,
Budyko position, and the adequacy of inferred evapotranspiration --- by a modest but systematic margin, largest in
the cold, snow-dominated basins that define the Russian domain." *(removes the implied dramatic spread)*

**¶ line 9 (daily stats):** update biases & *r*:
- ERA5–MSWEP: *r* = `\eramsweprcorr` ± 0.05, mean daily bias **+0.27** mm d⁻¹; per-catchment annual bias **+96**
  mm yr⁻¹.
- MSWEP–GPCP: *r* = `\mswepgpcpcorr` ± 0.15, daily bias **−0.14**, annual bias −49.
- ERA5–GPCP: *r* = `\eragpcpcorr` ± 0.12, daily bias **+0.13**, annual bias **+48**.
> [DECISION] daily biases: the old +0.76/+0.56/−0.19 came from a catchment-day-pair computation distinct from the
> correlation table's per-gauge biases. I propose citing the **per-gauge corr-table biases** (+0.27/+0.13/−0.14)
> so text and Table 2 match and are reproducible. (Alternative: recompute the catchment-day-pair version.)

**Precip table (lines 22–24):** only the ERA5 row changes →
`ERA5-Land & 705 & 225 & 32.0 \\` (MSWEP 609/217/35.7 and GPCP 657/206/31.4 already correct).

**¶ line 27:**
**OLD:** "…ERA5-Land (`\erafiveannual`) exceeds MSWEP by 295 and GPCP by 246 …, whereas MSWEP and GPCP differ by
only 49, identifying ERA5-Land as the outlier."
**NEW:**
> ERA5 precipitation is a model forecast product whose prognostic cloud microphysics tends to overestimate snowfall
> at high latitudes (Wang2019, Lavers2022; Fig. precip_comparison). ERA5-Land (`\erafiveannual`) exceeds MSWEP
> (`\mswepannual`) by **96 mm yr⁻¹** and GPCP (`\gpcpannual`) by **48 mm yr⁻¹**, while MSWEP and GPCP differ by
> 49 mm yr⁻¹ --- so ERA5-Land is the **modestly wettest** of the three rather than an outlier, consistent with a
> cold-season wet bias.

**Fig precip_comparison caption (line 32):** "+295 mm yr⁻¹ in the basin mean" → "**+96 mm yr⁻¹**"; keep "most
pronounced in mountainous and northern catchments" (still directionally true).

**Q/P table (lines 55–57) + closure (line 60):** medians shift up (corrected lower P → higher Q/P).
> [DECISION] The old Mean/>1 columns used an undocumented notebook filter (not reproducible). I propose
> regenerating the whole table from `recompute_forcing_numbers.py` (median + 5 %-trimmed mean + counts), which
> makes all three rows reproducible:

| Dataset | Median Q/P | Mean Q/P (5 %-trim) | Q/P > 1 (%) |
|---|---|---|---|
| ERA5-Land | **0.332** | **0.358** | **4.5 % (94)** |
| MSWEP | **0.387** | **0.422** | **6.3 % (132)** |
| GPCP | **0.346** | **0.398** | **7.1 % (148)** |

Closure line 60: "98.6 % … median 0.257" → "**95.5 %** of catchments yield Q/P ≤ 1 (median **0.332**)"; soften the
"tautology given the wet bias" sentence (ERA5's Q/P>1 rate 4.5 % is now *below* MSWEP's 6.3 %, but by a small
margin, consistent with a *modest* wet bias).

**Seasonal Q/P (line 62):** DJF **0.18**, MAM **0.63** (3.5× winter), JJA **0.22**, SON **0.26** (was 0.15/0.49/0.16/0.20).

**Fig water_balance caption (line 67):** ERA5 "median +175, positive at 91 %" → "**median −19 mm yr⁻¹, positive at
42 %**" (now closes near zero, like GPCP −28/40 %); MSWEP −109/15 % unchanged. → **figure regeneration required.**

**¶ line 74:** "Valid Budyko indices … 1,861 with ERA5-Land and 1,862 each with MSWEP and GPCP" → "**1,862 each**";
"the ERA5-Land subset reduces to `\nwaterbalgauges`" renders **1,845**.

**¶ line 76:**
**NEW:**
> Across products the median aridity index ranges from **0.91 (ERA5-Land)** through 0.92 (GPCP) to 1.02 (MSWEP),
> placing the typical Russian catchment near the humid–arid transition; the corresponding evaporative-index medians
> (**0.67** ERA5-Land, 0.61 MSWEP, 0.66 GPCP) indicate roughly two-thirds of precipitation returns to the
> atmosphere as AET. Energy-limit excursions (evaporative > aridity, i.e. AET > PET in per-year ratios) affect
> **8.1 % of ERA5-Land catchments (150 gauges)** versus 2.0 % under MSWEP (37) and 3.4 % under GPCP (63); the
> modestly higher ERA5-Land rate is consistent with its cold-season wet bias inflating (P − Q).

**¶ line 78:** AET\_wb medians "625, 347, 424 … ratios 1.40, 0.76, 0.94" → "**435**, 347, 424 mm yr⁻¹ … ratios
**0.96**, 0.76, 0.94" (GLEAM AET 442, PET 645 unchanged). *(This is the cleanest one-line statement of the fix:
ERA5 AET_wb now matches GLEAM AET to 4 %.)*

**¶ line 80 (the headline paragraph) — full rewrite:**
> The choice of precipitation product shifts this water-balance diagnostic by a clear, snow-concentrated margin.
> Water-balance AET (AET\_wb = ⟨P⟩ − ⟨Q⟩) exceeds GLEAM PET in `\aetgtpeterafive` of catchments under ERA5-Land,
> against `\aetgtpetmswep` under MSWEP and `\aetgtpetgpcp` under GPCP; the precipitation-normalised per-year-ratio
> test agrees (energy-limit excursion 8.1 % under ERA5-Land vs 2.0 % and 3.4 %). Because discharge, area, and PET
> are identical across products, this spread isolates precipitation as the operative difference, though we cannot
> exclude some contribution from discharge or boundary error to the absolute exceedance level. The effect is
> snow-concentrated: stratified by snow cover, the ERA5-Land AET > PET rate rises from **≈4 % in low-snow
> catchments to ≈7 % in the snowiest** (Fig. coldregion_gradient c). ERA5-Land is several-fold more prone to this
> energy-limit excess than the two gauge-corrected products --- a modest but systematic forcing-dependence,
> largest where snowfall dominates --- which, with ERA5-Land's wider water-balance residual, motivates the choice
> of MSWEP as the released precipitation forcing in CAMELS-RU.

**Fig budyko caption (line 85):** "cluster systematically above the energy-limited envelope" → "sit **modestly
above** the energy-limited part of the envelope in a minority of humid-regime catchments". → figure regeneration.

**¶ line 92 (precip–discharge):** ERA5 β 0.32 → **≈0.44**, now close to MSWEP's ≈0.45; the old "ERA5 shallower /
MSWEP steeper because lower P" contrast largely dissolves. → exact β pending recompute with the original
regression convention (anchor reproduced MSWEP to 0.455 vs 0.446; I'll lock the convention at edit time).

### 5d. `08_discussion.tex` — "Forcing uncertainty is a result, not a caveat"

**(A)** retitle → **"Forcing choice shifts the apparent water balance"** and reword the central sentence:
> Across identical catchments, the choice of precipitation product moves the apparent water balance by a modest but
> systematic margin: under ERA5-Land, inferred long-term AET exceeds GLEAM PET in `\aetgtpeterafive` of catchments,
> against `\aetgtpetmswep` under MSWEP and `\aetgtpetgpcp` under GPCP (Sect. budyko) --- several-fold more often
> under reanalysis precipitation, concentrated in snow-dominated basins.
Drop "physically implausible without unaccounted import." Keep the transferable-hypothesis and Caravan paragraph
(still valid: a *modest* forcing-dependent water balance is still invisible to aggregate skill scores).

### 5e. `09_conclusions.tex` item 3

**NEW:**
> It shows that the choice of precipitation product shifts the apparent water balance, not merely the reported
> numbers. A combined Budyko / GLEAM-AET-adequacy diagnostic finds water-balance AET exceeding GLEAM PET in
> `\aetgtpeterafive` of catchments under ERA5-Land, versus `\aetgtpetmswep` under MSWEP and `\aetgtpetgpcp` under
> GPCP --- a modest, snow-concentrated forcing-dependence relevant to cold-region large-sample hydrology, and the
> basis for our choice of MSWEP as the released precipitation forcing.
(Closing "Two of these contributions reach beyond the Russian domain" — keep; the forcing-adequacy *template* is
still transferable even at the reduced magnitude.)

---

## 6. Figures to regenerate (corrected data + new captions)

| Figure | Script | Design change needed |
|---|---|---|
| `fig_precip_comparison` | `regenerate_precip_comparison_figure.py` | repoint done; diff scale now ±96 not ±295 — milder lobe |
| `fig_forcing_correlations` | `regenerate_forcing_correlations_figure.py` | repoint done; annual scatter tighter |
| `fig_water_balance` | `regenerate_water_balance_figure.py` | repoint done; ERA5 residual now near-zero — the panel no longer "dramatizes" a lobe |
| `fig_budyko` | `generate_budyko_figure.py` | repoint done; ERA5 cloud no longer sits above envelope |
| `fig_water_balance_strata` | `stratify_water_balance_violations.py` | **already regenerated** (4→7 % gradient) |

These were redesigned in the prior session to *dramatize* the (false) outlier; their designs + captions now need
to match the modest corrected story. Recommend regenerating after you approve §5 numbers.

---

## 7. Pending / Task 3 (release-blocked) items

- **Release `signatures.csv` refresh** (Task 3, needs your approval): runoff_ratio/aridity/evaporative columns were
  built on inflated ERA5 P. Corrected (in `data/CAMELS_RU/statistics/`): runoff_ratio median 0.258 → **0.331**,
  aridity 0.91, evaporative 0.67. Drives `mediandamfreerunoffratio` etc. — these macros + their verify_macros
  checks update only once the release copy is replaced.
- **Exact β** (line 92) — lock regression convention.
- **Daily-bias presentation** (line 9) — confirm per-gauge corr-table biases vs catchment-day-pair.
- **Q/P table method** (lines 55–57) — confirm switch to documented median + 5 %-trim.

---

## 8. What I need from you

1. **Framing: (A) demote (recommended) or (B) keep-but-soften?**
2. Approve the three presentation decisions (daily-bias source, Q/P-table method, Budyko index counts).
3. Then I apply macros + §5 + abstract + discussion + conclusions in one pass, regenerate the four figures,
   run `verify_macros.py`, and stage everything for your review before any push (Task 4).
