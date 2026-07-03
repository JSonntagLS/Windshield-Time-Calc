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
    start_time_col_id = 138544857517956   # Start Time Column ID
    end_time_col_id = 4642144484888452    # End Time Column ID

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
    start_col = "start time"
    end_col = "end time"
    
    # Standardizing incoming data layouts to guarantee exact string lookup matches
    df[date_col] = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")
    df[becs_col] = df[becs_col].astype(str).str.strip()
    
    # Convert Excel values directly to military strings
    df["start_military"] = df[start_col].apply(convert_to_military)
    df["end_military"] = df[end_col].apply(convert_to_military)
    
    # Generate composite mapping dictionary lookup keys (Date + BECS Code)
    time_lookup = {}
    for _, row in df.iterrows():
        if row["start_military"] or row["end_military"]:
            composite_key = f"{row[date_col]}_{row[becs_col]}"
            time_lookup[composite_key] = (row["start_military"], row["end_military"])

    print(f"Successfully loaded {len(time_lookup)} time mapping rules from Excel.")
    print("Fetching active sheet data from master Smartsheet channel...")
    
    sheet = smartsheet_client.Sheets.get_sheet(sheet_id)
    rows_to_update = []

    for sheet_row in sheet.rows:
        row_date = ""
        row_becs = ""
        current_start_val = ""
        current_end_val = ""
        
        for cell in sheet_row.cells:
            if cell.column_id == date_col_id and cell.value:
                row_date = pd.to_datetime(cell.value).strftime("%Y-%m-%d")
            elif cell.column_id == becs_col_id and cell.value:
                row_becs = str(cell.value).strip()
            elif cell.column_id == start_time_col_id:
                current_start_val = str(cell.value).strip() if cell.value else ""
            elif cell.column_id == end_time_col_id:
                current_end_val = str(cell.value).strip() if cell.value else ""

        if row_date and row_becs:
            lookup_key = f"{row_date}_{row_becs}"
            
            if lookup_key in time_lookup:
                new_start, new_end = time_lookup[lookup_key]
                cells_to_change = []
                
                if new_start and current_start_val != new_start:
                    start_cell = smartsheet.models.Cell()
                    start_cell.column_id = start_time_col_id
                    start_cell.value = new_start
                    cells_to_change.append(start_cell)
                    
                if new_end and current_end_val != new_end:
                    end_cell = smartsheet.models.Cell()
                    end_cell.column_id = end_time_col_id
                    end_cell.value = new_end
                    cells_to_change.append(end_cell)
                    
                if cells_to_change:
                    updated_row = smartsheet.models.Row()
                    updated_row.id = sheet_row.id
                    updated_row.cells.extend(cells_to_change)
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
