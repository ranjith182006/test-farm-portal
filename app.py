from flask import Flask, render_template, jsonify, request, session
import database
import sqlite3
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash
import math

app = Flask(__name__)
app.secret_key = 'super_secret_farm_key_for_residueguard_session_auth'

# Initialize database on startup
database.init_db()

def update_livestock_statuses(tenant_id):
    """
    Dynamically evaluate livestock statuses based on active/recent treatments
    partitioned by tenant, and update the database.
    """
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    # Get all livestock for this tenant
    cursor.execute("SELECT id, status FROM livestock WHERE tenant_id = ?", (tenant_id,))
    animals = cursor.fetchall()
    
    for animal in animals:
        animal_id = animal['id']
        current_status = animal['status']
        
        # Get latest treatment for this animal
        cursor.execute("""
            SELECT t.start_date, t.end_date, d.withdrawal_meat_days, d.withdrawal_milk_days, d.withdrawal_eggs_days
            FROM treatments t
            JOIN drugs d ON t.drug_id = d.id
            WHERE t.livestock_id = ? AND t.tenant_id = ?
            ORDER BY t.end_date DESC LIMIT 1
        """, (animal_id, tenant_id))
        
        treatment = cursor.fetchone()
        
        new_status = 'Healthy'
        if treatment:
            start_date = datetime.strptime(treatment['start_date'], '%Y-%m-%d %H:%M:%S')
            end_date = datetime.strptime(treatment['end_date'], '%Y-%m-%d %H:%M:%S')
            
            # Max withdrawal days among meat, milk, eggs
            withdrawal_days = max(
                treatment['withdrawal_meat_days'], 
                treatment['withdrawal_milk_days'], 
                treatment['withdrawal_eggs_days']
            )
            clearance_date = end_date + timedelta(days=withdrawal_days)
            now = datetime.now()
            
            if start_date <= now <= end_date:
                new_status = 'Treated'
            elif end_date < now <= clearance_date:
                new_status = 'In Withdrawal'
            else:
                new_status = 'Healthy'
                
        # Update if changed and not Quarantine (which is manual)
        if current_status != 'Quarantine' and current_status != new_status:
            cursor.execute("UPDATE livestock SET status = ? WHERE id = ? AND tenant_id = ?", (new_status, animal_id, tenant_id))
            
    conn.commit()
    conn.close()

# HTML Template Route
@app.route('/')
def index():
    return render_template('index.html')

# ==================== AUTHENTICATION ENDPOINTS ====================

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "Missing username or password"}), 400
        
    username = data['username']
    password = data['password']
    
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    
    if user and check_password_hash(user['password_hash'], password):
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        session['tenant_id'] = user['tenant_id']
        return jsonify({
            "message": "Login successful",
            "user": {
                "username": user['username'],
                "role": user['role']
            }
        }), 200
        
    return jsonify({"error": "Invalid username or password"}), 401

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "Missing username or password"}), 400
        
    username = data['username'].strip()
    password = data['password']
    
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters long"}), 400
    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters long"}), 400
        
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    # Check if username exists
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return jsonify({"error": "Username already exists"}), 400
        
    from werkzeug.security import generate_password_hash
    pw_hash = generate_password_hash(password)
    
    try:
        # Insert user with a placeholder tenant_id = 0, then update it to match their new user ID
        cursor.execute("INSERT INTO users (username, password_hash, role, tenant_id) VALUES (?, ?, 'Admin', 0)", (username, pw_hash))
        user_id = cursor.lastrowid
        cursor.execute("UPDATE users SET tenant_id = ? WHERE id = ?", (user_id, user_id))
        conn.commit()
        conn.close()
        return jsonify({"message": "Registration successful! You can now sign in."}), 201
    except Exception as e:
        conn.close()
        return jsonify({"error": f"Database error: {str(e)}"}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200

@app.route('/api/me')
def me():
    if 'user_id' in session:
        return jsonify({
            "username": session.get('username'),
            "role": session.get('role')
        }), 200
    return jsonify({"error": "Not logged in"}), 401

# ==================== PROTECTED API ENDPOINTS ====================

@app.route('/api/livestock', methods=['GET', 'POST'])
def handle_livestock():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized. Please log in."}), 401
        
    tenant_id = session['tenant_id']
    update_livestock_statuses(tenant_id)
    
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'GET':
        cursor.execute("SELECT * FROM livestock WHERE tenant_id = ? ORDER BY tag_id ASC", (tenant_id,))
        rows = cursor.fetchall()
        
        livestock_list = []
        for row in rows:
            animal = dict(row)
            cursor.execute("""
                SELECT t.id as treatment_id, t.end_date, d.name as drug_name, 
                       d.withdrawal_meat_days, d.withdrawal_milk_days, d.withdrawal_eggs_days
                FROM treatments t
                JOIN drugs d ON t.drug_id = d.id
                WHERE t.livestock_id = ? AND t.tenant_id = ?
                ORDER BY t.end_date DESC LIMIT 1
            """, (animal['id'], tenant_id))
            t_row = cursor.fetchone()
            
            if t_row:
                animal['latest_treatment'] = dict(t_row)
                end_dt = datetime.strptime(t_row['end_date'], '%Y-%m-%d %H:%M:%S')
                w_days = max(t_row['withdrawal_meat_days'], t_row['withdrawal_milk_days'], t_row['withdrawal_eggs_days'])
                clear_dt = end_dt + timedelta(days=w_days)
                animal['clearance_date'] = clear_dt.strftime('%Y-%m-%d %H:%M:%S')
                
                now = datetime.now()
                if end_dt < now <= clear_dt:
                    animal['withdrawal_remaining_seconds'] = max(0, int((clear_dt - now).total_seconds()))
                else:
                    animal['withdrawal_remaining_seconds'] = 0
            else:
                animal['latest_treatment'] = None
                animal['clearance_date'] = None
                animal['withdrawal_remaining_seconds'] = 0
                
            livestock_list.append(animal)
            
        conn.close()
        return jsonify(livestock_list)
        
    elif request.method == 'POST':
        if session.get('role') != 'Admin':
            return jsonify({"error": "Forbidden. Admin access required."}), 403
            
        data = request.json
        if not data or not all(k in data for k in ('tag_id', 'species', 'breed', 'weight', 'pen_number')):
            return jsonify({"error": "Missing required fields"}), 400
            
        try:
            cursor.execute("""
                INSERT INTO livestock (tag_id, species, breed, weight, pen_number, status, tenant_id)
                VALUES (?, ?, ?, ?, ?, 'Healthy', ?)
            """, (data['tag_id'], data['species'], data['breed'], float(data['weight']), data['pen_number'], tenant_id))
            conn.commit()
            new_id = cursor.lastrowid
            conn.close()
            return jsonify({"message": "Livestock added successfully", "id": new_id}), 201
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"error": "Livestock Tag ID already exists"}), 400

@app.route('/api/livestock/<int:id>', methods=['GET', 'DELETE', 'PUT'])
def handle_single_livestock(id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized. Please log in."}), 401
        
    tenant_id = session['tenant_id']
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    # Verify livestock belongs to this tenant
    cursor.execute("SELECT * FROM livestock WHERE id = ? AND tenant_id = ?", (id, tenant_id))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Livestock not found"}), 404
        
    if request.method == 'GET':
        conn.close()
        return jsonify(dict(row))
        
    elif request.method == 'DELETE':
        if session.get('role') != 'Admin':
            conn.close()
            return jsonify({"error": "Forbidden. Admin access required."}), 403
            
        cursor.execute("DELETE FROM livestock WHERE id = ? AND tenant_id = ?", (id, tenant_id))
        conn.commit()
        conn.close()
        return jsonify({"message": "Livestock deleted successfully"}), 200
        
    elif request.method == 'PUT':
        if session.get('role') != 'Admin':
            conn.close()
            return jsonify({"error": "Forbidden. Admin access required."}), 403
            
        data = request.json
        status = data.get('status', row['status'])
        weight = data.get('weight', row['weight'])
        pen_number = data.get('pen_number', row['pen_number'])
        
        cursor.execute("""
            UPDATE livestock 
            SET status = ?, weight = ?, pen_number = ?
            WHERE id = ? AND tenant_id = ?
        """, (status, float(weight), pen_number, id, tenant_id))
        conn.commit()
        conn.close()
        return jsonify({"message": "Livestock updated successfully"}), 200

@app.route('/api/drugs', methods=['GET', 'POST'])
def handle_drugs():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized. Please log in."}), 401
        
    tenant_id = session['tenant_id']
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'GET':
        cursor.execute("SELECT * FROM drugs WHERE tenant_id = ? ORDER BY name ASC", (tenant_id,))
        rows = cursor.fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
        
    elif request.method == 'POST':
        if session.get('role') != 'Admin':
            conn.close()
            return jsonify({"error": "Forbidden. Admin access required."}), 403
            
        data = request.json
        required = ('name', 'active_ingredient', 'drug_class', 'classification', 
                    'withdrawal_meat_days', 'withdrawal_milk_days', 'withdrawal_eggs_days', 
                    'mrl_limit', 'half_life_hours')
        if not data or not all(k in data for k in required):
            conn.close()
            return jsonify({"error": "Missing required fields"}), 400
            
        try:
            cursor.execute("""
                INSERT INTO drugs (name, active_ingredient, drug_class, classification, 
                                   withdrawal_meat_days, withdrawal_milk_days, withdrawal_eggs_days, 
                                   mrl_limit, half_life_hours, tenant_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (data['name'], data['active_ingredient'], data['drug_class'], data['classification'],
                  int(data['withdrawal_meat_days']), int(data['withdrawal_milk_days']), int(data['withdrawal_eggs_days']),
                  float(data['mrl_limit']), float(data['half_life_hours']), tenant_id))
            conn.commit()
            new_id = cursor.lastrowid
            conn.close()
            return jsonify({"message": "Drug added successfully", "id": new_id}), 201
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"error": "Drug name already exists"}), 400

@app.route('/api/treatments', methods=['GET', 'POST'])
def handle_treatments():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized. Please log in."}), 401
        
    tenant_id = session['tenant_id']
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'GET':
        cursor.execute("""
            SELECT t.id, t.livestock_id, t.drug_id, t.dosage_mg_per_kg, t.total_mg, t.route, 
                   t.start_date, t.end_date, t.vet_name, 
                   l.tag_id as livestock_tag, l.species as livestock_species, l.weight as livestock_weight,
                   d.name as drug_name, d.drug_class, d.withdrawal_meat_days, d.withdrawal_milk_days, d.withdrawal_eggs_days
            FROM treatments t
            JOIN livestock l ON t.livestock_id = l.id
            JOIN drugs d ON t.drug_id = d.id
            WHERE t.tenant_id = ?
            ORDER BY t.start_date DESC
        """, (tenant_id,))
        rows = cursor.fetchall()
        
        treatments = []
        for r in rows:
            treatment = dict(r)
            end_dt = datetime.strptime(treatment['end_date'], '%Y-%m-%d %H:%M:%S')
            w_days = max(treatment['withdrawal_meat_days'], treatment['withdrawal_milk_days'], treatment['withdrawal_eggs_days'])
            clear_dt = end_dt + timedelta(days=w_days)
            treatment['clearance_date'] = clear_dt.strftime('%Y-%m-%d %H:%M:%S')
            
            now = datetime.now()
            if end_dt < now <= clear_dt:
                treatment['withdrawal_remaining_seconds'] = max(0, int((clear_dt - now).total_seconds()))
                treatment['status'] = 'In Withdrawal'
            elif now <= end_dt:
                treatment['withdrawal_remaining_seconds'] = w_days * 86400
                treatment['status'] = 'Active Treatment'
            else:
                treatment['withdrawal_remaining_seconds'] = 0
                treatment['status'] = 'Cleared'
                
            treatments.append(treatment)
            
        conn.close()
        return jsonify(treatments)
        
    elif request.method == 'POST':
        if session.get('role') != 'Admin':
            conn.close()
            return jsonify({"error": "Forbidden. Admin access required."}), 403
            
        data = request.json
        required = ('livestock_id', 'drug_id', 'dosage_mg_per_kg', 'route', 'start_date', 'end_date', 'vet_name')
        if not data or not all(k in data for k in required):
            conn.close()
            return jsonify({"error": "Missing required fields"}), 400
            
        # Verify animal matches tenant
        cursor.execute("SELECT weight FROM livestock WHERE id = ? AND tenant_id = ?", (data['livestock_id'], tenant_id))
        animal = cursor.fetchone()
        if not animal:
            conn.close()
            return jsonify({"error": "Livestock not found"}), 404
            
        # Verify drug matches tenant
        cursor.execute("SELECT id FROM drugs WHERE id = ? AND tenant_id = ?", (data['drug_id'], tenant_id))
        drug = cursor.fetchone()
        if not drug:
            conn.close()
            return jsonify({"error": "Drug sheet reference not found"}), 404
            
        weight = animal['weight']
        dosage = float(data['dosage_mg_per_kg'])
        total_mg = dosage * weight
        
        cursor.execute("""
            INSERT INTO treatments (livestock_id, drug_id, dosage_mg_per_kg, total_mg, route, start_date, end_date, vet_name, tenant_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (int(data['livestock_id']), int(data['drug_id']), dosage, total_mg, data['route'], 
              data['start_date'], data['end_date'], data['vet_name'], tenant_id))
        
        cursor.execute("UPDATE livestock SET status = 'Treated' WHERE id = ? AND tenant_id = ?", (data['livestock_id'], tenant_id))
        
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        
        update_livestock_statuses(tenant_id)
        
        return jsonify({"message": "Treatment logged successfully", "id": new_id}), 201

@app.route('/api/treatments/<int:id>/decay')
def handle_decay(id):
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized. Please log in."}), 401
        
    tenant_id = session['tenant_id']
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT t.dosage_mg_per_kg, t.end_date, 
               d.name as drug_name, d.mrl_limit, d.half_life_hours, 
               d.withdrawal_meat_days, d.withdrawal_milk_days, d.withdrawal_eggs_days,
               l.tag_id as livestock_tag
        FROM treatments t
        JOIN drugs d ON t.drug_id = d.id
        JOIN livestock l ON t.livestock_id = l.id
        WHERE t.id = ? AND t.tenant_id = ?
    """, (id, tenant_id))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return jsonify({"error": "Treatment not found"}), 404
        
    dosage = row['dosage_mg_per_kg']
    mrl = row['mrl_limit']
    half_life = row['half_life_hours']
    withdrawal_days = max(row['withdrawal_meat_days'], row['withdrawal_milk_days'], row['withdrawal_eggs_days'])
    
    c_0 = dosage * 1000.0
    duration_hours = max(48, withdrawal_days * 24)
    if duration_hours > 720:
        duration_hours = 720
        
    step = max(1, int(duration_hours / 20))
    
    points = []
    end_dt = datetime.strptime(row['end_date'], '%Y-%m-%d %H:%M:%S')
    
    for h in range(0, int(duration_hours) + step, step):
        concentration = c_0 * (0.5 ** (h / half_life))
        time_label = (end_dt + timedelta(hours=h)).strftime('%m-%d %H:%M')
        points.append({
            "hour": h,
            "time_label": time_label,
            "concentration": round(concentration, 2),
            "mrl": mrl
        })
        
    return jsonify({
        "drug_name": row['drug_name'],
        "livestock_tag": row['livestock_tag'],
        "mrl_limit": mrl,
        "half_life_hours": half_life,
        "withdrawal_days": withdrawal_days,
        "end_date": row['end_date'],
        "points": points
    })

@app.route('/api/analytics')
def handle_analytics():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized. Please log in."}), 401
        
    tenant_id = session['tenant_id']
    update_livestock_statuses(tenant_id)
    
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    # 1. Livestock Status Counter
    cursor.execute("SELECT status, COUNT(*) as count FROM livestock WHERE tenant_id = ? GROUP BY status", (tenant_id,))
    status_rows = cursor.fetchall()
    status_counts = {"Healthy": 0, "Treated": 0, "In Withdrawal": 0, "Quarantine": 0}
    for r in status_rows:
        if r['status'] in status_counts:
            status_counts[r['status']] = r['count']
            
    # Total animals
    cursor.execute("SELECT COUNT(*), SUM(weight) FROM livestock WHERE tenant_id = ?", (tenant_id,))
    total_row = cursor.fetchone()
    total_animals = total_row[0] or 0
    total_weight = total_row[1] or 0.0
    
    # 2. Under Withdrawal Listing
    cursor.execute("SELECT id, tag_id, species, pen_number, status FROM livestock WHERE status = 'In Withdrawal' AND tenant_id = ?", (tenant_id,))
    iw_rows = cursor.fetchall()
    withdrawal_alerts = []
    
    now = datetime.now()
    for row in iw_rows:
        cursor.execute("""
            SELECT t.end_date, d.name as drug_name, d.withdrawal_meat_days, d.withdrawal_milk_days, d.withdrawal_eggs_days
            FROM treatments t
            JOIN drugs d ON t.drug_id = d.id
            WHERE t.livestock_id = ? AND t.tenant_id = ?
            ORDER BY t.end_date DESC LIMIT 1
        """, (row['id'], tenant_id))
        t_row = cursor.fetchone()
        if t_row:
            end_dt = datetime.strptime(t_row['end_date'], '%Y-%m-%d %H:%M:%S')
            w_days = max(t_row['withdrawal_meat_days'], t_row['withdrawal_milk_days'], t_row['withdrawal_eggs_days'])
            clear_dt = end_dt + timedelta(days=w_days)
            remaining_seconds = max(0, int((clear_dt - now).total_seconds()))
            
            withdrawal_alerts.append({
                "tag_id": row['tag_id'],
                "species": row['species'],
                "pen_number": row['pen_number'],
                "drug_name": t_row['drug_name'],
                "clearance_date": clear_dt.strftime('%Y-%m-%d %H:%M:%S'),
                "remaining_seconds": remaining_seconds
            })
            
    # 3. Compliance Rate
    cursor.execute("SELECT COUNT(*) FROM treatments WHERE tenant_id = ?", (tenant_id,))
    total_treatments = cursor.fetchone()[0] or 0
    
    if total_treatments > 0:
        cursor.execute("""
            SELECT t.end_date, d.withdrawal_meat_days, d.withdrawal_milk_days, d.withdrawal_eggs_days
            FROM treatments t
            JOIN drugs d ON t.drug_id = d.id
            WHERE t.tenant_id = ?
        """, (tenant_id,))
        t_list = cursor.fetchall()
        cleared_count = 0
        for t in t_list:
            end_dt = datetime.strptime(t['end_date'], '%Y-%m-%d %H:%M:%S')
            w_days = max(t['withdrawal_meat_days'], t['withdrawal_milk_days'], t['withdrawal_eggs_days'])
            clear_dt = end_dt + timedelta(days=w_days)
            if clear_dt <= now:
                cleared_count += 1
        compliance_rate = round((cleared_count / len(t_list)) * 100, 1) if t_list else 100.0
    else:
        compliance_rate = 100.0

    # 4. AMU Index (mg active ingredient / kg livestock) in past 30 days
    thirty_days_ago = (now - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        SELECT SUM(total_mg) FROM treatments 
        WHERE start_date >= ? AND tenant_id = ?
    """, (thirty_days_ago, tenant_id))
    amu_sum = cursor.fetchone()[0] or 0.0
    
    amu_index = round(amu_sum / total_weight, 2) if total_weight > 0 else 0.0

    # 5. Usage by Drug Class (mg)
    cursor.execute("""
        SELECT d.drug_class, SUM(t.total_mg) as total_mg
        FROM treatments t
        JOIN drugs d ON t.drug_id = d.id
        WHERE t.tenant_id = ?
        GROUP BY d.drug_class
    """, (tenant_id,))
    class_rows = cursor.fetchall()
    drug_class_usage = {r['drug_class']: round(r['total_mg'], 2) for r in class_rows}

    # 6. Usage by Critically Important classification
    cursor.execute("""
        SELECT d.classification, SUM(t.total_mg) as total_mg
        FROM treatments t
        JOIN drugs d ON t.drug_id = d.id
        WHERE t.tenant_id = ?
        GROUP BY d.classification
    """, (tenant_id,))
    classification_rows = cursor.fetchall()
    class_usage = {r['classification']: round(r['total_mg'], 2) for r in classification_rows}

    # 7. Monthly Treatment Counts & AMU (past 6 months)
    monthly_stats = []
    for i in range(5, -1, -1):
        month_start = (now - timedelta(days=30 * (i + 1)))
        month_end = (now - timedelta(days=30 * i))
        m_start_str = month_start.strftime('%Y-%m-%d %H:%M:%S')
        m_end_str = month_end.strftime('%Y-%m-%d %H:%M:%S')
        month_label = month_end.strftime('%b %Y')
        
        cursor.execute("""
            SELECT COUNT(*), SUM(total_mg) FROM treatments
            WHERE start_date >= ? AND start_date < ? AND tenant_id = ?
        """, (m_start_str, m_end_str, tenant_id))
        r = cursor.fetchone()
        monthly_stats.append({
            "month": month_label,
            "treatments_count": r[0] or 0,
            "amu_mg": round(r[1] or 0.0, 1)
        })

    conn.close()
    
    return jsonify({
        "status_counts": status_counts,
        "total_animals": total_animals,
        "total_weight_kg": round(total_weight, 1),
        "compliance_rate": compliance_rate,
        "amu_index": amu_index,
        "total_amu_mg_30d": round(amu_sum, 1),
        "withdrawal_alerts": withdrawal_alerts,
        "drug_class_usage": drug_class_usage,
        "classification_usage": class_usage,
        "monthly_stats": monthly_stats
    })

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
