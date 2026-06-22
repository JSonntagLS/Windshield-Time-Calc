import os
import math
import time
import smartsheet
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

# Initialize Secrets
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

COL_STAGING_COORDS = 8304325909843844
COL_LOC_COORDS = 985976515366788
COL_DISTANCE = 2182270936190852

def haversine_distance(coord1, coord2):
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

def clean_address_string(address):
    """Strips out common clutter text that causes free geocoders to fail."""
    if not address:
        return ""
    addr = str(address).upper()
    # Remove common indoor descriptors that confuse basic map search
    for terms in ["SUITE", "STE ", "ROOM ", "RM ", "BASEMENT", "APT ", "LOT "]:
        if terms in addr:
            addr = addr.split(terms)
    return addr.strip().strip(',')

def main():
    print("Fetching Smartsheet to locate remaining blank coordinates...")
    sheet = smartsheet_client.Sheets.get_sheet(int(sheet_id))
    
    geolocator = Nominatim(user_agent="lifeserve_fallback_processor")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.5)
    
    address_cache = {}
    rows_to_update = []
    blank_count = 0

    for row in sheet.rows:
        cells = {cell.column_id: cell for cell in row.cells}
        
        # Only touch rows where Location Coordinates are currently completely blank
        existing_loc_coords = cells.get(COL_LOC_COORDS).value if cells.get(COL_LOC_COORDS) else None
        if existing_loc_coords and str(existing_loc_coords).strip():
            continue
            
        blank_count += 1
        staging_val = cells[COL_STAGING_LOC].value
        addr_val = cells[COL_ADDRESS].value
        city_val = cells[COL_CITY].value
        state_val = cells[COL_STATE].value
        
        if COL_ZIP in cells and cells[COL_ZIP].value:
            raw_zip_string = str(cells[COL_ZIP].value)
            split_zip_components = raw_zip_string.split('.')
            # Safely grab the first item without using brackets
            for item in split_zip_components:
                zip_val = item.strip()
                break
        else:
            zip_val = ""
            
        s_coords = get_staging_coords(staging_val)
        s_coords_str = f"{s_coords}, {s_coords}" if s_coords else ""
        
        l_coords = None
        
        # TIER 1: Full Address Search (With text cleaning helper applied)
        cleaned_addr = clean_address_string(addr_val)
        full_address = f"{cleaned_addr}, {city_val}, {state_val} {zip_val}".strip()
        
        if full_address in address_cache:
            l_coords = address_cache[full_address]
        else:
            try:
                loc = geocode(full_address)
                if loc:
                    l_coords = (loc.latitude, loc.longitude)
                    print(f"Tier 1 Success (Cleaned): {full_address} -> {l_coords}")
            except Exception:
                pass
                
        # TIER 2: Fallback to ZIP Code Centroid (Your requested modification)
        if not l_coords and zip_val and len(zip_val) >= 5:
            try:
                print(f"Tier 1 Failed. Trying Tier 2 (ZIP Centroid) for: {zip_val[:5]}")
                loc = geocode({"postalcode": zip_val[:5]})
                if loc:
                    l_coords = (loc.latitude, loc.longitude)
            except Exception:
                pass
                
        # TIER 3: Fallback to City, State Town Center
        if not l_coords and city_val and state_val:
            city_fallback = f"{city_val}, {state_val}".strip()
            try:
                print(f"Tier 2 Failed. Trying Tier 3 (City Center) for: {city_fallback}")
                loc = geocode(city_fallback)
                if loc:
                    l_coords = (loc.latitude, loc.longitude)
            except Exception:
                pass
                
        # If any of the tiers hit a location, save it
        if l_coords:
            address_cache[full_address] = l_coords
            l_coords_str = f"{l_coords}, {l_coords}"
            miles = haversine_distance(s_coords, l_coords)
            
            updated_cells = []
            if s_coords_str:
                updated_cells.append(smartsheet.models.Cell({'column_id': COL_STAGING_COORDS, 'value': s_coords_str}))
            updated_cells.append(smartsheet.models.Cell({'column_id': COL_LOC_COORDS, 'value': l_coords_str}))
            if miles is not None:
                updated_cells.append(smartsheet.models.Cell({'column_id': COL_DISTANCE, 'value': miles}))
                
            new_row = smartsheet.models.Row({'id': row.id, 'cells': updated_cells})
            rows_to_update.append(new_row)

        if len(rows_to_update) >= 50:
            smartsheet_client.Sheets.update_rows(int(sheet_id), rows_to_update)
            print(f"Saved fallback batch of {len(rows_to_update)} rows.")
            rows_to_update = []

    if rows_to_update:
        smartsheet_client.Sheets.update_rows(int(sheet_id), rows_to_update)
        print("Final fallback batch saved.")
        
    print(f"Fallback run complete. Checked {blank_count} total blank rows.")

if __name__ == "__main__":
    main()
