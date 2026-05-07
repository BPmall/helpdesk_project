import sqlite3
import os

def migrate():
    # กำหนดที่อยู่ของไฟล์ฐานข้อมูล SQLite
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'helpdesk.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}. Please run the application first.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # --- 1. เพิ่มคอลัมน์ในตาราง tickets ---
    print("Checking 'tickets' table...")
    cursor.execute("PRAGMA table_info(tickets)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'equipment_id' not in columns:
        print("Adding 'equipment_id' column to 'tickets' table...")
        cursor.execute("ALTER TABLE tickets ADD COLUMN equipment_id INTEGER REFERENCES equipments(id)")
    else:
        print("'equipment_id' already exists in 'tickets'.")

    # --- 2. เพิ่มคอลัมน์ในตาราง equipments ---
    print("\nChecking 'equipments' table...")
    cursor.execute("PRAGMA table_info(equipments)")
    equipment_columns = [col[1] for col in cursor.fetchall()]

    new_columns = {
        'acquired_date': 'DATE',
        'warranty_info': 'VARCHAR(255)',
        'warranty_expiry_date': 'DATE',
        'vendor_name': 'VARCHAR(200)',
        'vendor_contact': 'VARCHAR(255)',
        'model': 'VARCHAR(100)',
        'voltage': 'VARCHAR(50)',
        'power_consumption': 'VARCHAR(50)',
        'current_amps': 'VARCHAR(50)',
        'refrigerant': 'VARCHAR(50)'
    }

    for col_name, col_type in new_columns.items():
        if col_name not in equipment_columns:
            print(f"Adding '{col_name}' column to 'equipments' table...")
            cursor.execute(f"ALTER TABLE equipments ADD COLUMN {col_name} {col_type}")
        else:
            print(f"'{col_name}' already exists in 'equipments'.")

    conn.commit()
    conn.close()
    print("\nMigration completed successfully!")

if __name__ == "__main__":
    migrate()
