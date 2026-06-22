import os
import math
import time
import smartsheet
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

# 1. Initialize Secrets
access_token = os.environ.get('SMARTSHEET_TOKEN')
sheet_id = os.environ.get('SHEET_ID')

if not access_token or not sheet_id:
    print("Error: Missing Smartsheet secrets.")
    exit(1)

smartsheet_client = smartsheet.Smartsheet(access_token)

# 2. Hardcoded Staging Coordinates Map (Cleaned Keys for Fuzzy Matching)
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

# Explicit Column ID Definitions
COL_STAGING_LOC = 2443388002799492
COL_ADDRESS = 4272975351418756
COL_CITY = 8776574978789252
COL_STATE = 191588189114244
COL_ZIP = 4695187816484740

# Target Columns to Fill
COL_STAGING_COORDS = 8304325909843844
COL_LOC_COORDS = 985976515366788
COL_DISTANCE = 2182270936190852

def haversine_distance(coord1, coord2):
    """Calculates the distance in miles between two coordinate tuples."""
    if not coord1 or not coord2 or None in coord1 or None in coord2:
        return None
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    
    R = 3958.8  # Earth radius in miles
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    
    a = (math.sin(d_lat / 2) ** 2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

def get_staging_coords(location_string):
    """Normalizes the string to match staging coordinates safely."""
    if not location_string:
        return None
    normalized = location_string.lower().replace("mobiles", "").strip()
    for key, coords in STAGING_COORDS.items():
        if key in normalized:
            return coords
    return None

def main():
    print("Fetching Smartsheet data...")
    sheet = smartsheet_client.Sheets.get_sheet(int(sheet_id))
    
    # Setup Geocoding engine
    geolocator = Nominatim(user_agent="lifeserve_distance_calculator")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.2)
    
    address_cache = {}
    rows_to_update = []
    
    print(f"Processing {len(sheet.rows)} rows...")
    for row in sheet.rows:
        # Extract row data by matching Column IDs
        cells = {cell.column_id: cell for cell in row.cells}
        
        staging_val = cells[COL_STAGING_LOC].value
        addr_val = cells[COL_ADDRESS].value
        city_val = cells[COL_CITY].value
        state_val = cells[COL_STATE].value
        zip_val = cells[COL_ZIP].value if COL_ZIP in cells else ""
        
        # Check if coordinates are already filled to prevent duplicate work
        existing_loc_coords = cells.get(COL_LOC_COORDS).value if cells.get(COL_LOC_COORDS) else None
        if existing_loc_coords:
            continue
            
        # 1. Map Staging Coords
        s_coords = get_staging_coords(staging_val)
        s_coords_str = f"{s_coords}, {s_coords}" if s_coords else ""
        
        # 2. Geocode Destination Coords
        l_coords = None
        l_coords_str = ""
        if addr_val and city_val and state_val:
            full_address = f"{addr_val}, {city_val}, {state_val} {zip_val}".strip()
            
            if full_address in address_cache:
                l_coords = address_cache[full_address]
            else:
                try:
                    loc = geocode(full_address)
                    if loc:
                        l_coords = (loc.latitude, loc.longitude)
                        address_cache[full_address] = l_coords
                        print(f"Geocoded: {full_address} -> {l_coords}")
                except Exception as e:
                    print(f"Error geocoding {full_address}: {e}")
            
            if l_coords:
                l_coords_str = f"{l_coords}, {l_coords}"
                
        # 3. Calculate Distance
        miles = haversine_distance(s_coords, l_coords)
        
        # Build update cells
        updated_cells = []
        if s_coords_str:
            updated_cells.append(smartsheet.models.Cell({'column_id': COL_STAGING_COORDS, 'value': s_coords_str}))
        if l_coords_str:
            updated_cells.append(smartsheet.models.Cell({'column_id': COL_LOC_COORDS, 'value': l_coords_str}))
        if miles is not None:
            updated_cells.append(smartsheet.models.Cell({'column_id': COL_DISTANCE, 'value': miles}))
            
        if updated_cells:
            new_row = smartsheet.models.Row({'id': row.id, 'cells': updated_cells})
            rows_to_update.append(new_row)
            
        # Write updates in chunks of 100 cells to prevent hitting API size payloads
        if len(rows_to_update) >= 100:
            smartsheet_client.Sheets.update_rows(int(sheet_id), rows_to_update)
            print(f"Batch update saved successfully ({len(rows_to_update)} rows)")
            rows_to_update = []

    # Final cleanup patch update
    if rows_to_update:
        smartsheet_client.Sheets.update_rows(int(sheet_id), rows_to_update)
        print(f"Final batch update saved successfully ({len(rows_to_update)} rows)")

if __name__ == "__main__":
    main()
