import os
import pandas as pd
import smartsheet

# Strict 4-space uniform indentation formatting enforced
def update_smartsheet_projections():
    # Initialize the Smartsheet client using the environment variable
    token = os.environ.get("SMARTSHEET_ACCESS_TOKEN")
    if not token:
        print("Error: SMARTSHEET_ACCESS_TOKEN environment variable not set.")
        return

    smartsheet_client = smartsheet.Smartsheet(token)
    
    # Target Configuration
    sheet_id = 5398875258261380  # Account ID row sheet context
    date_col_id = 3147075444576132
    becs_col_id = 2021175537733508
    target_col_id = 6385244412612484  # Collection Projection Column ID

    # Load and clean the new Excel export
    excel_file = "2025 Projections From Drives.xlsx"
    if not os.path.exists(excel_file):
        print(f"Error: Target data file {excel_file} not found.")
        return
        
    df = pd.read_csv(excel_file)
    
    # standardizing values to ensure exact matching string lookups
    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    df["BECS Code"] = df["BECS Code"].astype(str).str.strip()
    df["Projection"] = df["Projection"].astype(str).str.strip()
    
    # Create the lookup map based on the composite key (Date + BECS Code)
    projection_lookup = {}
    for _, row in df.iterrows():
        composite_key = f"{row['Date']}_{row['BECS Code']}"
        projection_lookup[composite_key] = row["Projection"]

    print(f"Successfully loaded {len(projection_lookup)} mapping rules from Excel.")

    # Pull down the current Smartsheet rows
    print("Fetching active sheet data from Smartsheet...")
    sheet = smartsheet_client.Sheets.get_sheet(sheet_id)
    
    rows_to_update = []

    for sheet_row in sheet.rows:
        row_date = ""
        row_becs = ""
        current_projection_val = ""
        
        # Extract row cell values context
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
                
                # Only update if the value has changed or is empty
                if current_projection_val != new_val:
                    new_cell = smartsheet.models.Cell()
                    new_cell.column_id = target_col_id
                    new_cell.value = new_val
                    
                    updated_row = smartsheet.models.Row()
                    updated_row.id = sheet_row.id
                    updated_row.cells.append(new_cell)
                    rows_to_update.append(updated_row)

    # Perform updates in chunks to protect execution runtime boundaries
    if rows_to_update:
        print(f"Surgically transmitting {len(rows_to_update)} row updates to Smartsheet...")
        chunk_size = 100
        for i in range(0, len(rows_to_update), chunk_size):
            chunk = rows_to_update[i:i + chunk_size]
            smartsheet_client.Sheets.update_rows(sheet_id, chunk)
        print("Smartsheet updates completed successfully!")
    else:
        print("No new updates required. Smartsheet data matches the excel file perfectly.")

if __name__ == "__main__":
    update_smartsheet_projections()
