<div align="center">

# 📍 zip-code-research

### Turn a radius into a scored, mappable ZIP targeting list — powered by live US Census data.

A [Claude Code](https://claude.com/claude-code) skill that pulls **every ZIP within a radius of any set of cities**, joins current **Census ACS demographics**, scores each ZIP **Include / Test / Exclude** for lead-gen geo-targeting, and ships a **CSV + approved-ZIP list + an interactive map**.

[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-d97757)](https://claude.com/claude-code)
[![Python 3](https://img.shields.io/badge/Python-3.8%2B-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![Data: US Census ACS](https://img.shields.io/badge/Data-US%20Census%20ACS-1a4480)](https://www.census.gov/data/developers/data-sets/acs-5year.html)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

</div>

---

## ✨ Why this exists

For home-services lead gen (roofing, HVAC, windows, solar), the #1 money-leak is **financing credit denials** — paying for leads that can't qualify. **Median income alone is a weak filter.** The real denial-drivers it misses are:

- 🏘️ **Renters** — don't own the roof, aren't the decision-maker, weaker credit
- 🏢 **Condos / multifamily** — the HOA owns the roof; nothing to individually finance
- 🚚 **Mobile / manufactured homes** — don't qualify for roof financing, and a wrong-avatar magnet

So those three are **first-class disqualifiers** alongside income. The result is a targeting list that spends on rooftops that can actually close.

---

## 🚀 What you get

From one command:

| Output | Description |
|---|---|
| `<project>-zips.csv` | Every ZIP: market, **decision**, income, owner rate, single-family %, mobile-home %, population, reason |
| `<project>-approved-zips.txt` | Paste-ready comma list of **Include** ZIPs — drop straight into Meta / NewsBreak / Google geo |
| `<project>-data.json` | Full record for re-scoring without re-pulling the API |
| `index.html` + `zip_shapes.json` | A self-contained **Leaflet choropleth map** — deploy anywhere static |

<div align="center">

`🟢 INCLUDE` priority spend · `🟡 TEST` low budget + monitor · `🔴 EXCLUDE` credit-denial / wrong-avatar

</div>

---

## 📦 Install

This is a Claude Code skill — clone it into your skills directory:

```bash
# Project-level (this repo's skills travel with the project)
git clone https://github.com/ai-agents-for-agencies-coaches/zip-code-research \
  .claude/skills/zip-code-research

# …or user-level (available in every project)
git clone https://github.com/ai-agents-for-agencies-coaches/zip-code-research \
  ~/.claude/skills/zip-code-research
```

### 1. Get a free Census API key
Sign up (instant): **https://api.census.gov/data/key_signup.html**

> Without a key, the Census API returns an HTML *"Missing Key"* page (HTTP 200, non-JSON).

### 2. Make it available
Add it to a `.env` the script can find, or export it:

```bash
echo 'CENSUS_API_KEY=your_key_here' >> .env
# or
export CENSUS_API_KEY=your_key_here
```

That's it — **Python 3 standard library only**, no `pip install`.

---

## ⚡ Quickstart

**1. Write a config** (`market.json`):

```json
{
  "project": "roofer-ron-gulf-coast-newsbreak",
  "states": ["FL"],
  "markets": [
    { "name": "Tampa",      "lat": 27.9506, "lon": -82.4572, "radius_mi": 50 },
    { "name": "Sarasota",   "lat": 27.3364, "lon": -82.5307, "radius_mi": 50 },
    { "name": "Fort Myers", "lat": 26.6406, "lon": -81.8723, "radius_mi": 40 }
  ],
  "leniency": 0.10,
  "holds": ["33566"]
}
```

**2. Run it:**

```bash
python3 scripts/zip_research.py --config market.json --out ./output
```

**3. Or just ask Claude Code:**

> *"Run zip research for Tampa +50mi, Sarasota +50mi, Fort Myers +40mi."*

```text
[1/4] ZCTA centroids…
      273 ZIPs in radius union
[2/4] ACS 2022 demographics…
[3/4] scoring (leniency=10%)…
[4/4] building map…
      266 polygons, 7 fallback points

RESULT  Include 93 (2,168,339) · Test 101 (2,290,149) · Exclude 79 (1,405,696)
```

---

## ⚙️ Config reference

| Key | Required | Description |
|---|:---:|---|
| `project` | ✓ | Slug used to name output files |
| `markets` | ✓ | List of `{ name, lat, lon, radius_mi }` — any number of cities |
| `states` | – | State abbrevs for the map's boundary shapes (e.g. `["FL","GA"]`). Default `["FL"]` |
| `leniency` | – | `0.0`–`~0.15`. Relaxes the **Include** bars to promote near-miss ZIPs. Hard **Exclude** guardrails never relax |
| `holds` | – | ZIPs to force-keep in **Test** even if they qualify (e.g. one brushing the mobile-home cap) |
| `thresholds` | – | Override any scoring threshold (see below) |

### CLI flags
```text
--config PATH   market config JSON (required)
--out DIR       output directory (default: ./zip-research-output/<project>)
--no-map        skip building the Leaflet map
```

---

## 🎯 The scoring model

All signals come from the **US Census ACS 5-year estimates**, by ZCTA. Townhomes count as single-family (individual roof) — only true condos/multifamily and mobile homes are penalized.

### ⛔ EXCLUDE if **ANY** (hard guardrails — never relaxed)

| Factor | Threshold | `thresholds` key |
|---|---|---|
| Median income | `< $50,000` | `exclude_income_below` |
| Owner-occupancy | `< 45%` | `exclude_owner_below` |
| Single-family share | `< 35%` | `exclude_sf_below` |
| Mobile-home share | `> 30%` | `exclude_mobile_above` |

### ✅ INCLUDE if **ALL** (relaxable via `leniency`)

| Factor | Threshold | `thresholds` key |
|---|---|---|
| Median income | `≥ $75,000` | `include_income_min` |
| Owner-occupancy | `≥ 65%` | `include_owner_min` |
| Single-family share | `≥ 55%` | `include_sf_min` |
| Mobile-home share | `≤ 15%` | `include_mobile_max` |

### 🟡 TEST = everything else
Passes all hard DQs but misses an Include bar. Run at low budget, watch denial rate, promote winners.

> **Adapting to other verticals** (renter-OK services, premium replacement, cash jobs): see [`references/dq-playbook.md`](./references/dq-playbook.md).

---

## 🗺️ Deploying the map

The map is two static files — `index.html` + `zip_shapes.json` — deploy them together to any static host (Netlify, Vercel, GitHub Pages, S3). Open it to:

- See all ZIPs as a **colored choropleth** by tier
- **Toggle** Include / Test / Exclude layers
- **Click** any ZIP for income, owner-occupancy, single-family %, mobile-home %, and population

---

## 🔬 How it works

1. **Radius → ZIPs** — Census Gazetteer ZCTA centroids + haversine. Overlapping market radii are deduped to the **nearest** market (no double-counting).
2. **Demographics** — batched ACS pulls: income (`B19013`), owner-occupancy (`B25003`), units-in-structure for single-family vs condo vs mobile (`B25024`), population (`B01003`).
3. **Score** — apply the DQ model above, with optional leniency + holds.
4. **Render** — CSV, approved list, and a Leaflet map (2010 ZCTA boundary shapes; cosmetic only — all scoring uses current ACS).

---

## 📁 Repo layout

```text
zip-code-research/
├── SKILL.md                              # Claude Code skill manifest
├── scripts/zip_research.py               # the pipeline (stdlib only)
├── references/dq-playbook.md             # scoring rationale + vertical adaptations
└── examples/roofer-ron-gulf-coast.json   # working example config
```

---

<div align="center">

Built for the **[AI Agents for Agencies & Coaches](https://github.com/ai-agents-for-agencies-coaches)** community.

Data © US Census Bureau · ZIP boundary shapes © [OpenDataDE](https://github.com/OpenDataDE/State-zip-code-GeoJSON)

</div>

---

## Free training & community

This is one of several **free** skills from the AI for Agencies & SMBs community.

- 📺 **Free build-alongs & tutorials on YouTube:** https://www.youtube.com/@geopopos
- 🚀 **Full AI marketing courses, templates & live support** inside the Skool community: https://www.skool.com/ai-for-agencies-smbs-1573
