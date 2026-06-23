import os
import math
import urllib.request
import urllib.parse
import json
import smartsheet
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

# Initialize Secrets [cite: 2026-05-22]
access_token = os.environ.get('SMARTSHEET_TOKEN')
sheet_id = os.environ.get('SHEET_ID')

if not access_token or not sheet_id:
    print("Error: Missing Smartsheet secrets.")
    exit(1)

smartsheet_client = smartsheet.Smartsheet(access_token)

# Hardcoded Staging Coordinates Map
STAGING_COORDS = {
    "aberdeen": (45.4623, -98.4528),
    "cedar falls": (42.4938, -92.4497),
    "fort dodge": (42.5028, -94.1625),
    "johnston": (41.6669, -93.7020),
    "mason city": (43.1417, -93.2646),
    "mitchell": (43.7198, -98.0163),
    "pella": (41.4055, -92.9304),
    "sioux city": (42.4402, -96.3533),
    "yankton": (42.8942, -97.3980)
}

# Column IDs
COL_STAGING_LOC = 2443388002799492
COL_ADDRESS = 4272975351418756
COL_CITY = 8776574978789252
COL_STATE = 191588189114244
COL_ZIP = 4695187816484740
COL_LOC_COORDS = 985976515366788
COL_DISTANCE = 2182270936190852

def haversine_distance(coord1, coord2):
    """Calculates straight-line miles between coordinate pairs."""
    if not coord1 or not coord2 or None in coord1 or None in coord2:
        return None
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    R = 3958.8
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

def get_staging_coords(location_string):
    if not location_string:
        return None
    normalized = location_string.lower().replace("mobiles", "").strip()
    for key, coords in STAGING_COORDS.items():
        if key in normalized:
            return coords
    return None

import time

def free_search_geocode(addr_val, city_val, state_val, zip_val):
    """Queries a structured open public search parser using explicit address parameters to prevent wild misses."""
    try:
        # Enforce rate limit protection delay
        time.sleep(3.0)
        
        # Clean church/school text blocks if they are mashed against numbers
        clean_street = ""
        raw_street = str(addr_val)
        for i in range(len(raw_street)):
            clean_street += raw_street[i]
            if i < len(raw_street) - 1:
                if raw_street[i].isalpha() and raw_street[i+1].isdigit():
                    clean_street += " "

        params = {
            'street': clean_street.strip(),
            'city': str(city_val).strip(),
            'state': str(state_val).strip(),
            'postalcode': str(zip_val).strip(),
            'format': 'json',
            'limit': '1'
        }
        
        encoded_params = urllib.parse.urlencode(params)
        url = f"https://nominatim.openstreetmap.org/search?{encoded_params}"
        
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'lifeserve_outlier_structured_v3'}
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            if data and isinstance(data, list) and len(data) > 0:
                return (float(data["lat"]), float(data["lon"]))
    except Exception as e:
        print(f"  Structured search lookup encountered an issue: {e}")
    return None

def main():
    print("Starting outlier detection and Google Search auto-correction script...")
    sheet = smartsheet_client.Sheets.get_sheet(int(sheet_id))
    
    rows_to_update = []
    
    for row in sheet.rows:
        cells = {cell.column_id: cell for cell in row.cells}
        
        dist_cell = cells.get(COL_DISTANCE)
        if not dist_cell or dist_cell.value is None:
            continue
            
        try:
            distance_val = float(dist_cell.value)
        except ValueError:
            continue
            
        # Target rows exceeding 200 miles
        if distance_val > 200.0:
            staging_val = cells[COL_STAGING_LOC].value
            addr_val = cells[COL_ADDRESS].value
            city_val = cells[COL_CITY].value
            state_val = cells[COL_STATE].value
            
            # Safely extract ZIP
            zip_val = ""
            if COL_ZIP in cells and cells[COL_ZIP].value:
                raw_zip_string = str(cells[COL_ZIP].value)
                split_zip_components = raw_zip_string.split('.')
                for item in split_zip_components:
                    zip_val = item.strip()
                    break
            
            full_address = f"{addr_val}, {city_val}, {state_val} {zip_val}".strip()
            print(f"\n[Row ID {row.id}] Outlier detected: {distance_val} miles.")
            print(f"  Running Search fallback for: '{full_address}'")
            
            s_coords = get_staging_coords(staging_val)
            l_coords = free_search_geocode(full_address)
            
            if l_coords:
                l_coords_str = f"{l_coords}, {l_coords}"
                new_miles = haversine_distance(s_coords, l_coords)
                
                # CRITICAL RUNTIME VERIFICATION [cite: 2026-05-22]
                # If Google somehow still yields a location over 200 miles away, halt instantly
                if new_miles is not None and new_miles > 200.0:
                    print(f"  WARNING: Google search fallback still resulted in a distance over 200 miles: {new_miles} mi.")
                    print(f"  Halting runtime to inspect. Check 'l_coords' and 'full_address'.")
                    import pdb; pdb.set_trace()
                
                # Build cell modifications
                updated_cells = [
                    smartsheet.models.Cell({'column_id': COL_LOC_COORDS, 'value': l_coords_str}),
                    smartsheet.models.Cell({'column_id': COL_DISTANCE, 'value': new_miles})
                ]
                
                new_row = smartsheet.models.Row({'id': row.id, 'cells': updated_cells})
                rows_to_update.append(new_row)
                print(f"  Success: Corrected distance via Google to {new_miles} miles.")
            else:
                print(f"  Failed: Google search fallback could not parse this location.")

        if len(rows_to_update) >= 50:
            smartsheet_client.Sheets.update_rows(int(sheet_id), rows_to_update)
            print(f"Saved batch of {len(rows_to_update)} Google-corrected rows.")
            rows_to_update = []

    if rows_to_update:
        smartsheet_client.Sheets.update_rows(int(sheet_id), rows_to_update)
        print("Final batch of Google-corrected rows successfully saved.")
        
    print("\nOutlier correction cycle complete.")

if __name__ == "__main__":
    main()
