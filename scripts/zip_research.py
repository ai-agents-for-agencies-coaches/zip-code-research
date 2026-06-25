#!/usr/bin/env python3
"""
zip-code-research — radius -> Census ACS -> include/test/exclude -> CSV + map.

Pulls every ZIP (ZCTA) within a radius of one or more city centers, joins current
Census ACS demographics, scores each ZIP for lead-gen targeting (built for home-
services financing campaigns where credit denials are the pain), and emits a CSV,
an approved-ZIP list, and a self-contained Leaflet choropleth map.

Usage:
    python3 zip_research.py --config market.json [--out DIR] [--no-map]

Requires CENSUS_API_KEY in the toolkit .env (free key: https://api.census.gov/data/key_signup.html).
See references/dq-playbook.md for the scoring rationale and SKILL.md for config shape.
"""
import argparse, csv, io, json, math, os, re, ssl, sys, time, urllib.request, zipfile

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
GAZ_YEAR = 2023
ACS_YEAR = 2022
# ACS variables: income, occupied/owner units, units-in-structure (total/detached/attached/mobile), population
ACS_VARS = "B19013_001E,B25003_001E,B25003_002E,B25024_001E,B25024_002E,B25024_003E,B25024_010E,B01003_001E"

# Default scoring thresholds — tuned for roofing/home-services financing approval.
DEFAULT_THRESHOLDS = {
    "exclude_income_below": 50000,   # subprime / credit-denial risk
    "exclude_owner_below": 0.45,     # renter-dominated, not decision-makers
    "exclude_sf_below": 0.35,        # condo/multifamily — HOA owns the roof
    "exclude_mobile_above": 0.30,    # mobile homes don't qualify for financing
    "include_income_min": 75000,
    "include_owner_min": 0.65,
    "include_sf_min": 0.55,
    "include_mobile_max": 0.15,
}

# state abbrev -> OpenDataDE geojson filename slug (full state name)
STATE_NAME = {
 "AL":"alabama","AK":"alaska","AZ":"arizona","AR":"arkansas","CA":"california","CO":"colorado",
 "CT":"connecticut","DE":"delaware","FL":"florida","GA":"georgia","HI":"hawaii","ID":"idaho",
 "IL":"illinois","IN":"indiana","IA":"iowa","KS":"kansas","KY":"kentucky","LA":"louisiana",
 "ME":"maine","MD":"maryland","MA":"massachusetts","MI":"michigan","MN":"minnesota","MS":"mississippi",
 "MO":"missouri","MT":"montana","NE":"nebraska","NV":"nevada","NH":"new_hampshire","NJ":"new_jersey",
 "NM":"new_mexico","NY":"new_york","NC":"north_carolina","ND":"north_dakota","OH":"ohio","OK":"oklahoma",
 "OR":"oregon","PA":"pennsylvania","RI":"rhode_island","SC":"south_carolina","SD":"south_dakota",
 "TN":"tennessee","TX":"texas","UT":"utah","VT":"vermont","VA":"virginia","WA":"washington",
 "WV":"west_virginia","WI":"wisconsin","WY":"wyoming","DC":"district_of_columbia",
}


def load_key():
    for p in [os.path.expanduser("~/claude_work/home-services-ad-toolkit/.env"), ".env"]:
        if os.path.exists(p):
            for line in open(p):
                m = re.match(r"CENSUS_API_KEY=(\S+)", line.strip())
                if m:
                    return m.group(1)
    if os.environ.get("CENSUS_API_KEY"):
        return os.environ["CENSUS_API_KEY"]
    sys.exit("ERROR: CENSUS_API_KEY not found in .env or environment. "
             "Get a free key at https://api.census.gov/data/key_signup.html")


def get_json(url, timeout=120):
    return json.loads(urllib.request.urlopen(url, context=CTX, timeout=timeout).read())


def haversine(a, b, c, d):
    R = 3958.8
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = math.radians(c - a), math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.asin(math.sqrt(x))


def get_centroids():
    url = (f"https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
           f"{GAZ_YEAR}_Gazetteer/{GAZ_YEAR}_Gaz_zcta_national.zip")
    z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url, context=CTX, timeout=90).read()))
    raw = z.read(z.namelist()[0]).decode("latin-1").splitlines()
    cent = {}
    for line in raw[1:]:
        p = line.split("\t")
        if len(p) < 7:
            continue
        try:
            cent[p[0].strip()] = (float(p[5].strip()), float(p[6].strip()))
        except ValueError:
            pass
    return cent


def assign_markets(cent, markets):
    """Each ZIP -> nearest qualifying market (dedupes overlapping radii)."""
    out = {}
    for z5, (la, lo) in cent.items():
        best = None
        for m in markets:
            d = haversine(m["lat"], m["lon"], la, lo)
            if d <= m["radius_mi"] and (best is None or d < best[1]):
                best = (m["name"], d)
        if best:
            out[z5] = {"market": best[0], "dist_mi": round(best[1], 1), "lat": la, "lon": lo}
    return out


def fetch_acs(zips, key):
    data = {}
    for i in range(0, len(zips), 45):
        q = ",".join(zips[i:i + 45])
        url = (f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5?get={ACS_VARS}"
               f"&for=zip%20code%20tabulation%20area:{q}&key={key}")
        arr = get_json(url, timeout=90)
        h = arr[0]
        for row in arr[1:]:
            d = dict(zip(h, row))
            z5 = d["zip code tabulation area"]

            def g(k):
                v = d.get(k)
                try:
                    v = int(v); return v if v >= 0 else None
                except (TypeError, ValueError):
                    return None
            occ, own = g("B25003_001E"), g("B25003_002E")
            tot, det, att, mob = g("B25024_001E"), g("B25024_002E"), g("B25024_003E"), g("B25024_010E")
            data[z5] = {
                "income": g("B19013_001E"),
                "own_rate": round(own / occ, 3) if occ and own is not None and occ > 0 else None,
                "sf_share": round(((det or 0) + (att or 0)) / tot, 3) if tot and tot > 0 else None,
                "mobile_share": round(mob / tot, 3) if tot and mob is not None and tot > 0 else None,
                "home_value": None,
                "pop": g("B01003_001E") or 0,
                "occ_homes": occ,
            }
        time.sleep(0.15)
    return data


def classify(d, t, leniency, holds):
    z5 = d.get("_zip")
    inc, own, sf, mob = d.get("income"), d.get("own_rate"), d.get("sf_share"), d.get("mobile_share")
    if d.get("occ_homes") in (None, 0) and inc is None:
        return "EXCLUDE", "non-residential / no ACS data"
    if mob is not None and mob > t["exclude_mobile_above"]:
        return "EXCLUDE", f"{mob*100:.0f}% mobile homes — financing-denial / wrong-avatar magnet"
    if inc is not None and inc < t["exclude_income_below"]:
        return "EXCLUDE", f"income ${inc:,} — subprime/credit-denial risk"
    if own is not None and own < t["exclude_owner_below"]:
        return "EXCLUDE", f"renter-dominated ({own*100:.0f}% owner) — not roof decision-makers"
    if sf is not None and sf < t["exclude_sf_below"]:
        return "EXCLUDE", f"condo/multifamily ({sf*100:.0f}% SF) — HOA owns roof"
    # include thresholds, optionally relaxed by `leniency`
    li = t["include_income_min"] * (1 - leniency)
    lo = t["include_owner_min"] * (1 - leniency)
    ls = t["include_sf_min"] * (1 - leniency)
    lm = t["include_mobile_max"] * (1 + leniency)
    if (inc is not None and inc >= li and (own or 0) >= lo and (sf or 0) >= ls
            and (mob or 0) <= lm):
        if z5 in holds:
            return "TEST", f"held in test (config holds): ${inc:,}, {(mob or 0)*100:.0f}% mobile"
        tag = "promoted (leniency)" if inc < t["include_income_min"] or (own or 0) < t["include_owner_min"] \
            or (sf or 0) < t["include_sf_min"] or (mob or 0) > t["include_mobile_max"] else "strong"
        return "INCLUDE", f"{tag}: ${inc:,}, {(own or 0)*100:.0f}% own, {(sf or 0)*100:.0f}% SF, {(mob or 0)*100:.0f}% mobile"
    incs = f"${inc:,}" if inc is not None else "income n/a"
    return "TEST", incs + (f", {own*100:.0f}% own" if own else "") + (f", {mob*100:.0f}% mobile" if mob else "")


def fetch_shapes(states):
    shapes = {}
    for st in states:
        slug = STATE_NAME.get(st.upper())
        if not slug:
            continue
        url = (f"https://raw.githubusercontent.com/OpenDataDE/State-zip-code-GeoJSON/"
               f"master/{st.lower()}_{slug}_zip_codes_geo.min.json")
        try:
            gj = get_json(url, timeout=120)
            for f in gj["features"]:
                shapes[f["properties"]["ZCTA5CE10"]] = f["geometry"]
        except Exception as e:
            print(f"  warn: no shapes for {st}: {e}")
    return shapes


def round_geom(g):
    def r(c):
        if isinstance(c, list):
            if c and isinstance(c[0], (int, float)):
                return [round(c[0], 5), round(c[1], 5)]
            return [r(x) for x in c]
        return c
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


MAP_TMPL = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>__TITLE__</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#map{height:100%;margin:0}body{font-family:system-ui,Arial}
.legend{background:#fff;padding:10px 12px;border-radius:8px;box-shadow:0 1px 6px rgba(0,0,0,.3);font-size:13px;line-height:1.7}
.legend b{font-size:14px}.dot{display:inline-block;width:13px;height:13px;border-radius:3px;margin-right:6px;vertical-align:middle}
.leaflet-popup-content{font-size:13px;line-height:1.5}
#load{position:absolute;top:10px;left:50%;transform:translateX(-50%);z-index:1000;background:#fff;padding:6px 14px;border-radius:6px;box-shadow:0 1px 6px rgba(0,0,0,.3);font-size:13px}
.ctl{background:#fff;padding:6px 8px;border-radius:6px;box-shadow:0 1px 6px rgba(0,0,0,.3);font-size:12px}.ctl label{display:block;cursor:pointer}</style>
</head><body><div id="map"></div><div id="load">Loading ZIP shapes…</div><script>
var COL={INCLUDE:'#16a34a',TEST:'#f59e0b',EXCLUDE:'#dc2626'};var cities=__CITIES__,mpts=__MPTS__,counts=__COUNTS__;
var map=L.map('map').setView(__CENTER__,__ZOOM__);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{attribution:'© OpenStreetMap, © CARTO',maxZoom:19}).addTo(map);
for(var c in cities){var v=cities[c];L.circle([v[0],v[1]],{radius:v[2]*1609.34,color:'#1e293b',weight:1.5,fill:false,dashArray:'6,7'}).addTo(map).bindTooltip(c+' ('+v[2]+'mi)');}
function f(x,p){return x==null?'n/a':(p?(x*100).toFixed(0)+'%':'$'+x.toLocaleString());}
function pop(p){return '<b>'+p.z+'</b> · '+p.m+'<br><b style="color:'+COL[p.dec]+'">'+p.dec+'</b><br>Income: '+f(p.inc)+'<br>Owner-occ: '+f(p.own,1)+'<br>Single-family: '+f(p.sf,1)+'<br>Mobile homes: '+f(p.mob,1)+'<br>Population: '+(p.pop||0).toLocaleString();}
var layers={INCLUDE:L.layerGroup().addTo(map),TEST:L.layerGroup().addTo(map),EXCLUDE:L.layerGroup().addTo(map)};
function style(ft){return {color:'#fff',weight:1,fillColor:COL[ft.properties.dec],fillOpacity:.55};}
fetch('./zip_shapes.json').then(r=>r.json()).then(fc=>{L.geoJSON(fc,{style:style,onEachFeature:function(ft,ly){ly.bindPopup(pop(ft.properties));
ly.on('mouseover',function(){this.setStyle({weight:3,fillOpacity:.75});});ly.on('mouseout',function(){this.setStyle(style(ft));});layers[ft.properties.dec].addLayer(ly);}});
mpts.forEach(function(p){if(p.lat)L.circleMarker([p.lat,p.lon],{radius:7,color:'#fff',weight:1,fillColor:COL[p.dec],fillOpacity:.85}).bindPopup(pop(p)+'<br><i>(point — no boundary shape)</i>').addTo(layers[p.dec]);});
document.getElementById('load').remove();}).catch(e=>{document.getElementById('load').innerText='Error loading shapes: '+e;});
var lg=L.control({position:'bottomright'});lg.onAdd=function(){var d=L.DomUtil.create('div','legend');
d.innerHTML='<b>__TITLE__</b><br><span class="dot" style="background:#16a34a"></span>Include — '+counts.INCLUDE+'<br><span class="dot" style="background:#f59e0b"></span>Test — '+counts.TEST+'<br><span class="dot" style="background:#dc2626"></span>Exclude — '+counts.EXCLUDE+'<br><span style="font-size:11px;color:#555">dashed ring = market radius · hover a ZIP for detail</span>';return d;};lg.addTo(map);
var tc=L.control({position:'topright'});tc.onAdd=function(){var d=L.DomUtil.create('div','ctl');d.innerHTML='<b>Toggle tiers</b>';
['INCLUDE','TEST','EXCLUDE'].forEach(function(k){d.innerHTML+='<label><input type="checkbox" checked id="t_'+k+'"> '+k+'</label>';});L.DomEvent.disableClickPropagation(d);
setTimeout(function(){['INCLUDE','TEST','EXCLUDE'].forEach(function(k){document.getElementById('t_'+k).onchange=function(){this.checked?map.addLayer(layers[k]):map.removeLayer(layers[k]);};});},0);return d;};tc.addTo(map);
</script></body></html>"""


def build_map(rec, markets, states, title, outdir):
    shapes = fetch_shapes(states)
    feats, missing = [], []
    for z5, d in rec.items():
        props = {"z": z5, "m": d["market"], "dec": d["decision"], "inc": d.get("income"),
                 "own": d.get("own_rate"), "sf": d.get("sf_share"), "mob": d.get("mobile_share"), "pop": d.get("pop", 0)}
        g = shapes.get(z5)
        if g:
            feats.append({"type": "Feature", "geometry": round_geom(g), "properties": props})
        else:
            missing.append({**props, "lat": d.get("lat"), "lon": d.get("lon")})
    json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(outdir, "zip_shapes.json"), "w"))
    counts = {c: sum(1 for d in rec.values() if d["decision"] == c) for c in ("INCLUDE", "TEST", "EXCLUDE")}
    cities = {m["name"]: [m["lat"], m["lon"], m["radius_mi"]] for m in markets}
    clat = sum(m["lat"] for m in markets) / len(markets)
    clon = sum(m["lon"] for m in markets) / len(markets)
    html = (MAP_TMPL.replace("__TITLE__", title).replace("__CITIES__", json.dumps(cities))
            .replace("__MPTS__", json.dumps(missing)).replace("__COUNTS__", json.dumps(counts))
            .replace("__CENTER__", json.dumps([round(clat, 3), round(clon, 3)])).replace("__ZOOM__", "8"))
    open(os.path.join(outdir, "index.html"), "w").write(html)
    return len(feats), len(missing)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="market config JSON")
    ap.add_argument("--out", default=None, help="output dir (default: ./zip-research-output/<project>)")
    ap.add_argument("--no-map", action="store_true", help="skip building the Leaflet map")
    args = ap.parse_args()

    cfg = json.load(open(args.config))
    project = cfg.get("project", "zip-research")
    markets = cfg["markets"]
    states = cfg.get("states", ["FL"])
    thresholds = {**DEFAULT_THRESHOLDS, **cfg.get("thresholds", {})}
    leniency = float(cfg.get("leniency", 0.0))
    holds = set(cfg.get("holds", []))
    outdir = args.out or os.path.join("zip-research-output", project)
    os.makedirs(outdir, exist_ok=True)

    key = load_key()
    print(f"[1/4] ZCTA centroids…"); cent = get_centroids()
    rec = assign_markets(cent, markets)
    print(f"      {len(rec)} ZIPs in radius union")
    print(f"[2/4] ACS {ACS_YEAR} demographics…")
    acs = fetch_acs(list(rec.keys()), key)
    for z5 in rec:
        rec[z5].update(acs.get(z5, {})); rec[z5]["_zip"] = z5
    print(f"[3/4] scoring (leniency={leniency:.0%})…")
    for z5, d in rec.items():
        c, why = classify(d, thresholds, leniency, holds); d["decision"], d["reason"] = c, why
    counts = {c: sum(1 for d in rec.values() if d["decision"] == c) for c in ("INCLUDE", "TEST", "EXCLUDE")}
    pops = {c: sum(d.get("pop", 0) for d in rec.values() if d["decision"] == c) for c in counts}

    # CSV
    csv_path = os.path.join(outdir, f"{project}-zips.csv")
    rank = {"INCLUDE": 0, "TEST": 1, "EXCLUDE": 2}
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["zip", "market", "decision", "median_income", "owner_rate", "sf_share",
                    "mobile_share", "population", "dist_mi", "reason"])
        for z5, d in sorted(rec.items(), key=lambda t: (rank[t[1]["decision"]], -(t[1].get("income") or 0))):
            w.writerow([z5, d["market"], d["decision"], d.get("income") or "", d.get("own_rate") or "",
                        d.get("sf_share") or "", d.get("mobile_share") or "", d.get("pop", 0),
                        d.get("dist_mi"), d["reason"]])
    # approved list
    inc = sorted(z for z, d in rec.items() if d["decision"] == "INCLUDE")
    with open(os.path.join(outdir, f"{project}-approved-zips.txt"), "w") as f:
        f.write(f"APPROVED (INCLUDE) ZIPs — {len(inc)}\n\n" + ", ".join(inc) + "\n")
    json.dump(rec, open(os.path.join(outdir, f"{project}-data.json"), "w"))

    if not args.no_map:
        print(f"[4/4] building map…")
        np_, nm = build_map(rec, markets, states, project, outdir)
        print(f"      {np_} polygons, {nm} fallback points")
    else:
        print("[4/4] map skipped")

    print(f"\nRESULT  Include {counts['INCLUDE']} ({pops['INCLUDE']:,}) · "
          f"Test {counts['TEST']} ({pops['TEST']:,}) · Exclude {counts['EXCLUDE']} ({pops['EXCLUDE']:,})")
    print(f"Output → {outdir}/")
    print(f"  {project}-zips.csv · {project}-approved-zips.txt · {project}-data.json"
          + ("" if args.no_map else " · index.html + zip_shapes.json (deploy these two to Netlify)"))


if __name__ == "__main__":
    main()
