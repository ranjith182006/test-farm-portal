import sqlite3
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'farm.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Create USERS table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL, -- 'Admin' or 'User'
        tenant_id INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 2. Create DRUGS table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS drugs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, -- Remove UNIQUE constraint on name alone since different tenants can add same drug
        active_ingredient TEXT NOT NULL,
        drug_class TEXT NOT NULL,
        classification TEXT NOT NULL,
        withdrawal_meat_days INTEGER NOT NULL,
        withdrawal_milk_days INTEGER NOT NULL,
        withdrawal_eggs_days INTEGER NOT NULL,
        mrl_limit REAL NOT NULL, -- in mcg/kg (ppb)
        half_life_hours REAL NOT NULL, -- for decay simulation
        tenant_id INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(name, tenant_id) -- Drug names must be unique within a tenant
    )
    ''')

    # 3. Create LIVESTOCK table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS livestock (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tag_id TEXT NOT NULL, -- Remove global UNIQUE constraint
        species TEXT NOT NULL,
        breed TEXT NOT NULL,
        weight REAL NOT NULL, -- in kg
        pen_number TEXT NOT NULL,
        status TEXT DEFAULT 'Healthy', -- 'Healthy', 'Treated', 'In Withdrawal', 'Quarantine'
        tenant_id INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(tag_id, tenant_id) -- Tag IDs must be unique within a tenant
    )
    ''')

    # 4. Create TREATMENTS table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS treatments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        livestock_id INTEGER NOT NULL,
        drug_id INTEGER NOT NULL,
        dosage_mg_per_kg REAL NOT NULL, -- dosage concentration
        total_mg REAL NOT NULL, -- total active ingredient in mg
        route TEXT NOT NULL, -- 'Intramuscular', 'Subcutaneous', 'Oral', 'Topical'
        start_date TEXT NOT NULL, -- ISO Format YYYY-MM-DD HH:MM:SS
        end_date TEXT NOT NULL, -- ISO Format
        vet_name TEXT NOT NULL,
        tenant_id INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (livestock_id) REFERENCES livestock (id) ON DELETE CASCADE,
        FOREIGN KEY (drug_id) REFERENCES drugs (id) ON DELETE CASCADE
    )
    ''')

    conn.commit()

    # Seed users if empty
    cursor.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] == 0:
        seed_users(cursor)
        conn.commit()

    # Seed initial drugs, livestock, treatments if empty
    cursor.execute('SELECT COUNT(*) FROM drugs')
    if cursor.fetchone()[0] == 0:
        seed_data(cursor)
        conn.commit()

    conn.close()

def seed_users(cursor):
    users = [
        ("admin", generate_password_hash("admin123"), "Admin", 1),
        ("employe", generate_password_hash("worker"), "User", 1)
    ]
    cursor.executemany('''
        INSERT INTO users (username, password_hash, role, tenant_id)
        VALUES (?, ?, ?, ?)
    ''', users)

def seed_data(cursor):
    # Seeding Drugs (tenant_id = 1)
    drugs = [
        ("Penicillin G (Pen-Ject)", "Penicillin G Benzathine", "Penicillins", "Highly Important", 10, 3, 0, 50.0, 18.0, 1),
        ("Ceftiofur (Excenel)", "Ceftiofur Sodium", "Cephalosporins (3rd/4th Gen)", "Highest Priority Critically Important", 4, 0, 0, 1000.0, 12.0, 1),
        ("Tylosin (Tylan 200)", "Tylosin Phosphate", "Macrolides", "Highest Priority Critically Important", 21, 0, 0, 200.0, 24.0, 1),
        ("Oxytetracycline (Terramycin)", "Oxytetracycline dihydrate", "Tetracyclines", "Highly Important", 28, 4, 0, 200.0, 36.0, 1),
        ("Sulfadimethoxine (Albon)", "Sulfadimethoxine", "Sulfonamides", "Highly Important", 7, 2, 0, 100.0, 16.0, 1),
        ("Enrofloxacin (Baytril 100)", "Enrofloxacin", "Fluoroquinolones", "Highest Priority Critically Important", 28, 0, 0, 100.0, 20.0, 1)
    ]
    cursor.executemany('''
        INSERT INTO drugs (name, active_ingredient, drug_class, classification, 
                           withdrawal_meat_days, withdrawal_milk_days, withdrawal_eggs_days, 
                           mrl_limit, half_life_hours, tenant_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', drugs)

    # Seeding Livestock (tenant_id = 1)
    livestock = [
        ("LIV-C-1002", "Cattle", "Angus", 450.0, "Pen A-1", "Healthy", 1),
        ("LIV-C-1004", "Cattle", "Hereford", 420.0, "Pen A-1", "In Withdrawal", 1),
        ("LIV-S-2051", "Swine", "Landrace", 110.0, "Pen B-3", "Healthy", 1),
        ("LIV-S-2055", "Swine", "Duroc", 98.0, "Pen B-3", "Treated", 1),
        ("LIV-H-3012", "Sheep", "Suffolk", 65.0, "Pasture C", "Healthy", 1),
        ("LIV-P-4088", "Poultry", "Leghorn", 1.8, "Coop D-2", "Healthy", 1),
        ("LIV-P-4091", "Poultry", "Rhode Island Red", 2.1, "Coop D-2", "In Withdrawal", 1)
    ]
    cursor.executemany('''
        INSERT INTO livestock (tag_id, species, breed, weight, pen_number, status, tenant_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', livestock)

    # Fetch IDs to create treatment links
    cursor.execute('SELECT id, tag_id, weight FROM livestock WHERE tenant_id = 1')
    livestock_map = {row['tag_id']: (row['id'], row['weight']) for row in cursor.fetchall()}

    cursor.execute('SELECT id, name, withdrawal_meat_days FROM drugs WHERE tenant_id = 1')
    drug_map = {row['name']: (row['id'], row['withdrawal_meat_days']) for row in cursor.fetchall()}

    # Helper dates
    now = datetime.now()
    
    # 1. Past completed treatment
    start_t1 = (now - timedelta(days=35)).strftime('%Y-%m-%d %H:%M:%S')
    end_t1 = (now - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    l_id, l_w = livestock_map["LIV-C-1002"]
    d_id, d_w = drug_map["Penicillin G (Pen-Ject)"]
    cursor.execute('''
        INSERT INTO treatments (livestock_id, drug_id, dosage_mg_per_kg, total_mg, route, start_date, end_date, vet_name, tenant_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    ''', (l_id, d_id, 10.0, 10.0 * l_w, "Intramuscular", start_t1, end_t1, "Dr. Sarah Jenkins"))

    # 2. Active treatment
    start_t2 = (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
    end_t2 = (now + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    l_id, l_w = livestock_map["LIV-S-2055"]
    d_id, d_w = drug_map["Ceftiofur (Excenel)"]
    cursor.execute('''
        INSERT INTO treatments (livestock_id, drug_id, dosage_mg_per_kg, total_mg, route, start_date, end_date, vet_name, tenant_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    ''', (l_id, d_id, 3.0, 3.0 * l_w, "Intramuscular", start_t2, end_t2, "Dr. Alan Grant"))

    # 3. Completed treatment but in withdrawal period
    start_t3 = (now - timedelta(days=8)).strftime('%Y-%m-%d %H:%M:%S')
    end_t3 = (now - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
    l_id, l_w = livestock_map["LIV-C-1004"]
    d_id, d_w = drug_map["Oxytetracycline (Terramycin)"]
    cursor.execute('''
        INSERT INTO treatments (livestock_id, drug_id, dosage_mg_per_kg, total_mg, route, start_date, end_date, vet_name, tenant_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    ''', (l_id, d_id, 20.0, 20.0 * l_w, "Subcutaneous", start_t3, end_t3, "Dr. Sarah Jenkins"))

    # 4. Completed treatment in withdrawal
    start_t4 = (now - timedelta(days=4)).strftime('%Y-%m-%d %H:%M:%S')
    end_t4 = (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    l_id, l_w = livestock_map["LIV-P-4091"]
    d_id, d_w = drug_map["Sulfadimethoxine (Albon)"]
    cursor.execute('''
        INSERT INTO treatments (livestock_id, drug_id, dosage_mg_per_kg, total_mg, route, start_date, end_date, vet_name, tenant_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    ''', (l_id, d_id, 50.0, 50.0 * l_w, "Oral", start_t4, end_t4, "Dr. Alan Grant"))

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully at:", DB_PATH)
