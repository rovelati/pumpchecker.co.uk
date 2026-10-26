#!/usr/bin/env python3
"""
build-uk-database.py — PumpChecker.co.uk
Ingests official UK CMA Open Fuel Data, groups by settlement/town/city/county,
and outputs high-performance static JSON datasets for 20,000+ programmatic pages.
"""

import urllib.request
import csv
import io
import json
import os
import re

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
SRC_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'src', 'data')
PUBLIC_DIR = os.path.join(os.path.dirname(__file__), '..', 'public')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SRC_DATA_DIR, exist_ok=True)
os.makedirs(PUBLIC_DIR, exist_ok=True)

CMA_CSV_URL = 'https://raw.githubusercontent.com/matthewgall/fuelfinder-archive/main/data.csv'
GB_CITIES_URL = 'https://raw.githubusercontent.com/lutangar/cities.json/master/cities.json'

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[\'\"]', '', text)
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

def clean_city_name(name):
    name = re.sub(r'\s*/\s*', ' - ', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip().title()

def main():
    print("[1/5] Downloading CMA Open Fuel Data...")
    req = urllib.request.Request(CMA_CSV_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=20) as resp:
        csv_text = resp.read().decode('utf-8')

    with open(os.path.join(DATA_DIR, 'cma_fuel_data.csv'), 'w', encoding='utf-8') as f:
        f.write(csv_text)

    reader = csv.DictReader(io.StringIO(csv_text))
    stations = []
    cma_city_map = {}

    for row in reader:
        name = row.get('forecourts.trading_name', '').strip()
        brand = row.get('forecourts.brand_name', '').strip() or 'Independent'
        city = clean_city_name(row.get('forecourts.location.city', ''))
        county = row.get('forecourts.location.county', '').strip().title()
        postcode = row.get('forecourts.location.postcode', '').strip().upper()
        addr = row.get('forecourts.location.address_line_1', '').strip()
        lat_str = row.get('forecourts.location.latitude', '').strip()
        lng_str = row.get('forecourts.location.longitude', '').strip()

        if not lat_str or not lng_str:
            continue
        try:
            lat = round(float(lat_str), 5)
            lng = round(float(lng_str), 5)
        except ValueError:
            continue

        e10 = row.get('forecourts.fuel_price.E10', '').strip()
        e5 = row.get('forecourts.fuel_price.E5', '').strip()
        diesel = row.get('forecourts.fuel_price.B7S', '').strip()
        b7p = row.get('forecourts.fuel_price.B7P', '').strip()

        e10_val = round(float(e10), 1) if e10 else None
        e5_val = round(float(e5), 1) if e5 else None
        diesel_val = round(float(diesel), 1) if diesel else None
        b7p_val = round(float(b7p), 1) if b7p else None

        st = {
            'id': row.get('forecourts.node_id', ''),
            'name': name,
            'brand': brand,
            'city': city or county or 'UK',
            'county': county,
            'postcode': postcode,
            'address': addr,
            'lat': lat,
            'lng': lng,
            'e10': e10_val,
            'e5': e5_val,
            'diesel': diesel_val,
            'b7p': b7p_val,
            'supermarket': row.get('forecourts.is_supermarket_service_station', '').lower() == 'true',
            'motorway': row.get('forecourts.is_motorway_service_station', '').lower() == 'true'
        }
        stations.append(st)

        c_name = city or county
        if c_name and len(c_name) > 1:
            slug = slugify(c_name)
            if slug not in cma_city_map:
                cma_city_map[slug] = {
                    'name': c_name,
                    'slug': slug,
                    'county': county or '',
                    'lats': [],
                    'lngs': [],
                    'station_count': 0,
                    'min_e10': 999.0,
                    'min_diesel': 999.0
                }
            entry = cma_city_map[slug]
            entry['lats'].append(lat)
            entry['lngs'].append(lng)
            entry['station_count'] += 1
            if e10_val and e10_val < entry['min_e10']:
                entry['min_e10'] = e10_val
            if diesel_val and diesel_val < entry['min_diesel']:
                entry['min_diesel'] = diesel_val

    print(f"Parsed {len(stations)} forecourts across {len(cma_city_map)} primary cities from CMA.")

    print("[2/5] Downloading UK settlements database to expand town directory...")
    req2 = urllib.request.Request(GB_CITIES_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req2, timeout=20) as resp2:
        all_cities = json.loads(resp2.read().decode('utf-8'))

    gb_cities = [c for c in all_cities if c.get('country') == 'GB']
    print(f"Found {len(gb_cities)} GB places in reference database.")

    # Combine CMA cities with GB places
    merged_cities = {}

    # Priority 1: Cities with active stations from CMA
    for slug, c in cma_city_map.items():
        avg_lat = round(sum(c['lats']) / len(c['lats']), 4)
        avg_lng = round(sum(c['lngs']) / len(c['lngs']), 4)
        merged_cities[slug] = {
            'name': c['name'],
            'slug': slug,
            'county': c['county'],
            'lat': avg_lat,
            'lng': avg_lng,
            'stationCount': c['station_count'],
            'cheapestE10': c['min_e10'] if c['min_e10'] < 900 else None,
            'cheapestDiesel': c['min_diesel'] if c['min_diesel'] < 900 else None
        }

    # Priority 2: Add significant UK settlements
    for p in gb_cities:
        p_name = clean_city_name(p['name'])
        p_slug = slugify(p_name)
        if not p_slug or len(p_slug) < 2 or p_slug.isdigit():
            continue
        if p_slug not in merged_cities:
            try:
                lat = round(float(p['lat']), 4)
                lng = round(float(p['lng']), 4)
            except (ValueError, KeyError):
                continue
            merged_cities[p_slug] = {
                'name': p_name,
                'slug': p_slug,
                'county': p.get('subcountry', ''),
                'lat': lat,
                'lng': lng,
                'stationCount': 0,
                'cheapestE10': None,
                'cheapestDiesel': None
            }

    # Sort cities: primary forecourt count descending, then alphabetically
    sorted_cities = sorted(
        merged_cities.values(),
        key=lambda x: (x['stationCount'], -len(x['name'])),
        reverse=True
    )

    # Pick exactly top 3,000 cities & towns for programmatic index
    final_cities = sorted_cities[:3000]
    print(f"Selected {len(final_cities)} UK towns & cities for directory.")

    # Top Brands in the UK (with SEMrush search volumes)
    uk_brands = [
        {
            "name": "Tesco",
            "slug": "tesco",
            "type": "Supermarket",
            "tagline": "Tesco Fuel Prices & Forecourts",
            "description": "Find the cheapest Tesco petrol filling stations across the UK. Compare live Clubcard petrol and diesel prices at Tesco superstores and extra forecourts.",
            "searchVolume": "8.1K",
            "kd": 19
        },
        {
            "name": "Asda",
            "slug": "asda",
            "type": "Supermarket",
            "tagline": "Asda Fuel Cost & Petrol Stations",
            "description": "Compare current Asda fuel prices for Unleaded E10 and Diesel B7 across the UK. Find your nearest low-cost Asda supermarket forecourt.",
            "searchVolume": "8.1K",
            "kd": 16
        },
        {
            "name": "Morrisons",
            "slug": "morrisons",
            "type": "Supermarket",
            "tagline": "Morrisons Petrol Prices Today",
            "description": "Current petrol and diesel prices at Morrisons filling stations. Compare live forecourt rates near you.",
            "searchVolume": "22.2K",
            "kd": 25
        },
        {
            "name": "Sainsbury's",
            "slug": "sainsburys",
            "type": "Supermarket",
            "tagline": "Sainsbury's Petrol Station Prices",
            "description": "Compare live fuel prices at Sainsbury's forecourts. Find cheap Unleaded and Diesel at your local supermarket filling station.",
            "searchVolume": "6.6K",
            "kd": 21
        },
        {
            "name": "Costco",
            "slug": "costco",
            "type": "Wholesale / Supermarket",
            "tagline": "Costco Fuel Price UK",
            "description": "Lowest wholesale fuel rates at Costco UK forecourts. Check live Kirkland Signature petrol and diesel prices for members.",
            "searchVolume": "22.2K",
            "kd": 23
        },
        {
            "name": "BP",
            "slug": "bp",
            "type": "Major Retailer",
            "tagline": "BP Garage Near Me & Fuel Prices",
            "description": "Compare fuel prices at BP service stations across the UK. Check live prices for BP Ultimate Unleaded, Regular E10, and Diesel.",
            "searchVolume": "6.6K",
            "kd": 19
        },
        {
            "name": "Shell",
            "slug": "shell",
            "type": "Major Retailer",
            "tagline": "Shell Petrol Station Prices",
            "description": "Find Shell petrol stations near you with live prices for Shell V-Power, FuelSave Unleaded, and Diesel.",
            "searchVolume": "18.1K",
            "kd": 35
        },
        {
            "name": "Esso",
            "slug": "esso",
            "type": "Major Retailer",
            "tagline": "Esso Petrol Stations & Fuel Cost",
            "description": "Check current prices at Esso service stations across England, Scotland, and Wales. Real-time Unleaded and Synergy Diesel rates.",
            "searchVolume": "22.2K",
            "kd": 62
        }
    ]

    # Generate Brand x City combinations (8 brands x top 850 cities = 6,800 pages)
    # Keeping total site under Cloudflare Pages 20,000 file hard limit (~19,100 files total)
    brand_city_pairs = []
    top_cities_for_brand = final_cities[:850]
    for b in uk_brands:
        for c in top_cities_for_brand:
            brand_city_pairs.append({
                "brandSlug": b['slug'],
                "brandName": b['name'],
                "citySlug": c['slug'],
                "cityName": c['name'],
                "county": c['county'],
                "lat": c['lat'],
                "lng": c['lng']
            })

    print(f"Generated {len(brand_city_pairs)} Brand x City programmatic targets.")

    # Counties
    counties_set = set()
    for c in final_cities:
        co = c.get('county')
        if co and len(co) > 2:
            counties_set.add(co)

    uk_counties = []
    for co in sorted(list(counties_set)):
        uk_counties.append({
            "name": co,
            "slug": slugify(co)
        })

    print(f"Extracted {len(uk_counties)} UK counties.")

    # Write JSON files to src/data and public
    print("[3/5] Saving datasets to src/data/...")
    with open(os.path.join(SRC_DATA_DIR, 'uk_cities.json'), 'w', encoding='utf-8') as f:
        json.dump(final_cities, f, indent=2, ensure_ascii=False)

    with open(os.path.join(SRC_DATA_DIR, 'uk_brands.json'), 'w', encoding='utf-8') as f:
        json.dump(uk_brands, f, indent=2, ensure_ascii=False)

    with open(os.path.join(SRC_DATA_DIR, 'uk_counties.json'), 'w', encoding='utf-8') as f:
        json.dump(uk_counties, f, indent=2, ensure_ascii=False)

    with open(os.path.join(SRC_DATA_DIR, 'brand_cities.json'), 'w', encoding='utf-8') as f:
        json.dump(brand_city_pairs, f, ensure_ascii=False)

    # Save compact stations file for client-side search / map
    print("[4/5] Saving forecourts index to public/cma_stations_index.json...")
    compact_stations = []
    for s in stations:
        compact_stations.append({
            "i": s['id'],
            "n": s['name'],
            "b": s['brand'],
            "c": s['city'],
            "p": s['postcode'],
            "a": s['address'],
            "lt": s['lat'],
            "lg": s['lng'],
            "e10": s['e10'],
            "e5": s['e5'],
            "d": s['diesel'],
            "sm": 1 if s['supermarket'] else 0,
            "mw": 1 if s['motorway'] else 0
        })

    with open(os.path.join(PUBLIC_DIR, 'cma_stations_index.json'), 'w', encoding='utf-8') as f:
        json.dump(compact_stations, f, ensure_ascii=False)

    print("[5/5] UK Open Fuel Data Engine build complete!")
    print(f"Total programmatic pages planned:")
    print(f" - City overview pages: {len(final_cities)}")
    print(f" - City diesel pages:   {len(final_cities)}")
    print(f" - City unleaded E10:   {len(final_cities)}")
    print(f" - City super E5:       {len(final_cities)}")
    print(f" - Brand x City pages:  {len(brand_city_pairs)}")
    print(f" - County hubs:         {len(uk_counties) * 3}")
    print(f" - Brand hubs:          {len(uk_brands)}")
    print(f" - Pillar & legal:      15")
    total_pages = (len(final_cities) * 4) + len(brand_city_pairs) + (len(uk_counties) * 3) + len(uk_brands) + 15
    print(f" -> TOTAL STATIC PAGES: {total_pages:,}")

if __name__ == '__main__':
    main()
