from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import mysql.connector
import random
import smtplib
from email.mime.text import MIMEText
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
import os
from werkzeug.utils import secure_filename
app = Flask(__name__)
app.secret_key = 'care_bridge_2026'
UPLOAD_FOLDER = 'static/uploads/camps'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# MySQL Configuration
db_config = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", "tiger"),
    "database": os.environ.get("DB_NAME", "care_bridge")
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['POST'])
def signup():
    data = request.form
    fullname = data.get('fullname')
    email = data.get('email')
    password_value = data.get('password_value', '').strip()
    hashed_password = generate_password_hash(password_value)
    role = data.get('role')
    
    otp = str(random.randint(100000, 999999))
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Insert into common users table
        query = "INSERT INTO users (fullname, email, password, otp_code, role, is_verified) VALUES (%s, %s, %s, %s, %s, 0)"
        cursor.execute(query, (fullname, email, hashed_password, otp, role))
        
        # 2. If it's a hospital, insert into hospitals table too
        if role == 'hospital':
            cursor.execute("""
                INSERT INTO hospitals (hospital_name, email, password, license_id, city, hospital_type, contact_no, status, otp_code) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'Pending', %s)
            """, (fullname, email, hashed_password, data.get('license_id'), data.get('city'), 
                  data.get('hospital_type'), data.get('contact_no'), otp))
        
        conn.commit()
        send_otp_email(email, otp)
        return jsonify({"status": "otp_sent", "message": "OTP sent to your email!"})
            
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": str(e)})
    finally:
        cursor.close()
        conn.close()

# Email Function
def send_otp_email(receiver_email, otp):
    sender_email = "siddhi.salvi2006@gmail.com"
    app_password = "pnhndyzaltegmsxg" # Paste your key here
    
    msg = MIMEText(f"Your MediHub Verification Code is: {otp}")
    msg['Subject'] = 'MediHub OTP Verification'
    msg['From'] = sender_email
    msg['To'] = receiver_email

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(sender_email, app_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())

def send_approval_email(receiver_email, hospital_name):
    sender_email = "siddhi.salvi2006@gmail.com"
    app_password = "pnhndyzaltegmsxg" 
    
    body = f"Hello {hospital_name},\n\nYour MediHub profile has been approved by our administration. You can now log in to your dashboard to manage your inventory and camps.\n\nWelcome to the network!"
    msg = MIMEText(body)
    msg['Subject'] = 'MediHub Account Approved'
    msg['From'] = sender_email
    msg['To'] = receiver_email

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(sender_email, app_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())

def send_rejection_email(receiver_email, hospital_name, reason):
    sender_email = "siddhi.salvi2006@gmail.com"
    app_password = "pnhndyzaltegmsxg"
    
    body = f"Hello {hospital_name},\n\nUnfortunately, your registration request on MediHub was not approved.\n\nReason: {reason}\n\nPlease contact support if you believe this is an error."
    msg = MIMEText(body)
    msg['Subject'] = 'MediHub Registration Update'
    msg['From'] = sender_email
    msg['To'] = receiver_email

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(sender_email, app_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())

@app.route('/verify', methods=['POST'])
def verify():
    data = request.json
    email = data.get('email')
    user_otp = data.get('otp')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT role FROM users WHERE email = %s AND otp_code = %s", (email, user_otp))
    user = cursor.fetchone()
    
    if user:
        cursor.execute("UPDATE users SET is_verified = 1 WHERE email = %s", (email,))
        if user['role'] == 'hospital':
            cursor.execute("UPDATE hospitals SET is_verified = 1 WHERE email = %s", (email,))
        
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success", "message": "Email verified successfully!"})
    
    return jsonify({"status": "error", "message": "Incorrect OTP. Please try again."})

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('fullname', '').strip()
    password = request.form.get('password', '').strip()
    print(f"DEBUG: Trying to login with: {username}")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Check general users table first
    cursor.execute("SELECT * FROM users WHERE fullname = %s", (username,))
    user = cursor.fetchone()

    if not user:
        print("DEBUG: User not found in database!")
        return jsonify({"status": "error", "message": "Invalid credentials."})

    print(f"DEBUG: Found user. Verified status: {user['is_verified']}")
    
    if not check_password_hash(user['password'], password):
        print("DEBUG: Password hash mismatch!")
        return jsonify({"status": "error", "message": "Invalid credentials."})

    if user['is_verified'] == 0:
        return jsonify({"status": "error", "message": "Please verify your email first."})

    session.clear()
    session['user_id'] = user['id']
    session['role'] = user['role']
    session['username'] = user['fullname']

    # Special logic for Hospital Approval
    if user['role'] == 'hospital':
        cursor.execute("SELECT id, status FROM hospitals WHERE email = %s", (user['email'],))
        hosp_data = cursor.fetchone()
        
        if hosp_data['status'] == 'Pending':
            return jsonify({"status": "error", "message": "Account pending admin approval."})
        elif hosp_data['status'] == 'Rejected':
            return jsonify({"status": "error", "message": "Account rejected by admin."})
        
        session['hospital_id'] = hosp_data['id'] # Important for "The Loop"

    return jsonify({"status": "success","message": "Welcome back!", "redirect": url_for(f"{user['role']}_dashboard")})

@app.route('/user_dashboard')
def user_dashboard():
    if session.get('role') == 'user':
        return render_template('dashboard.html')
    return redirect(url_for('index'))

@app.route('/hospital_dashboard')
def hospital_dashboard():
    if session.get('role') == 'hospital':
        return render_template('hospital.html', hospital_id=session.get('hospital_id'))
    return redirect(url_for('index'))

@app.route('/admin_dashboard')
def admin_dashboard():
    if session.get('role') == 'admin':
        return render_template('admin.html')
    return redirect(url_for('index'))

@app.route('/admin/get_pending_hospitals')
def get_pending_hospitals():
    if session.get('role') != 'admin':
        return jsonify([])

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # We only show hospitals that have verified their email but are still 'Pending'
    cursor.execute("""
        SELECT id, hospital_name, license_id, city, hospital_type, email 
        FROM hospitals 
        WHERE status = 'Pending' AND is_verified = 1
    """)
    rows = cursor.fetchall()
    
    # Mapping database names to match your JavaScript keys
    hospitals = []
    for row in rows:
        hospitals.append({
            "id": row['id'],
            "hospitalName": row['hospital_name'],
            "licenseId": row['license_id'],
            "city": row['city'],
            "type": row['hospital_type'],
            "email": row['email']
        })
    
    cursor.close()
    conn.close()
    return jsonify(hospitals)

@app.route('/api/hospital_decision/<int:hosp_id>', methods=['POST'])
def hospital_decision(hosp_id):
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "Unauthorized"})

    data = request.json
    action = data.get('action') 
    reason = data.get('reason', '')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # 1. Get hospital details first (we need email for deletion/contact)
        cursor.execute("SELECT hospital_name, email FROM hospitals WHERE id = %s", (hosp_id,))
        hospital = cursor.fetchone()

        if not hospital:
            return jsonify({"status": "error", "message": "Hospital not found."})

        if action == 'approve':
            # Simply update status
            cursor.execute("UPDATE hospitals SET status = 'Approved' WHERE id = %s", (hosp_id,))
            send_approval_email(hospital['email'], hospital['hospital_name'])
            msg = "Hospital Approved Successfully!"
        
        elif action == 'reject':
            send_rejection_email(hospital['email'], hospital['hospital_name'], reason)
    
            # SAFETY SHIELD: Only delete if it's a hospital role
            cursor.execute("DELETE FROM users WHERE email = %s AND role = 'hospital'", (hospital['email'],))
            cursor.execute("DELETE FROM hospitals WHERE id = %s", (hosp_id,))
    
            msg = "Hospital Rejected & Data Removed."

        conn.commit()
        return jsonify({"status": "success", "message": msg})
    
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": str(e)})
    finally:
        cursor.close()
        conn.close()

@app.route('/appointment')
def appointment():
    # This will look for organ_donation.html in your 'templates' folder
    return render_template('appointment.html')

@app.route('/hospital/add_doctor', methods=['POST'])
def add_doctor():
    if session.get('role') != 'hospital':
        return jsonify({"status": "error", "message": "Unauthorized"})
    
    data = request.json
    hospital_id = session.get('hospital_id') # Ensure you store this in session during login
    
    # Convert list of days to a single string: "Mon,Tue,Wed"
    days_str = ",".join(data.get('days', []))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """INSERT INTO doctors (hospital_id, name, department, availability_days, 
               from_time, to_time, max_patients, status) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'Pending')"""
    
    cursor.execute(query, (hospital_id, data['doctor_name'], data['department'], 
                          days_str, data['from_time'], data['to_time'], data['max_patients']))
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({"status": "success", "message": "Doctor submitted for Admin approval!"})

@app.route('/admin/get_pending_doctors')
def get_pending_doctors():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT d.id, d.name, h.hospital_name, d.department as specialization, 
               'N/A' as experience, 'N/A' as license_no 
        FROM doctors d 
        JOIN hospitals h ON d.hospital_id = h.id 
        WHERE d.status = 'Pending'
    """)
    doctors = cursor.fetchall()
    return jsonify(doctors)

@app.route('/api/handle_doctor/<int:doc_id>', methods=['POST'])
def handle_doctor(doc_id):
    action = request.json.get('action') # 'approve' or 'reject'
    new_status = 'Approved' if action == 'approve' else 'Rejected'
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE doctors SET status = %s WHERE id = %s", (new_status, doc_id))
    conn.commit()
    return jsonify({"status": "success", "message": f"Doctor {new_status}"})

@app.route('/api/get_approved_doctors')
def get_approved_doctors():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # Ensure d.id is selected so the frontend can use it for booking
    cursor.execute("""
        SELECT d.id, h.hospital_name as hospital, d.name, d.department, 
               d.availability_days as days, d.from_time, d.to_time
        FROM doctors d
        JOIN hospitals h ON d.hospital_id = h.id
        WHERE d.status = 'Approved'
    """)
    data = cursor.fetchall()
    
    formatted_docs = []
    for doc in data:
        # We must convert the database format into the JSON format your frontend expects
        formatted_docs.append({
            "id": doc['id'], 
            "hospital": doc['hospital'],
            "name": doc['name'],
            "department": doc['department'],
            "availability": [{"day": d.strip(), "from": str(doc['from_time']), "to": str(doc['to_time'])} 
                             for d in doc['days'].split(',')]
        })
    return jsonify(formatted_docs)

@app.route('/hospital/get_my_doctors')
def get_my_doctors():
    hosp_id = session.get('hospital_id')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # Fetch all doctors belonging to THIS hospital
    cursor.execute("SELECT * FROM doctors WHERE hospital_id = %s", (hosp_id,))
    doctors = cursor.fetchall()
    
    # Convert TIME to string for JSON
    for doc in doctors:
        doc['from_time'] = str(doc['from_time'])
        doc['to_time'] = str(doc['to_time'])
        
    return jsonify(doctors)

from mysql.connector import IntegrityError

@app.route('/api/book_appointment', methods=['POST'])
def book_appointment():
    data = request.json

    if 'doctor_id' not in data:
        return jsonify({"status": "error", "message": "Missing doctor_id"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT hospital_id FROM doctors WHERE id = %s", (data['doctor_id'],))
    result = cursor.fetchone()

    if not result:
        return jsonify({"status": "error", "message": "Doctor not found"}), 404

    hosp_id = result['hospital_id']

    try:
        query = """INSERT INTO appointments 
                   (doctor_id, user_id, hospital_id, patient_name, patient_age, id_proof, appointment_date, appointment_time) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""

        cursor.execute(query, (
            data['doctor_id'], 
            session.get('user_id'), 
            hosp_id, 
            data['patient_name'], 
            data['age'], 
            data['id_proof'], 
            data['date'], 
            data['time']
        ))

        conn.commit()

        return jsonify({
            "status": "success",
            "message": "Appointment Booked Successfully!"
        })

    except IntegrityError:
        return jsonify({
            "status": "error",
            "message": "This slot is already booked. Please choose another time."
        }), 409

@app.route('/hospital/get_attendees')
def get_attendees():
    hosp_id = session.get('hospital_id')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # We join with doctors to get the names and departments
    cursor.execute("""
        SELECT a.patient_name, a.patient_age, a.id_proof, 
               a.appointment_date, a.appointment_time,
               d.name as doctor_name, d.department 
        FROM appointments a 
        JOIN doctors d ON a.doctor_id = d.id 
        WHERE a.hospital_id = %s
        ORDER BY a.appointment_date DESC
    """, (hosp_id,))
    
    attendees = cursor.fetchall()

    # CRITICAL: Convert SQL Date/Time to String for JSON compatibility
    for row in attendees:
        row['appointment_date'] = str(row['appointment_date'])
        row['appointment_time'] = str(row['appointment_time'])
    
    return jsonify(attendees)

import csv
from io import StringIO
from flask import make_response

@app.route('/hospital/download_attendees')
def download_attendees():
    hospital_id = session.get('hospital_id')
    dept = request.args.get('department')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = """
        SELECT a.patient_name, d.name as doctor_name, d.department, a.appointment_date, a.patient_age
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.hospital_id = %s
    """
    params = [hospital_id]

    # Only add the AND clause if a specific department is selected
    if dept and dept != 'all':
        query += " AND d.department = %s"
        params.append(dept)
        
    cursor.execute(query, params)
    rows = cursor.fetchall()

    # Create CSV in memory
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Patient Name', 'Doctor', 'Department', 'Date', 'Age'])
    for row in rows:
        cw.writerow([row['patient_name'], row['doctor_name'], row['department'], row['appointment_date'], row['patient_age']])
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=attendees.csv"
    output.headers["Content-type"] = "text/csv"
    return output


# --- USER DASHBOARD: View Approved Camps ---
@app.route('/health_camps')
def health_camps():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # We only want camps approved by the Admin
        query = "SELECT * FROM health_camps WHERE status = 'Approved' ORDER BY camp_date ASC"
        cursor.execute(query)
        camps = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # This renders the cards for the user
        return render_template('health_camps.html', camps=camps)
        
    except Exception as e:
        print(f"Error fetching camps: {e}")
        return "Database Error", 500

@app.route('/api/add_camp', methods=['POST'])
def add_camp():
    hosp_id = session.get('hospital_id')
    
    # Extract data from request.form (not request.json)
    name = request.form.get('name')
    ctype = request.form.get('type')
    date = request.form.get('date')
    address = request.form.get('address')
    
    file = request.files.get('image')
    filename = secure_filename(file.filename) if file else "default.jpg"
    
    if file:
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO health_camps (hospital_id, camp_name, camp_type, camp_date, address, image_path, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'Pending')
    """, (hosp_id, name, ctype, date, address, filename))
    conn.commit()
    return jsonify({"status": "success"})

# --- ADMIN: Get & Handle Camps ---
@app.route('/admin/get_pending_camps')
def get_pending_camps():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT c.*, h.hospital_name FROM health_camps c JOIN hospitals h ON c.hospital_id = h.id WHERE c.status = 'Pending'")
    return jsonify(cursor.fetchall())

@app.route('/admin/handle_camp/<int:camp_id>', methods=['POST'])
def handle_camp(camp_id):
    try:
        data = request.get_json()
        raw_action = data.get('action') # 'approved' or 'rejected'
        
        # Format the string to match your SQL ENUM ('Approved', 'Rejected')
        formatted_action = raw_action.capitalize() 

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Execution
        cursor.execute("UPDATE health_camps SET status = %s WHERE id = %s", (formatted_action, camp_id))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({"status": "success", "message": "Status updated"})
        
    except Exception as e:
        print(f"ERROR: {e}") # This will show in your black terminal window
        return jsonify({"status": "error", "message": str(e)}), 500

# --- USER: View & Register ---
@app.route('/health_camps_page')
def health_camps_page():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM health_camps WHERE status = 'Approved'")
    camps = cursor.fetchall()
    return render_template('health_camp.html', camps=camps)

@app.route('/api/register_user', methods=['POST'])
def register_user():
    data = request.json
    # Capture the user_id from the session
    user_id = session.get('user_id') 
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO camp_registrations (camp_id, user_id, full_name, phone, email, address)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (data['camp_id'], user_id, data['name'], data['phone'], data['email'], data['address']))
    conn.commit()
    return jsonify({"status": "success"})

# --- HOSPITAL: View My Camp Registrations ---
@app.route('/hospital/get_camp_attendees')
def get_camp_attendees():
    hosp_id = session.get('hospital_id')
    camp_filter = request.args.get('camp_id') # Get filter from URL
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = """
        SELECT r.*, c.camp_name 
        FROM camp_registrations r
        JOIN health_camps c ON r.camp_id = c.id
        WHERE c.hospital_id = %s
    """
    params = [hosp_id]
    
    if camp_filter and camp_filter != 'all':
        query += " AND c.id = %s"
        params.append(camp_filter)
        
    cursor.execute(query, tuple(params))
    attendees = cursor.fetchall()
    return jsonify(attendees)

@app.route('/hospital/get_my_camps')
def get_my_camps():
    hosp_id = session.get('hospital_id')
    if not hosp_id:
        return jsonify([])
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # This pulls all camps created by THIS hospital
    cursor.execute("SELECT * FROM health_camps WHERE hospital_id = %s ORDER BY created_at DESC", (hosp_id,))
    camps = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(camps)

from flask import Response

@app.route('/hospital/download_attendees_csv')
def download_attendees_csv():
    hosp_id = session.get('hospital_id')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT c.camp_name, r.full_name, r.phone, r.email, r.address, r.registration_date 
        FROM camp_registrations r
        JOIN health_camps c ON r.camp_id = c.id
        WHERE c.hospital_id = %s
    """, (hosp_id,))
    rows = cursor.fetchall()

    def generate():
        data = StringIO()
        writer = csv.writer(data)
        writer.writerow(['Camp Name', 'Attendee Name', 'Phone', 'Email', 'Address', 'Date'])
        yield data.getvalue()
        data.seek(0)
        data.truncate(0)

        for row in rows:
            writer.writerow([row['camp_name'], row['full_name'], row['phone'], row['email'], row['address'], row['registration_date']])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

    response = Response(generate(), mimetype='text/csv')
    response.headers.set("Content-Disposition", "attachment", filename="attendees.csv")
    return response

@app.route('/vaccination')
def vaccination():
    return render_template('vaccination.html')

@app.route('/hospital/add_vaccine_center', methods=['POST'])
def add_vaccine_center():
    if 'hospital_id' not in session:
        return jsonify({"message": "Unauthorized access"}), 403

    data = request.get_json()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO vaccination_centers
        (hospital_id, center_name, vaccine_type, slots_available, city, address, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'Pending')
    """, (
        session.get('hospital_id'),   # ✅ CORRECT
        data.get('name'),
        data.get('vaccine_type'),
        data.get('slots'),
        data.get('city'),
        data.get('address')
    ))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Center submitted for admin approval!"}), 200


# Route to fetch pending vaccination centers for Admin
@app.route('/admin/get_pending_vaccination')
def get_pending_vaccination():
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify([]), 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT 
            vc.id,
            vc.center_name,
            vc.vaccine_type,
            vc.slots_available,
            vc.city,
            vc.address,
            h.hospital_name
        FROM vaccination_centers vc
        JOIN hospitals h ON vc.hospital_id = h.id
        WHERE vc.status = 'Pending'
    """

    cursor.execute(query)
    data = cursor.fetchall()

    cursor.close()
    conn.close()
    return jsonify(data)


# Route to Approve or Reject
@app.route('/admin/handle_vaccine_center/<int:center_id>', methods=['POST'])
def handle_vaccine_center(center_id):
    data = request.get_json()
    action = data.get('action') # 'Approved' or 'Rejected'
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE vaccination_centers SET status = %s WHERE id = %s", (action, center_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": f"Center has been {action}!"})

@app.route('/api/get_approved_vaccination_centers')
def get_approved_vaccination_centers():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Only fetch centers that are Approved and have at least 1 slot left
        query = """
            SELECT id, center_name, vaccine_type, slots_available, city, address 
            FROM vaccination_centers 
            WHERE status = 'Approved' AND slots_available > 0
        """
        cursor.execute(query)
        centers = cursor.fetchall()
        return jsonify(centers)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/book_vaccination', methods=['POST'])
def book_vaccination():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Insert booking
    cursor.execute("""
        INSERT INTO vaccination_bookings 
        (center_id, user_id, patient_name, patient_phone, vaccine_type, appointment_date)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (data['center_id'], session.get('user_id'), data['name'], data['phone'], data['type'], data['date']))
    
    # Decrease slot count
    cursor.execute("UPDATE vaccination_centers SET slots_available = slots_available - 1 WHERE id = %s", (data['center_id'],))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/hospital/get_vaccination_attendees')
def get_vaccination_attendees():
    hospital_id = session.get('hospital_id')

    if not hospital_id:
        return jsonify([])

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT 
            b.patient_name,
            b.patient_phone,
            b.vaccine_type,
            c.center_name
        FROM vaccination_bookings b
        JOIN vaccination_centers c ON b.center_id = c.id
        WHERE c.hospital_id = %s
        ORDER BY b.registration_date DESC
    """

    cursor.execute(query, (hospital_id,))
    data = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(data)

@app.route('/hospital/get_my_vaccination_centers')
def get_my_vaccination_centers():
    if 'user_id' not in session:
        return jsonify([]), 403
        
    hospital_id = session.get('hospital_id')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Fetch all centers submitted by this specific hospital
    cursor.execute("SELECT * FROM vaccination_centers WHERE hospital_id = %s", (hospital_id,))
    centers = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return jsonify(centers)

@app.route('/get_vaccine_history')
def get_vaccine_history():
    # Assuming you store the logged-in user's ID in the session
    user_id = session.get('user_id') 
    
    if not user_id:
        return jsonify([]) # Return empty if not logged in

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Only select bookings belonging to this specific user
    query = "SELECT * FROM vaccination_bookings WHERE user_id = %s ORDER BY appointment_date DESC"
    cursor.execute(query, (user_id,))
    history = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return jsonify(history)

@app.route('/hospital/download_vaccination_csv')
def download_vaccination_csv():
    hospital_id = session.get('hospital_id')
    vaccine = request.args.get('vaccine', 'all')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT 
            b.patient_name,
            b.patient_phone,
            b.vaccine_type,
            c.center_name
        FROM vaccination_bookings b
        JOIN vaccination_centers c ON b.center_id = c.id
        WHERE c.hospital_id = %s
    """
    params = [hospital_id]

    if vaccine != 'all':
        query += " AND b.vaccine_type = %s"
        params.append(vaccine)

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    # Create CSV
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(['Patient Name', 'Phone', 'Vaccine Type', 'Center Name'])
    for r in rows:
        writer.writerow([
            r['patient_name'],
            r['patient_phone'],
            r['vaccine_type'],
            r['center_name']
        ])

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=vaccination_attendees.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response

@app.route('/organ_donation')
def organ_donation():
    return render_template('organ_donation.html')

@app.route('/submit_pledge', methods=['POST'])
def submit_pledge():
    data = request.json # Receives data from JavaScript fetch
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        sql = """INSERT INTO donor_registry 
                (first_name, last_name, email, blood_group, age, mobile_number, 
                city, identity_type, identity_number, organs_pledged, emergency_contact_number, user_id) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        
        # We join the organs list into a single string for storage
        organs_string = ", ".join(data.get('organs', []))
        
        values = (
            data.get('fname'), data.get('lname'), data.get('email'),
            data.get('blood'), data.get('age'), data.get('mobile'),
            data.get('city'), data.get('idType'), data.get('idNum'),
            organs_string, data.get('emobile'),
            session.get('user_id') 
        )
        
        cursor.execute(sql, values)
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"message": "Pledge saved successfully!"}), 200
        
    except Exception as e:
        print(f"Database Error: {e}")
        return jsonify({"error": "Failed to save pledge to database"}), 500

@app.route('/admin/get_organ_donors')
def get_organ_donors():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Fetching from the 'donor_registry' table
        # We fetch specific fields to match the table headers in your admin panel
        query = """
            SELECT id, first_name, last_name, blood_group, 
                   organs_pledged, mobile_number, registration_date 
            FROM donor_registry 
            ORDER BY registration_date DESC
        """
        cursor.execute(query)
        organ_donors = cursor.fetchall()
        return jsonify(organ_donors)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/get_existing_donor')
def get_existing_donor():

    if 'user_id' not in session:
        return jsonify({"exists": False})

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT first_name, last_name, blood_group,
               organs_pledged, emergency_contact_number,
               identity_number
        FROM donor_registry
        WHERE user_id = %s
    """, (session['user_id'],))

    donor = cursor.fetchone()

    cursor.close()
    conn.close()

    if donor:
        return jsonify({
            "exists": True,
            "data": {
                "name": donor['first_name'] + " " + donor['last_name'],
                "blood": donor['blood_group'],
                "organs": donor['organs_pledged'],
                "emobile": donor['emergency_contact_number'],
                "idNum": donor['identity_number']
            }
        })

    return jsonify({"exists": False})

@app.route('/blood_bank')
def blood_bank():
    return render_template('blood_bank.html')

@app.route('/hospital/update_blood_bulk', methods=['POST'])
def update_blood_bulk():
    data = request.json
    print("Incoming data:", data)
    hospital_id = data.get('hospital_id')
    stock = data.get('stock')

    if not hospital_id or not stock:
        return jsonify({"error": "Invalid data"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        INSERT INTO blood_inventory (hospital_id, blood_group, units_available)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
        units_available = VALUES(units_available)
    """

    try:
        for item in stock:
            cursor.execute(query, (
                hospital_id,
                item['blood_group'],
                item['units']
            ))

        conn.commit()
        return jsonify({"message": "Inventory updated"})

    except Exception as e:
        conn.rollback()
        print("DB ERROR:", e)
        return jsonify({"error": "Database error"}), 500

    finally:
        cursor.close()
        conn.close()


@app.route('/get_inventory')
def get_inventory():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT h.hospital_name, b.blood_group, b.units_available
        FROM blood_inventory b
        JOIN hospitals h ON b.hospital_id = h.id
        ORDER BY b.units_available DESC
    """

    cursor.execute(query)
    rows = cursor.fetchall()

    for r in rows:
        units = r['units_available']
        if units >= 10:
            r['status'] = 'High'
        elif units >= 4:
            r['status'] = 'Limited'
        else:
            r['status'] = 'Critical'

    cursor.close()
    conn.close()

    return jsonify(rows)

@app.route('/search_banks')
def search_banks():
    city = request.args.get('city', '')
    bank_type = request.args.get('type', '')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Using LIKE %city% allows for partial matches (e.g., 'Mum' matches 'Mumbai')
    query = "SELECT * FROM blood_banks WHERE city LIKE %s"
    params = [f"%{city}%"]
    
    if bank_type:
        query += " AND category = %s"
        params.append(bank_type)
        
    cursor.execute(query, params)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(results)

@app.route('/register_donor', methods=['POST'])
def register_donor():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        INSERT INTO blood_donors (name, blood_group, city, phone)
        VALUES (%s, %s, %s, %s)
    """

    cursor.execute(query, (
        data['name'],
        data['group'],
        data['city'],
        data['phone']
    ))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Donor registered"})

@app.route('/admin/get_blood_donors')
def get_blood_donors():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Fetching from the 'donors' table
        cursor.execute("SELECT name, blood_group, city, phone, registered_at FROM blood_donors ORDER BY registered_at DESC")
        blood_donors = cursor.fetchall()
        return jsonify(blood_donors)
    except Exception as e:
        print("ERROR:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/nearest_hospitals')
def nearest_hospitals():
    return render_template('nearest_hospitals.html')

@app.route('/api/search_hospitals', methods=['POST'])
def search_hospitals():
    data = request.json
    city = data.get('city')
    types = data.get('types', []) # ['Government', 'Private']
    facilities = data.get('facilities', []) # ['has_icu', 'has_blood_bank']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = "SELECT * FROM nearesthospital WHERE status = 'ACTIVE'"
    params = []

    if city:
        query += " AND city LIKE %s"
        params.append(f"%{city}%")

    # Filter for Govt/Private
    if types:
        query += " AND hospital_type IN (" + ",".join(["%s"] * len(types)) + ")"
        params.extend(types)

    # Filter for Facilities (ICU, etc.)
    for f in facilities:
        # Whitelist columns to prevent injection
        if f in ['has_icu', 'has_blood_bank', 'has_maternity', 'has_dialysis', 'emergency_24x7']:
            query += f" AND {f} = 1"

    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True)