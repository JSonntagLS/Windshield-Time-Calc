import os
import pandas as pd
import smartsheet

# Strict 4-space uniform indentation formatting enforced
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
    target_col_id = 6385244412612484  # Collection Projection Column ID

    # Use your exact newly uploaded file name
    excel_file = "2025 Projections From Drives.xlsx"
    if not os.path.exists(excel_file):
        print(f"Error: Target Excel workbook '{excel_file}' not found in workspace.")
        return
        
    print(f"Opening Excel workbook: {excel_file}")
    df = pd.read_excel(excel_file, sheet_name=0)
    
    # Standardizing incoming data layouts to guarantee exact string lookup matches
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    df["BECS Code"] = df["BECS Code"].astype(str).str.strip()
    # Note: The raw excel column header you uploaded is called 'Projection'
    df["Projection"] = df["Projection"].astype(str).str.strip()
    
    # Generate composite mapping dictionary lookup keys (Date + BECS Code)
    projection_lookup = {}
    for _, row in df.iterrows():
        composite_key = f"{row['Date']}_{row['BECS Code']}"
        projection_lookup[composite_key] = row["Projection"]

    print(f"Successfully loaded {len(projection_lookup)} mapping rules from Excel.")
    print("Fetching active sheet data from master Smartsheet channel...")
    
    sheet = smartsheet_client.Sheets.get_sheet(sheet_id)
    rows_to_update = []

    for sheet_row in sheet.rows:
        row_date = ""
        row_becs = ""
        current_projection_val = ""
        
        for cell in sheet_row.cells:
            if cell.column_id == date_col_id and cell.value:
                row_date = pd.to_datetime(cell.value).strftime("%Y-%m-%d")
            elif cell.column_id == becs_col_id and cell.value:
                row_becs = str(cell.value).strip()
            elif cell.column_id == target_col_id:
                current_projection_val = str(cell.value).strip() if cell.value else ""

        if row_date and row_becs:
            lookup_key = f"{row_date}_{row_becs}"
            
            if lookup_key in projection_lookup:
                new_val = projection_lookup[lookup_key]
                
                # Only push an update if the projection column cell is different or blank
                if current_projection_val != new_val:
                    new_cell = smartsheet.models.Cell()
                    new_cell.column_id = target_col_id
                    new_cell.value = new_val
                    
                    updated_row = smartsheet.models.Row()
                    updated_row.id = sheet_row.id
                    updated_row.cells.append(new_cell)
                    rows_to_update.append(updated_row)

    # Output to Smartsheet in chunks of 100 rows
    if rows_to_update:
        print(f"Surgically transmitting {len(rows_to_update)} updated projection entries...")
        chunk_size = 100
        for i in range(0, len(rows_to_update), chunk_size):
            chunk = rows_to_update[i:i + chunk_size]
            smartsheet_client.Sheets.update_rows(sheet_id, chunk)
        print("Smartsheet data update completed successfully!")
    else:
        print("No updates needed. Everything matches.")

if __name__ == "__main__":
    update_smartsheet_projections()
