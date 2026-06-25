---
name: zip-code-research
description: Pull every ZIP code within a radius of one or more cities, join current US Census ACS demographics (income, owner-occupancy, single-family vs condo, mobile-home share, population), and score each ZIP Include / Test / Exclude for lead-gen geo-targeting — then output a CSV, an approved-ZIP list, and an interactive choropleth map. Built for home-services financing campaigns (roofing, HVAC, windows, solar) where the core pain is credit denials, so the default disqualifiers screen out subprime, renter-dominated, condo, and mobile-home ZIPs that drive denials and wasted spend. Use whenever the user wants a ZIP list for a market, asks "which ZIPs should we target/exclude", wants to group ZIPs by income/demographics, build a targeting map for Meta/NewsBreak/Google geo, or research a metro's ZIP-level demographics. Triggers: "pull a zip list", "zips around <city> + <N> miles", "group zips by income", "which zips to include/exclude", "zip targeting", "approved zip list", "map these zips", "census data for these zips".
---

# zip-code-research

Turns a set of **city centers + radii** into a scored, mappable ZIP targeting list using
live Census data. One command produces a CSV, an approved-ZIP paste list, and a
self-contained Leaflet map you can deploy to Netlify for remote viewing.

## When to use
- "Pull all ZIPs within 50mi of Tampa / Sarasota / Ft Myers and group by income"
- "Which ZIPs should we include vs exclude for a roofing campaign?"
- "Map these ZIPs" / "give me the approved ZIP list" / "build a geo-targeting list"
- Any market where credit denials, renters, condos, or mobile homes pollute lead quality.

## Prerequisites
- **`CENSUS_API_KEY`** in `home-services-ad-toolkit/.env` (free, instant:
  https://api.census.gov/data/key_signup.html). Without it the Census API returns an
  HTML "Missing Key" page (HTTP 200, non-JSON). See memory `reference-census-api-key`.
- Python 3 stdlib only — no extra installs.

## How to run
1. **Geocode the city centers.** The config needs `lat`/`lon` for each market. If the
   user gives city names, resolve approximate centroids (well-known coords are fine —
   these are radius anchors, not precise points).
2. **Write a config JSON** (see `examples/roofer-ron-gulf-coast.json`):
   ```json
   {
     "project": "roofer-ron-gulf-coast-newsbreak",
     "states": ["FL"],
     "markets": [
       {"name": "Tampa",      "lat": 27.9506, "lon": -82.4572, "radius_mi": 50},
       {"name": "Sarasota",   "lat": 27.3364, "lon": -82.5307, "radius_mi": 50},
       {"name": "Fort Myers", "lat": 26.6406, "lon": -81.8723, "radius_mi": 40}
     ],
     "leniency": 0.10,
     "holds": ["33566"]
   }
   ```
   - `states` — which state ZCTA boundary files to load for the map (OpenDataDE). Multi-state OK.
   - `leniency` — 0.0–~0.15. Relaxes the **Include** thresholds by that fraction to promote
     near-miss ZIPs from Test → Include. Hard Exclude guardrails never relax.
   - `holds` — ZIPs to force-keep in Test even if they qualify (e.g. one brushing the mobile-home cap).
   - `thresholds` — optional object to override any DQ value (see `references/dq-playbook.md`).
3. **Run:**
   ```bash
   python3 .claude/skills/zip-code-research/scripts/zip_research.py \
     --config <config.json> [--out <dir>] [--no-map]
   ```
   Default output dir: `zip-research-output/<project>/`.

## Outputs
- `<project>-zips.csv` — every ZIP: market, decision, income, owner rate, SF share, mobile share, population, reason.
- `<project>-approved-zips.txt` — paste-ready comma list of Include ZIPs.
- `<project>-data.json` — full record (re-use for re-scoring without re-pulling).
- `index.html` + `zip_shapes.json` — the map. Deploy **both** to one Netlify site.

## Deploying the map (so it's viewable off-box / over SSH)
1. `/log-change` first (surface `netlify`, action `deploy`) — the changelog gate requires it.
2. Create a Netlify project on the **Volume Up Agency** team (slug `geopopos`) via the
   Netlify MCP, then deploy the output dir. Name the site descriptively
   (e.g. `roofer-ron-gulf-coast-newsbreak-approved-zips`).
3. Verify the live URL serves before sharing (sandbox `fetch`, retry for CDN propagation).

## Scoring model
The Include/Test/Exclude logic and *why each factor predicts credit denials* is documented
in `references/dq-playbook.md`. Income alone is a weak filter — the denial-killers it misses
are **renters, condos, and mobile homes**, which is why those are first-class disqualifiers.
