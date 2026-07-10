import os
import re
import pandas as pd
import smartsheet

# Strict 4-space uniform indentation formatting enforced
# Strict 4-space uniform indentation formatting enforced
def convert_to_military(raw_time):
    if pd.isna(raw_time):
        return ""
    try:
        # Converts time variations like "11:00 am" or "01:15 pm" smoothly into "11:00" or "13:15"
        return pd.to_datetime(str(raw_time).strip(), format='%I:%M %p').strftime('%H:%M')
    except Exception:
        try:
            # Fallback for alternative spacing formats if present
            return pd.to_datetime(str(raw_time).strip()).strftime('%H:%M')
        except Exception:
            return ""

def update_smartsheet_projections():
    # Initialize credentials dynamically exactly like your successful coordinate script
    token = os.environ.get("SMARTSHEET_TOKEN")
    sheet_id_env = os.environ.get("SHEET_ID")
    
    if not token or not sheet_id_env:
        print("Error: Missing dynamic Smartsheet token or Sheet ID environment secrets.")
        return

    # Initialize the client and convert the dynamic environment string to an integer
    smartsheet_client = smartsheet.Smartsheet(token)
    sheet_id = int(sheet_id_env)
    
    # Hardcoded Column IDs matching your master grid mapping layout
    date_col_id = 3147075444576132
    becs_col_id = 2021175537733508
    target_col_id = 4755624290455428  # Collections Actual Column ID

    # Target your newly uploaded historical overview spreadsheet
    excel_file = "2025 Drive Overview.xlsx"
    if not os.path.exists(excel_file):
        print(f"Error: Target Excel workbook '{excel_file}' not found in workspace.")
        return
        
    print(f"Opening Excel workbook: {excel_file}")
    df = pd.read_excel(excel_file, sheet_name=0)
    
    # Standardize column headers by converting to lowercase and stripping hidden spaces
    df.columns = df.columns.astype(str).str.strip().str.lower()
    
    # Explicitly map our standardized lowercase column target matches
    date_col = "drive date"
    becs_col = "account code"
    yield_col = "actual yield"
    
    # Standardizing incoming data layouts to guarantee exact string lookup matches
    df[date_col] = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")
    df[becs_col] = df[becs_col].astype(str).str.strip()
    df[yield_col] = df[yield_col].astype(str).str.strip()
    
    # Generate composite mapping dictionary lookup keys (Date + BECS Code)
    yield_lookup = {}
    for _, row in df.iterrows():
        if row[yield_col] and row[yield_col] != "nan":
            composite_key = f"{row[date_col]}_{row[becs_col]}"
            yield_lookup[composite_key] = row[yield_col]

    print(f"Successfully loaded {len(yield_lookup)} actual yield mapping rules from Excel.")
    print("Fetching active sheet data from master Smartsheet channel...")
    
    sheet = smartsheet_client.Sheets.get_sheet(sheet_id)
    rows_to_update = []

    for sheet_row in sheet.rows:
        row_date = ""
        row_becs = ""
        current_actual_val = ""
        
        for cell in sheet_row.cells:
            if cell.column_id == date_col_id and cell.value:
                row_date = pd.to_datetime(cell.value).strftime("%Y-%m-%d")
            elif cell.column_id == becs_col_id and cell.value:
                row_becs = str(cell.value).strip()
            elif cell.column_id == target_col_id:
                current_actual_val = str(cell.value).strip() if cell.value else ""

        if row_date and row_becs:
            lookup_key = f"{row_date}_{row_becs}"
            
            if lookup_key in yield_lookup:
                new_val = yield_lookup[lookup_key]
                
                # Only push an update if the Collections Actual cell is different or blank
                if current_actual_val != new_val:
                    new_cell = smartsheet.models.Cell()
                    new_cell.column_id = target_col_id
                    new_cell.value = new_val
                    
                    updated_row = smartsheet.models.Row()
                    updated_row.id = sheet_row.id
                    updated_row.cells.append(new_cell)
                    rows_to_update.append(updated_row)

    # Output to Smartsheet in chunks of 100 rows
    if rows_to_update:
        print(f"Surgically transmitting {len(rows_to_update)} updated staffing entries...")
        chunk_size = 100
        for i in range(0, len(rows_to_update), chunk_size):
            chunk = rows_to_update[i:i + chunk_size]
            smartsheet_client.Sheets.update_rows(sheet_id, chunk)
        print("Smartsheet data update completed successfully!")
    else:
        print("No updates needed. Everything matches.")

if __name__ == "__main__":
    update_smartsheet_projections()
