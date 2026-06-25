# ZIP Targeting DQ Playbook (home-services financing)

The core problem this skill solves: **financing credit denials**. Median income alone is a
weak filter — the real denial-drivers it misses are **renters** (don't own the roof, weaker
credit), **condos/multifamily** (the HOA owns the roof, nothing to individually finance), and
**mobile/manufactured homes** (don't qualify for roof financing, and a wrong-avatar magnet).
So those three are first-class disqualifiers alongside income.

All signals come from the US Census ACS 5-year estimates (current vintage), by ZCTA:

| Signal | ACS source | Meaning |
|---|---|---|
| Median household income | `B19013_001E` | Ability to pay / FICO proxy |
| Owner-occupancy rate | `B25003_002E / B25003_001E` | Decision-maker, owns the asset |
| Single-family share | `(B25024_002E + B25024_003E) / B25024_001E` | Detached + attached (townhomes) = an individual roof |
| Mobile-home share | `B25024_010E / B25024_001E` | Manufactured homes — unfinanceable, wrong avatar |
| Population | `B01003_001E` | Sizing reach |

> **Townhomes count as single-family** (1-unit attached) — they have individual financeable
> roofs. Only true condos/multifamily and mobile homes are penalized.

## ⛔ EXCLUDE if ANY (hard guardrails — never relaxed by leniency)
| Factor | Threshold | Config key |
|---|---|---|
| Income | `< $50,000` | `exclude_income_below` |
| Owner-occupancy | `< 45%` | `exclude_owner_below` |
| Single-family share | `< 35%` | `exclude_sf_below` |
| Mobile-home share | `> 30%` | `exclude_mobile_above` |
| No residential ACS data | — | (automatic) |

## ✅ INCLUDE if ALL (relaxable via `leniency`)
| Factor | Threshold | Config key |
|---|---|---|
| Income | `≥ $75,000` | `include_income_min` |
| Owner-occupancy | `≥ 65%` | `include_owner_min` |
| Single-family share | `≥ 55%` | `include_sf_min` |
| Mobile-home share | `≤ 15%` | `include_mobile_max` |

`leniency` (e.g. `0.10`) relaxes each Include bar by that fraction — income `× 0.9`,
owner `× 0.9`, SF `× 0.9`, mobile cap `× 1.1` — promoting near-miss ZIPs from Test → Include.
Use `holds: [...]` to force-keep specific ZIPs in Test (e.g. one sitting exactly at the
mobile-home cap).

## 🟡 TEST = everything else
Passes all hard DQs but misses an Include bar. Run at lower budget, watch denial rate,
promote winners (raise `leniency` or move them to a `holds`-free re-run).

## Adapting to other verticals
- **Non-financing lead gen** (e.g. cash service calls): loosen `exclude_income_below`, drop
  or raise the mobile-home rule.
- **Premium/roof-replacement**: raise `include_income_min` and add a home-value gate
  (`B25077_001E`) if needed.
- **Renter-OK services** (e.g. pest, cleaning): raise/remove the owner-occupancy DQ.

## Method notes
- ZIPs within a radius come from the Census Gazetteer ZCTA centroids (haversine). Overlapping
  market radii are deduped to the **nearest** market so population isn't double-counted.
- Map shapes are 2010 ZCTA cartographic boundaries (OpenDataDE) — cosmetic only; all scoring
  uses current ACS. A handful of post-2010 ZCTAs lack a shape and render as points.
- Population is total persons, not households — divide by ~2.3–2.6 for rooftop/household count.
