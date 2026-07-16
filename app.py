from flask import Flask, render_template, jsonify, request, session
import database
import sqlite3
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash
import math

app = Flask(__name__)
app.secret_key = 'super_secret_farm_key_for_residueguard_session_auth'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

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
    if not data or 'username' not in data or 'email' not in data or 'password' not in data:
        return jsonify({"error": "Missing username, email, or password"}), 400
        
    username = data['username'].strip()
    email = data['email'].strip()
    password = data['password']
    
    conn = database.get_db_connection()
    cursor = conn.cursor()
    # Require both username and email to match!
    cursor.execute("SELECT * FROM users WHERE username = ? AND email = ?", (username, email))
    user = cursor.fetchone()
    conn.close()
    
    if user and check_password_hash(user['password_hash'], password):
        session.permanent = True
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        session['tenant_id'] = user['tenant_id']
        return jsonify({
            "message": "Login successful",
            "user": {
                "username": user['username'],
                "role": user['role'],
                "email": user['email']
            }
        }), 200
        
    return jsonify({"error": "Invalid credentials. Please verify your username and email address."}), 401

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    if not data or 'username' not in data or 'password' not in data or 'email' not in data:
        return jsonify({"error": "Missing registration details"}), 400
        
    username = data['username'].strip()
    password = data['password']
    email = data['email'].strip()
    
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters long"}), 400
    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters long"}), 400
    if not email or '@' not in email or '.' not in email:
        return jsonify({"error": "Please enter a valid email address"}), 400
        
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    # Check if username exists
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return jsonify({"error": "Username already exists"}), 400
        
    # Check if email exists
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        return jsonify({"error": "Email address already registered"}), 400
        
    from werkzeug.security import generate_password_hash
    pw_hash = generate_password_hash(password)
    
    try:
        # Insert user with email and placeholder tenant_id = 0, then update it to match their new user ID
        cursor.execute("INSERT INTO users (username, email, password_hash, role, tenant_id) VALUES (?, ?, ?, 'Admin', 0)", (username, email, pw_hash))
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
        # Fetch email dynamically in case it changed or for session info
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT email FROM users WHERE id = ?", (session.get('user_id'),))
        row = cursor.fetchone()
        conn.close()
        
        email = row['email'] if row else None
        
        return jsonify({
            "username": session.get('username'),
            "role": session.get('role'),
            "email": email
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

def send_all_daily_emails():
    """
    Query all users in the system, compile their active alerts based on their tenant,
    and send the formatted daily summary report email.
    """
    import smtplib
    import os
    import re
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    # Get all users who have an email
    cursor.execute("SELECT id, username, email, tenant_id FROM users WHERE email IS NOT NULL AND email != ''")
    users = cursor.fetchall()
    
    if not users:
        conn.close()
        return "No users with registered email addresses found."
        
    emails_sent = 0
    log_messages = []
    
    # We will group by tenant_id to avoid querying alerts multiple times for the same tenant
    tenant_alerts = {}
    
    for user in users:
        username = user['username']
        user_email = user['email']
        tenant_id = user['tenant_id']
        
        # Ensure dynamic statuses are up-to-date
        update_livestock_statuses(tenant_id)
        
        if tenant_id not in tenant_alerts:
            # Query non-healthy livestock for this tenant
            cursor.execute("""
                SELECT id, tag_id, species, breed, pen_number, status 
                FROM livestock 
                WHERE status != 'Healthy' AND tenant_id = ?
                ORDER BY status DESC, tag_id ASC
            """, (tenant_id,))
            livestock_rows = cursor.fetchall()
            
            alerts = []
            now = datetime.now()
            for row in livestock_rows:
                # Get the latest treatment to display details
                cursor.execute("""
                    SELECT t.end_date, d.name as drug_name, d.withdrawal_meat_days, d.withdrawal_milk_days, d.withdrawal_eggs_days
                    FROM treatments t
                    JOIN drugs d ON t.drug_id = d.id
                    WHERE t.livestock_id = ? AND t.tenant_id = ?
                    ORDER BY t.end_date DESC LIMIT 1
                """, (row['id'], tenant_id))
                t_row = cursor.fetchone()
                
                drug_name = "N/A"
                clearance_date = "N/A"
                remaining_time = "N/A"
                
                if t_row:
                    drug_name = t_row['drug_name']
                    end_dt = datetime.strptime(t_row['end_date'], '%Y-%m-%d %H:%M:%S')
                    w_days = max(t_row['withdrawal_meat_days'], t_row['withdrawal_milk_days'], t_row['withdrawal_eggs_days'])
                    clear_dt = end_dt + timedelta(days=w_days)
                    clearance_date = clear_dt.strftime('%Y-%m-%d %H:%M:%S')
                    
                    if clear_dt > now:
                        diff = clear_dt - now
                        days = diff.days
                        hours = diff.seconds // 3600
                        remaining_time = f"{days}d {hours}h remaining"
                    else:
                        remaining_time = "Clearance reached"
                elif row['status'] == 'Quarantine':
                    remaining_time = "Manual Quarantine Active"
                    
                alerts.append({
                    "tag_id": row['tag_id'],
                    "species": row['species'],
                    "breed": row['breed'],
                    "pen_number": row['pen_number'],
                    "status": row['status'],
                    "drug_name": drug_name,
                    "clearance_date": clearance_date,
                    "remaining_time": remaining_time
                })
            tenant_alerts[tenant_id] = alerts
            
        alerts = tenant_alerts[tenant_id]
        
        # Build email content
        subject = f"[ResidueGuard] Daily Withdrawal & MRL Compliance Alert - {datetime.now().strftime('%Y-%m-%d')}"
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6; background-color: #f4f5f7; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; border: 1px solid #e1e4e8; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                <div style="background: linear-gradient(135deg, #0891b2, #0284c7); padding: 24px; color: #ffffff; text-align: center;">
                    <h2 style="margin: 0; font-size: 24px; font-weight: 700; letter-spacing: 0.5px;">ResidueGuard Alerts</h2>
                    <p style="margin: 4px 0 0 0; opacity: 0.9; font-size: 14px;">Daily Farm Compliance & Withdrawal Summary</p>
                </div>
                <div style="padding: 24px;">
                    <p style="font-size: 16px; margin-top: 0;">Hello <strong>{username}</strong>,</p>
                    <p>Below is your scheduled daily status report for tenant account <strong>#{tenant_id}</strong>. Please ensure all animals listed under withdrawal do not enter the commercial food supply chain until their respective clearance dates.</p>
        """
        
        if not alerts:
            html_content += """
                    <div style="background-color: #ecfdf5; border-left: 4px solid #10b981; padding: 16px; border-radius: 4px; margin: 20px 0;">
                        <h4 style="margin: 0; color: #065f46; font-size: 15px;">🎉 All Compliant</h4>
                        <p style="margin: 4px 0 0 0; color: #047857; font-size: 13px;">No animals are currently treated, in withdrawal, or quarantined. All livestock are eligible for standard transport and sale.</p>
                    </div>
            """
        else:
            html_content += f"""
                    <div style="background-color: #fffbeb; border-left: 4px solid #d97706; padding: 16px; border-radius: 4px; margin: 20px 0;">
                        <h4 style="margin: 0; color: #92400e; font-size: 15px;">⚠️ Active Warning Alerts ({len(alerts)})</h4>
                        <p style="margin: 4px 0 0 0; color: #b45309; font-size: 13px;">The following livestock require active withholding or quarantine monitoring.</p>
                    </div>
                    
                    <table style="width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 13px;">
                        <thead>
                            <tr style="background-color: #f8fafc; border-bottom: 2px solid #e2e8f0; text-align: left;">
                                <th style="padding: 10px; font-weight: 600;">Animal Tag</th>
                                <th style="padding: 10px; font-weight: 600;">Status</th>
                                <th style="padding: 10px; font-weight: 600;">Location</th>
                                <th style="padding: 10px; font-weight: 600;">Drug Used</th>
                                <th style="padding: 10px; font-weight: 600;">Withhold Info</th>
                            </tr>
                        </thead>
                        <tbody>
            """
            for alert in alerts:
                status_color = "#e11d48" if alert['status'] == 'Quarantine' else ("#d97706" if alert['status'] == 'In Withdrawal' else "#2563eb")
                status_bg = "#fff1f2" if alert['status'] == 'Quarantine' else ("#fffbeb" if alert['status'] == 'In Withdrawal' else "#eff6ff")
                
                html_content += f"""
                            <tr style="border-bottom: 1px solid #e2e8f0;">
                                <td style="padding: 12px 10px;"><strong>{alert['tag_id']}</strong><br><span style="color: #64748b; font-size: 11px;">{alert['species']} ({alert['breed']})</span></td>
                                <td style="padding: 12px 10px;"><span style="background-color: {status_bg}; color: {status_color}; padding: 3px 8px; border-radius: 12px; font-weight: 600; font-size: 11px;">{alert['status']}</span></td>
                                <td style="padding: 12px 10px;">{alert['pen_number']}</td>
                                <td style="padding: 12px 10px;">{alert['drug_name']}</td>
                                <td style="padding: 12px 10px;"><strong>{alert['remaining_time']}</strong><br><span style="color: #64748b; font-size: 10px;">Clearance: {alert['clearance_date']}</span></td>
                            </tr>
                """
            html_content += """
                        </tbody>
                    </table>
            """
            
        html_content += """
                    <div style="margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 15px; font-size: 12px; color: #64748b; text-align: center;">
                        <p>This is an automated warning message from your ResidueGuard portal.</p>
                        <p>&copy; 2026 ResidueGuard Ltd. All rights reserved.</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        smtp_sent = False
        smtp_error = ""
        
        smtp_host = os.environ.get("SMTP_HOST", "localhost")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_pass = os.environ.get("SMTP_PASSWORD", "")
        smtp_from = os.environ.get("SMTP_FROM", "alerts@residueguard.farm")
        
        if smtp_user:
            try:
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From'] = smtp_from
                msg['To'] = user_email
                msg.attach(MIMEText(html_content, 'html'))
                
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=5)
                if smtp_pass:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_from, [user_email], msg.as_string())
                server.quit()
                smtp_sent = True
            except Exception as e:
                smtp_error = str(e)
                
        # Write to log file ALWAYS as a local transaction receipt / visual fallback
        try:
            log_dir = os.path.dirname(database.DB_PATH)
            sent_emails_path = os.path.join(log_dir, 'sent_emails.log')
            with open(sent_emails_path, 'a', encoding='utf-8') as f:
                f.write(f"\n========================================\n")
                f.write(f"TIMESTAMP: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"TO: {username} <{user_email}>\n")
                f.write(f"SUBJECT: {subject}\n")
                f.write(f"SMTP SENT: {smtp_sent} (Error: {smtp_error if not smtp_sent else 'None'})\n")
                f.write(f"----------------------------------------\n")
                text_preview = re.sub('<[^<]+?>', '', html_content)
                text_preview = "\n".join([line.strip() for line in text_preview.splitlines() if line.strip()])
                f.write(text_preview)
                f.write(f"\n========================================\n")
        except Exception as log_ex:
            print("Failed to write sent email log:", log_ex)
            
        emails_sent += 1
        log_messages.append({
            "username": username,
            "email": user_email,
            "success": True,
            "smtp_sent": smtp_sent,
            "smtp_error": smtp_error
        })
        
    conn.close()
    return {
        "status": "success",
        "emails_processed": emails_sent,
        "details": log_messages
    }

@app.route('/api/send-alert-emails', methods=['POST'])
def handle_manual_email_alerts():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized. Please log in."}), 401
    
    result = send_all_daily_emails()
    if isinstance(result, str):
        return jsonify({"error": result}), 400
        
    return jsonify(result), 200

# Background Daemon Scheduler for Daily Email alerts
import threading
import time

def run_daily_email_scheduler():
    """
    Run an infinite loop in a background daemon thread that triggers email alerts
    every 24 hours.
    """
    while True:
        try:
            send_all_daily_emails()
        except Exception as e:
            print("Error in daily email scheduler:", e)
        time.sleep(24 * 3600)

scheduler_thread = threading.Thread(target=run_daily_email_scheduler, daemon=True)
scheduler_thread.start()

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
