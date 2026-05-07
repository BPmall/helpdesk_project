import sqlite3
import os

def migrate():
    db_path = os.path.join(os.path.dirname(__file__), 'instance', 'helpdesk.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}. No migration needed.")
        return
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(equipments)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'image' not in columns:
            cursor.execute("ALTER TABLE equipments ADD COLUMN image VARCHAR(255)")
            conn.commit()
            print("Successfully added 'image' column to 'equipments' table.")
        else:
            print("Column 'image' already exists in 'equipments' table.")
            
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    migrate()
