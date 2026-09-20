import os
import io
import sqlite3
import socket
import qrcode
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'duet_portal_ultra_secure_key_2026'

# Upload Folders Config
UPLOAD_FOLDER = os.path.join('static', 'uploads')
RESULTS_FOLDER = os.path.join('static', 'results')
PAYMENTS_FOLDER = os.path.join('static', 'payments')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESULTS_FOLDER'] = RESULTS_FOLDER
app.config['PAYMENTS_FOLDER'] = PAYMENTS_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)
os.makedirs(PAYMENTS_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Laptop ka Local Network IP nikalne ke liye function
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

# ------------------ DATABASE INITIALIZATION ------------------
def init_db():
    conn = sqlite3.connect('duet_multiport.db')
    cursor = conn.cursor()
    
    # 1. Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            full_name TEXT,
            roll_no TEXT UNIQUE,
            department TEXT,
            profile_pic TEXT DEFAULT 'default.png',
            status TEXT DEFAULT 'Pending'
        )
    ''')
    
    # 2. Subjects Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department TEXT NOT NULL,
            subject_code TEXT NOT NULL,
            subject_name TEXT NOT NULL,
            credit_hours INTEGER DEFAULT 3
        )
    ''')

    # 3. Attendance Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            subject TEXT,
            date TEXT,
            status TEXT,
            FOREIGN KEY(student_id) REFERENCES users(id)
        )
    ''')

    # 4. Bank Accounts Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bank_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_name TEXT NOT NULL,
            account_title TEXT NOT NULL,
            account_no TEXT NOT NULL,
            iban TEXT
        )
    ''')

    # 5. Fee Vouchers Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fee_vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            challan_no TEXT,
            amount INTEGER,
            semester TEXT,
            due_date TEXT,
            status TEXT DEFAULT 'Unpaid',
            receipt_file TEXT DEFAULT '',
            FOREIGN KEY(student_id) REFERENCES users(id)
        )
    ''')

    cursor.execute("PRAGMA table_info(fee_vouchers)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'receipt_file' not in columns:
        cursor.execute("ALTER TABLE fee_vouchers ADD COLUMN receipt_file TEXT DEFAULT ''")

    # 6. Timetable Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS timetable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department TEXT NOT NULL,
            day TEXT NOT NULL,
            time_slot TEXT NOT NULL,
            subject TEXT NOT NULL,
            teacher TEXT,
            room_no TEXT
        )
    ''')

    # 7. Results & CGPA Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            semester TEXT,
            gpa REAL,
            cgpa REAL,
            remarks TEXT,
            result_card_file TEXT,
            FOREIGN KEY(student_id) REFERENCES users(id)
        )
    ''')

    # 8. Complaints Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            subject TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'Pending',
            FOREIGN KEY(student_id) REFERENCES users(id)
        )
    ''')

    # Setup Admin Account
    admin_pass = generate_password_hash('qwerty098')
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin@duet.pk'")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO users (username, password, role, full_name, status) 
            VALUES ('admin@duet.pk', ?, 'admin', 'System Administrator', 'Approved')
        ''', (admin_pass,))
    else:
        cursor.execute("UPDATE users SET password = ? WHERE username = 'admin@duet.pk'", (admin_pass,))

    conn.commit()
    conn.close()

init_db()

# ------------------ FRONTEND TEMPLATE ------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DUET ERP Portal</title>
    <script src="https://unpkg.com/html5-qrcode"></script>
    <style>
        * { box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; }
        body { background: #f1f5f9; color: #1e293b; padding-bottom: 50px; }
        header { background: #002147; color: white; padding: 20px; text-align: center; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
        .container { max-width: 1150px; margin: 25px auto; padding: 0 15px; }
        .card { background: white; border-radius: 12px; padding: 22px; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
        
        .tab-buttons { display: flex; flex-wrap: wrap; border-bottom: 2px solid #cbd5e1; margin-bottom: 20px; gap: 5px; }
        .tab-btn { padding: 10px 16px; background: #e2e8f0; border: none; font-size: 13px; font-weight: bold; color: #475569; cursor: pointer; border-radius: 8px 8px 0 0; transition: 0.2s; }
        .tab-btn.active { background: #002147; color: white; }
        
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        input, select, textarea, button { width: 100%; padding: 10px; margin-top: 5px; margin-bottom: 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px; }
        textarea { resize: vertical; min-height: 80px; }
        .btn { background: #002147; color: white; border: none; font-weight: bold; cursor: pointer; transition: 0.2s; }
        .btn:hover { background: #003366; }
        .btn-success { background: #16a34a; color: white; }
        .btn-danger { background: #dc2626; color: white; }
        .btn-warning { background: #d97706; color: white; }
        .btn-logout { background: #dc2626; width: auto; padding: 8px 16px; float: right; font-size: 13px; margin: 0; border-radius: 6px; }
        .btn-sm { padding: 5px 10px; font-size: 11px; margin: 2px 2px; width: auto; display: inline-block; }
        
        .profile-box { display: flex; align-items: center; gap: 20px; }
        .profile-img { width: 80px; height: 80px; border-radius: 50%; object-fit: cover; border: 3px solid #002147; background: #e2e8f0; }
        
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 10px 8px; border-bottom: 1px solid #e2e8f0; text-align: left; font-size: 12px; vertical-align: middle; }
        th { background: #f8fafc; color: #334155; font-weight: 700; }
        
        .badge { padding: 4px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; display: inline-block; }
        .badge-pending { background: #fef3c7; color: #d97706; }
        .badge-approved { background: #dcfce7; color: #15803d; }
        .badge-rejected { background: #fee2e2; color: #dc2626; }
        
        .flash { padding: 12px; background: #e0f2fe; color: #0369a1; border-radius: 8px; margin-bottom: 15px; font-size: 13px; font-weight: 500; }
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px; }
        .metric-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; text-align: center; }
        .metric-card h4 { font-size: 12px; color: #64748b; margin-bottom: 5px; }
        .metric-card p { font-size: 20px; font-weight: bold; color: #002147; }
        .bank-box { background: #eff6ff; border: 1px dashed #2563eb; padding: 12px; border-radius: 8px; margin-bottom: 10px; }
        .alert-warning { background: #fffbebf5; border: 1px solid #fef3c7; color: #b45309; padding: 15px; border-radius: 8px; }
        .complaint-card { border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; margin-bottom: 10px; background: #fafafa; }
        
        .mobile-access-box { background: #1e293b; color: #f8fafc; padding: 15px; border-radius: 8px; font-size: 13px; margin-bottom: 15px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
        .mobile-access-box code { background: #334155; padding: 4px 8px; border-radius: 4px; color: #38bdf8; font-family: monospace; font-size: 14px; }
        .qr-card { text-align: center; background: white; padding: 10px; border-radius: 8px; width: 140px; }
        .qr-card img { width: 120px; height: 120px; }
        
        /* Modal for Editing Student */
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); }
        .modal-content { background: white; margin: 8% auto; padding: 20px; border-radius: 12px; width: 90%; max-width: 500px; }

        #reader { width: 100%; max-width: 400px; margin: 10px auto; border: 2px dashed #002147; border-radius: 8px; display: none; }
        #scan-result { font-weight: bold; color: #16a34a; margin-top: 10px; text-align: center; }
    </style>
</head>
<body>

    <header>
        <h1>Dawood University of Engineering & Technology</h1>
        <p>Comprehensive Academic ERP Portal</p>
    </header>

    <div class="container">
        <!-- Live Generated Mobile URL & QR Code -->
        <div class="mobile-access-box">
            <div>
                📱 <strong>Mobile Access:</strong> Same Wi-Fi network par mobile me yeh link kholein:<br><br>
                <code>http://{{ local_ip }}:5000</code>
            </div>
            <div class="qr-card">
                <img src="/generate_qr" alt="Scan to Open Site">
                <small style="color:#334155; font-size:10px; font-weight:bold; display:block;">Scan with Mobile</small>
            </div>
        </div>

        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for message in messages %}
                    <div class="flash">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        {% if not session.user_id %}
            <div class="card tab-container">
                <div class="tab-buttons">
                    <button class="tab-btn active" onclick="switchTab(event, 'signin')">🔑 Student Login</button>
                    <button class="tab-btn" onclick="switchTab(event, 'signup')">📝 Student Register</button>
                    <button class="tab-btn" onclick="switchTab(event, 'admin')">🛡️ Admin Portal</button>
                    <button class="tab-btn" onclick="switchTab(event, 'scanner')">📷 Scan QR Code</button>
                </div>

                <div id="signin" class="tab-content active">
                    <h2 style="color: #002147; font-size: 16px; margin-bottom: 10px;">Student Sign In</h2>
                    <form action="/login" method="POST">
                        <input type="text" name="username" id="login_username" placeholder="Username" required>
                        <input type="password" name="password" placeholder="Password" required>
                        <button type="submit" class="btn">Login</button>
                    </form>
                </div>

                <div id="signup" class="tab-content">
                    <h2 style="color: #16a34a; font-size: 16px; margin-bottom: 10px;">Student Registration</h2>
                    <form action="/register" method="POST" enctype="multipart/form-data">
                        <input type="text" name="username" placeholder="Username" required>
                        <input type="password" name="password" placeholder="Password" required>
                        <input type="text" name="full_name" placeholder="Full Name" required>
                        <input type="text" name="roll_no" placeholder="Roll No" required>
                        <select name="department" required>
                            <option value="">Select Department</option>
                            <option value="Computer Science">Computer Science</option>
                            <option value="Software Engineering">Software Engineering</option>
                            <option value="Cyber Security">Cyber Security</option>
                            <option value="Artificial Intelligence">Artificial Intelligence</option>
                        </select>
                        <label style="font-size: 11px; font-weight: bold;">Profile Picture:</label>
                        <input type="file" name="profile_pic" accept="image/*">
                        <button type="submit" class="btn btn-success">Register</button>
                    </form>
                </div>

                <div id="admin" class="tab-content">
                    <h2 style="color: #334155; font-size: 16px; margin-bottom: 10px;">Admin Login</h2>
                    <form action="/login" method="POST">
                        <input type="text" name="username" placeholder="Admin Username (admin@duet.pk)" required>
                        <input type="password" name="password" placeholder="Admin Password" required>
                        <button type="submit" class="btn">Admin Login</button>
                    </form>
                </div>

                <!-- QR Scanner Section -->
                <div id="scanner" class="tab-content">
                    <h2 style="color: #002147; font-size: 16px; margin-bottom: 10px;">📷 QR Code / Barcode Scanner</h2>
                    <p style="font-size: 12px; color: #64748b; margin-bottom: 10px;">Apne Roll No ya Login Link ka QR Code camera ke samne rakhein scan karne ke liye.</p>
                    <button type="button" class="btn btn-warning" onclick="startScanner()">Start Camera Scanner</button>
                    <div id="reader"></div>
                    <div id="scan-result"></div>
                </div>
            </div>

        {% else %}
            <a href="/logout"><button class="btn btn-logout">Logout</button></a>
            <div style="clear: both; margin-bottom: 15px;"></div>

            {% if session.role == 'student' %}
                <div class="card">
                    <div class="profile-box">
                        <img src="/static/uploads/{{ user[7] }}" class="profile-img" onerror="this.src='https://via.placeholder.com/80?text=User'">
                        <div>
                            <h2>{{ user[4] }}</h2>
                            <p style="font-size: 13px; color: #64748b;"><strong>Roll No:</strong> {{ user[5] }} | <strong>Dept:</strong> {{ user[6] }}</p>
                            <p style="margin-top: 5px;"><strong>Status:</strong> <span class="badge badge-{{ user[8].lower() }}">{{ user[8] }}</span></p>
                        </div>
                    </div>
                </div>

                {% if user[8] == 'Approved' %}
                    <div class="card">
                        <h3>📊 Academic Overview</h3>
                        <div class="metrics-grid">
                            <div class="metric-card">
                                <h4>Attendance Rate</h4>
                                <p style="color: {% if attendance_pct < 75 %}#dc2626{% else %}#16a34a{% endif %};">{{ attendance_pct }}%</p>
                            </div>
                            <div class="metric-card">
                                <h4>Latest CGPA</h4>
                                <p>{{ latest_result[4] if latest_result else 'N/A' }}</p>
                            </div>
                            <div class="metric-card">
                                <h4>Unpaid Fee</h4>
                                <p style="color: #dc2626;">PKR {{ unpaid_fee }}</p>
                            </div>
                        </div>
                    </div>

                    <div class="card tab-container">
                        <div class="tab-buttons">
                            <button class="tab-btn active" onclick="switchTab(event, 'st-attendance')">📋 Attendance</button>
                            <button class="tab-btn" onclick="switchTab(event, 'st-subjects')">📚 My Subjects</button>
                            <button class="tab-btn" onclick="switchTab(event, 'st-timetable')">🗓️ Timetable</button>
                            <button class="tab-btn" onclick="switchTab(event, 'st-fee')">💳 Fees & Payment</button>
                            <button class="tab-btn" onclick="switchTab(event, 'st-results')">🎓 Results & CGPA</button>
                            <button class="tab-btn" onclick="switchTab(event, 'st-complaints')">💬 Complain Box</button>
                        </div>

                        <!-- Attendance Tab -->
                        <div id="st-attendance" class="tab-content active">
                            <h3>Attendance Logs</h3>
                            <table>
                                <thead><tr><th>Date</th><th>Subject</th><th>Status</th></tr></thead>
                                <tbody>
                                    {% for att in attendance %}
                                        <tr>
                                            <td>{{ att[3] }}</td>
                                            <td>{{ att[2] }}</td>
                                            <td>
                                                {% if att[4] == 'Present' %}
                                                    <span class="badge badge-approved">Present</span>
                                                {% else %}
                                                    <span class="badge badge-rejected">Absent</span>
                                                {% endif %}
                                            </td>
                                        </tr>
                                    {% else %}
                                        <tr><td colspan="3" style="text-align: center; color: #94a3b8;">No attendance record logged yet.</td></tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>

                        <!-- My Subjects Tab -->
                        <div id="st-subjects" class="tab-content">
                            <h3>Enrolled Subjects ({{ user[6] }})</h3>
                            <table>
                                <thead><tr><th>Subject Code</th><th>Subject Name</th><th>Credit Hours</th></tr></thead>
                                <tbody>
                                    {% for subj in subjects %}
                                        <tr>
                                            <td><strong>{{ subj[2] }}</strong></td>
                                            <td>{{ subj[3] }}</td>
                                            <td>{{ subj[4] }} CH</td>
                                        </tr>
                                    {% else %}
                                        <tr><td colspan="3" style="text-align: center; color: #94a3b8;">No subjects registered for your department yet.</td></tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>

                        <!-- Timetable Tab -->
                        <div id="st-timetable" class="tab-content">
                            <h3>Class Timetable ({{ user[6] }})</h3>
                            <table>
                                <thead><tr><th>Day</th><th>Time</th><th>Subject</th><th>Room</th><th>Teacher</th></tr></thead>
                                <tbody>
                                    {% for tt in timetable %}
                                        <tr><td><strong>{{ tt[2] }}</strong></td><td>{{ tt[3] }}</td><td>{{ tt[4] }}</td><td>{{ tt[6] }}</td><td>{{ tt[5] }}</td></tr>
                                    {% else %}
                                        <tr><td colspan="5" style="text-align: center; color: #94a3b8;">No timetable published for your department yet.</td></tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>

                        <!-- Fee Tab -->
                        <div id="st-fee" class="tab-content">
                            <h3>University Bank Accounts</h3>
                            {% for bank in bank_accounts %}
                                <div class="bank-box">
                                    <strong>{{ bank[1] }}</strong> | Title: {{ bank[2] }} | A/C: <strong>{{ bank[3] }}</strong><br>
                                    <small>IBAN: {{ bank[4] }}</small>
                                </div>
                            {% else %}
                                <p style="font-size: 12px; color: #94a3b8; margin-bottom: 15px;">No bank account details uploaded by admin.</p>
                            {% endfor %}

                            <h3 style="margin-top: 20px;">Fee Vouchers & Payment Status</h3>
                            <table>
                                <thead><tr><th>Challan #</th><th>Semester</th><th>Amount</th><th>Due Date</th><th>Status</th><th>Upload Paid Slip</th></tr></thead>
                                <tbody>
                                    {% for fee in fee_vouchers %}
                                        <tr>
                                            <td>{{ fee[2] }}</td>
                                            <td>{{ fee[4] }}</td>
                                            <td>PKR {{ fee[3] }}</td>
                                            <td>{{ fee[5] }}</td>
                                            <td>
                                                {% if fee[6] == 'Paid' %}
                                                    <span class="badge badge-approved">Paid</span>
                                                {% elif fee[6] == 'Pending Approval' %}
                                                    <span class="badge badge-pending">Pending Approval</span>
                                                {% else %}
                                                    <span class="badge badge-rejected">Unpaid</span>
                                                {% endif %}
                                            </td>
                                            <td>
                                                {% if fee[6] != 'Paid' %}
                                                    <form action="/student/upload_voucher" method="POST" enctype="multipart/form-data" style="display:flex; gap:5px; margin:0;">
                                                        <input type="hidden" name="voucher_id" value="{{ fee[0] }}">
                                                        <input type="file" name="receipt" accept="image/*,.pdf" required style="margin:0; padding:3px; font-size:11px;">
                                                        <button type="submit" class="btn btn-sm btn-success">Upload</button>
                                                    </form>
                                                {% else %}
                                                    <a href="/static/payments/{{ fee[7] }}" target="_blank"><button class="btn btn-sm">View Receipt</button></a>
                                                {% endif %}
                                            </td>
                                        </tr>
                                    {% else %}
                                        <tr><td colspan="6" style="text-align: center; color: #94a3b8;">No fee voucher issued yet.</td></tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>

                        <!-- Results Tab -->
                        <div id="st-results" class="tab-content">
                            <h3>Result Card & CGPA</h3>
                            <table>
                                <thead><tr><th>Semester</th><th>GPA</th><th>CGPA</th><th>Remarks</th><th>Result Card</th></tr></thead>
                                <tbody>
                                    {% for res in results %}
                                        <tr>
                                            <td>{{ res[2] }}</td>
                                            <td>{{ res[3] }}</td>
                                            <td><strong>{{ res[4] }}</strong></td>
                                            <td>{{ res[5] }}</td>
                                            <td>
                                                {% if res[6] %}
                                                    <a href="/static/results/{{ res[6] }}" target="_blank"><button class="btn btn-sm">View Document</button></a>
                                                {% else %}
                                                    N/A
                                                {% endif %}
                                            </td>
                                        </tr>
                                    {% else %}
                                        <tr><td colspan="5" style="text-align: center; color: #94a3b8;">No examination results published yet.</td></tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>

                        <!-- Complaints Tab -->
                        <div id="st-complaints" class="tab-content">
                            <h3>Submit a Query / Complaint</h3>
                            <form action="/student/submit_complaint" method="POST">
                                <input type="text" name="subject" placeholder="Subject / Topic (e.g., Fee Verification Issue)" required>
                                <textarea name="description" placeholder="Explain your issue in detail..." required></textarea>
                                <button type="submit" class="btn btn-warning">Submit Complaint</button>
                            </form>

                            <h3 style="margin-top: 20px;">My Complaints History</h3>
                            {% for comp in complaints %}
                                <div class="complaint-card">
                                    <div style="display:flex; justify-content:space-between;">
                                        <strong>{{ comp[2] }}</strong>
                                        <span class="badge badge-{% if comp[5] == 'Resolved' %}approved{% else %}pending{% endif %}">{{ comp[5] }}</span>
                                    </div>
                                    <p style="font-size:12px; margin-top:5px; color:#475569;">{{ comp[3] }}</p>
                                    <small style="color:#94a3b8;">Submitted on: {{ comp[4] }}</small>
                                </div>
                            {% else %}
                                <p style="font-size: 12px; color: #94a3b8;">No complaints submitted yet.</p>
                            {% endfor %}
                        </div>
                    </div>
                {% else %}
                    <div class="card alert-warning">
                        ⏳ <strong>Account Status: Pending Approval</strong><br>
                        Aapki account request Admin review karrha hai.
                    </div>
                {% endif %}

            {% elif session.role == 'admin' %}
                <div class="card tab-container">
                    <h2 style="color: #002147; margin-bottom: 15px;">🛡️ Admin Control Panel</h2>
                    <div class="tab-buttons">
                        <button class="tab-btn active" onclick="switchTab(event, 'ad-students')">👥 Student Records</button>
                        <button class="tab-btn" onclick="switchTab(event, 'ad-attendance')">📋 Class Attendance</button>
                        <button class="tab-btn" onclick="switchTab(event, 'ad-subjects')">📚 Subjects</button>
                        <button class="tab-btn" onclick="switchTab(event, 'ad-timetable')">🗓️ Timetable</button>
                        <button class="tab-btn" onclick="switchTab(event, 'ad-fees')">💳 Fees & Payments</button>
                        <button class="tab-btn" onclick="switchTab(event, 'ad-results')">🎓 Results & CGPA</button>
                        <button class="tab-btn" onclick="switchTab(event, 'ad-complaints')">💬 Complaints</button>
                    </div>

                    <!-- Students Management Tab (With Edit & Delete) -->
                    <div id="ad-students" class="tab-content active">
                        <h3>Student Records & Account Management</h3>
                        <table>
                            <thead>
                                <tr>
                                    <th>Full Name</th>
                                    <th>Roll No</th>
                                    <th>Department</th>
                                    <th>Status</th>
                                    <th>Password Reset</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for student in students %}
                                    <tr>
                                        <td><strong>{{ student[4] }}</strong><br><small>{{ student[1] }}</small></td>
                                        <td>{{ student[5] }}</td>
                                        <td>{{ student[6] }}</td>
                                        <td><span class="badge badge-{{ student[8].lower() }}">{{ student[8] }}</span></td>
                                        <td>
                                            <form action="/admin/reset_password" method="POST" style="display:flex; gap:4px; margin:0;">
                                                <input type="hidden" name="student_id" value="{{ student[0] }}">
                                                <input type="password" name="new_password" placeholder="New Pass" required style="margin:0; width:90px; padding:4px;">
                                                <button type="submit" class="btn btn-sm">Set</button>
                                            </form>
                                        </td>
                                        <td>
                                            <button class="btn btn-sm btn-warning" onclick="openEditModal('{{ student[0] }}', '{{ student[4] }}', '{{ student[5] }}', '{{ student[6] }}', '{{ student[8] }}')">Edit</button>
                                            <a href="/admin/delete_student/{{ student[0] }}" onclick="return confirm('Kya aap is student ko delete karna chahte hain? Saara data remove hojaega.');"><button class="btn btn-sm btn-danger">Delete</button></a>
                                            {% if student[8] == 'Pending' %}
                                                <a href="/approve/{{ student[0] }}"><button class="btn btn-sm btn-success">Approve</button></a>
                                                <a href="/reject/{{ student[0] }}"><button class="btn btn-sm btn-danger">Reject</button></a>
                                            {% endif %}
                                        </td>
                                    </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>

                    <!-- Department-Wise Attendance Tab -->
                    <div id="ad-attendance" class="tab-content">
                        <h3>Department-Wise Attendance Marking</h3>
                        
                        <form method="GET" action="/" style="background:#f8fafc; padding:15px; border-radius:8px; border:1px solid #e2e8f0; margin-bottom:20px;">
                            <input type="hidden" name="tab" value="ad-attendance">
                            <label style="font-weight:bold; font-size:12px;">Step 1: Department Select Karein</label>
                            <select name="dept_filter" onchange="this.form.submit()" required>
                                <option value="">-- Select Department --</option>
                                <option value="Computer Science" {% if selected_dept == 'Computer Science' %}selected{% endif %}>Computer Science</option>
                                <option value="Software Engineering" {% if selected_dept == 'Software Engineering' %}selected{% endif %}>Software Engineering</option>
                                <option value="Cyber Security" {% if selected_dept == 'Cyber Security' %}selected{% endif %}>Cyber Security</option>
                                <option value="Artificial Intelligence" {% if selected_dept == 'Artificial Intelligence' %}selected{% endif %}>Artificial Intelligence</option>
                            </select>
                        </form>

                        {% if selected_dept %}
                            <form action="/admin/mark_bulk_attendance" method="POST" style="background:#eff6ff; padding:15px; border-radius:8px; border:1px solid #2563eb;">
                                <input type="hidden" name="department" value="{{ selected_dept }}">
                                
                                <h4>Marking Class Attendance for: <span style="color:#2563eb;">{{ selected_dept }}</span></h4>
                                
                                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; margin-top:10px;">
                                    <div>
                                        <label style="font-weight:bold; font-size:12px;">Registered Subject:</label>
                                        <select name="subject" required>
                                            <option value="">-- Select Subject --</option>
                                            {% for subj in dept_subjects %}
                                                <option value="{{ subj[2] }} - {{ subj[3] }}">{{ subj[2] }} - {{ subj[3] }}</option>
                                            {% else %}
                                                <option value="" disabled>Is Department me koi subject registered nhi hai!</option>
                                            {% endfor %}
                                        </select>
                                    </div>
                                    <div>
                                        <label style="font-weight:bold; font-size:12px;">Date:</label>
                                        <input type="date" name="date" required value="{{ current_date }}">
                                    </div>
                                </div>

                                <h4 style="margin-top:15px; margin-bottom:5px;">Students Class Roll List:</h4>
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Roll No</th>
                                            <th>Student Name</th>
                                            <th>Attendance Status</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {% for st in dept_students %}
                                            <tr>
                                                <td><strong>{{ st[5] }}</strong></td>
                                                <td>{{ st[4] }}</td>
                                                <td>
                                                    <select name="status_{{ st[0] }}" style="margin:0; padding:5px;">
                                                        <option value="Present">Present</option>
                                                        <option value="Absent">Absent</option>
                                                    </select>
                                                </td>
                                            </tr>
                                        {% else %}
                                            <tr><td colspan="3" style="text-align:center; color:#dc2626;">Is Department me abhi koi Approved Student nahi hai.</td></tr>
                                        {% endfor %}
                                    </tbody>
                                </table>

                                {% if dept_students and dept_subjects %}
                                    <button type="submit" class="btn btn-success" style="margin-top:15px;">Submit Class Attendance</button>
                                {% endif %}
                            </form>
                        {% endif %}
                    </div>

                    <!-- Subjects Tab -->
                    <div id="ad-subjects" class="tab-content">
                        <h3>Add New Course Subject</h3>
                        <form action="/admin/add_subject" method="POST">
                            <select name="department" required>
                                <option value="Computer Science">Computer Science</option>
                                <option value="Software Engineering">Software Engineering</option>
                                <option value="Cyber Security">Cyber Security</option>
                                <option value="Artificial Intelligence">Artificial Intelligence</option>
                            </select>
                            <input type="text" name="subject_code" placeholder="Course Code (e.g., AI-101)" required>
                            <input type="text" name="subject_name" placeholder="Course Title (e.g., Deep Learning)" required>
                            <input type="number" name="credit_hours" placeholder="Credit Hours (e.g., 3)" min="1" max="6" required>
                            <button type="submit" class="btn btn-success">Add Subject</button>
                        </form>
                    </div>

                    <!-- Timetable Tab -->
                    <div id="ad-timetable" class="tab-content">
                        <h3>Add Timetable Entry</h3>
                        <form action="/admin/add_timetable" method="POST">
                            <select name="department" required>
                                <option value="Computer Science">Computer Science</option>
                                <option value="Software Engineering">Software Engineering</option>
                                <option value="Cyber Security">Cyber Security</option>
                                <option value="Artificial Intelligence">Artificial Intelligence</option>
                            </select>
                            <select name="day" required>
                                <option value="Monday">Monday</option><option value="Tuesday">Tuesday</option><option value="Wednesday">Wednesday</option><option value="Thursday">Thursday</option><option value="Friday">Friday</option>
                            </select>
                            <input type="text" name="time_slot" placeholder="09:00 AM - 10:30 AM" required>
                            <input type="text" name="subject" placeholder="Subject Name" required>
                            <input type="text" name="teacher" placeholder="Teacher Name" required>
                            <input type="text" name="room_no" placeholder="Room No" required>
                            <button type="submit" class="btn btn-success">Save Timetable</button>
                        </form>
                    </div>

                    <!-- Fees Tab -->
                    <div id="ad-fees" class="tab-content">
                        <h3>Configure University Bank Account</h3>
                        <form action="/admin/add_bank" method="POST">
                            <input type="text" name="bank_name" placeholder="Bank Name (e.g. HBL)" required>
                            <input type="text" name="account_title" placeholder="Account Title" required>
                            <input type="text" name="account_no" placeholder="Account Number" required>
                            <input type="text" name="iban" placeholder="IBAN Number">
                            <button type="submit" class="btn">Add Bank Account</button>
                        </form>

                        <h3 style="margin-top:20px;">Issue Student Fee Voucher</h3>
                        <form action="/admin/issue_fee" method="POST">
                            <select name="student_id" required>
                                {% for st in approved_students %}
                                    <option value="{{ st[0] }}">{{ st[4] }} ({{ st[5] }}) - {{ st[6] }}</option>
                                {% endfor %}
                            </select>
                            <input type="text" name="challan_no" placeholder="Challan No" required>
                            <input type="number" name="amount" placeholder="Amount (PKR)" required>
                            <input type="text" name="semester" placeholder="Semester (e.g., Fall 2026)" required>
                            <input type="date" name="due_date" required>
                            <button type="submit" class="btn btn-success">Issue Voucher</button>
                        </form>

                        <h3 style="margin-top:20px;">Submitted Fee Verification Receipts</h3>
                        <table>
                            <thead><tr><th>Student</th><th>Challan</th><th>Amount</th><th>Receipt</th><th>Action</th></tr></thead>
                            <tbody>
                                {% for fee in all_fees %}
                                    <tr>
                                        <td>{{ fee[8] }} ({{ fee[9] }})</td>
                                        <td>{{ fee[2] }}</td>
                                        <td>PKR {{ fee[3] }}</td>
                                        <td>
                                            {% if fee[7] %}
                                                <a href="/static/payments/{{ fee[7] }}" target="_blank"><button class="btn btn-sm">View Payment Slip</button></a>
                                            {% else %}
                                                No Slip Uploaded
                                            {% endif %}
                                        </td>
                                        <td>
                                            {% if fee[6] != 'Paid' %}
                                                <a href="/admin/verify_fee/{{ fee[0] }}"><button class="btn btn-sm btn-success">Approve Paid Status</button></a>
                                            {% else %}
                                                <span class="badge badge-approved">Verified</span>
                                            {% endif %}
                                        </td>
                                    </tr>
                                {% else %}
                                    <tr><td colspan="5" style="text-align:center; color:#94a3b8;">No pending payment receipts to review.</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>

                    <!-- Results Tab -->
                    <div id="ad-results" class="tab-content">
                        <h3>Publish Result & CGPA</h3>
                        <form action="/admin/publish_result" method="POST" enctype="multipart/form-data">
                            <select name="student_id" required>
                                {% for st in approved_students %}
                                    <option value="{{ st[0] }}">{{ st[4] }} ({{ st[5] }})</option>
                                {% endfor %}
                            </select>
                            <input type="text" name="semester" placeholder="Semester (e.g., 3rd Semester)" required>
                            <input type="number" step="0.01" name="gpa" placeholder="GPA (e.g., 3.45)" required>
                            <input type="number" step="0.01" name="cgpa" placeholder="CGPA (e.g., 3.52)" required>
                            <input type="text" name="remarks" placeholder="Remarks (e.g., Passed)">
                            <label style="font-size: 11px; font-weight: bold;">Result Card PDF/Image:</label>
                            <input type="file" name="result_card" accept="image/*,.pdf">
                            <button type="submit" class="btn btn-success">Publish Result</button>
                        </form>
                    </div>

                    <!-- Complaints Tab -->
                    <div id="ad-complaints" class="tab-content">
                        <h3>Student Queries & Complaints</h3>
                        {% for comp in all_complaints %}
                            <div class="complaint-card">
                                <div style="display:flex; justify-content:space-between;">
                                    <strong>{{ comp[7] }} ({{ comp[8] }}) - {{ comp[2] }}</strong>
                                    <span class="badge badge-{% if comp[5] == 'Resolved' %}approved{% else %}pending{% endif %}">{{ comp[5] }}</span>
                                </div>
                                <p style="font-size:12px; margin-top:5px; color:#475569;">{{ comp[3] }}</p>
                                <small style="color:#94a3b8;">Submitted on: {{ comp[4] }}</small>
                                {% if comp[5] != 'Resolved' %}
                                    <br><a href="/admin/resolve_complaint/{{ comp[0] }}"><button class="btn btn-sm btn-success" style="margin-top:5px;">Mark as Resolved</button></a>
                                {% endif %}
                            </div>
                        {% else %}
                            <p style="font-size: 12px; color: #94a3b8;">No complaints submitted by students.</p>
                        {% endfor %}
                    </div>
                </div>
            {% endif %}
        {% endif %}
    </div>

    <!-- Student Edit Modal -->
    <div id="editModal" class="modal">
        <div class="modal-content">
            <h3 style="margin-bottom:15px; color:#002147;">✏️ Edit Student Record</h3>
            <form action="/admin/edit_student" method="POST">
                <input type="hidden" name="student_id" id="modal_student_id">
                <label style="font-size:11px; font-weight:bold;">Full Name:</label>
                <input type="text" name="full_name" id="modal_full_name" required>
                
                <label style="font-size:11px; font-weight:bold;">Roll No:</label>
                <input type="text" name="roll_no" id="modal_roll_no" required>
                
                <label style="font-size:11px; font-weight:bold;">Department:</label>
                <select name="department" id="modal_department" required>
                    <option value="Computer Science">Computer Science</option>
                    <option value="Software Engineering">Software Engineering</option>
                    <option value="Cyber Security">Cyber Security</option>
                    <option value="Artificial Intelligence">Artificial Intelligence</option>
                </select>

                <label style="font-size:11px; font-weight:bold;">Status:</label>
                <select name="status" id="modal_status" required>
                    <option value="Approved">Approved</option>
                    <option value="Pending">Pending</option>
                    <option value="Rejected">Rejected</option>
                </select>

                <div style="display:flex; gap:10px; margin-top:10px;">
                    <button type="submit" class="btn btn-success">Update Student</button>
                    <button type="button" class="btn btn-danger" onclick="closeEditModal()">Cancel</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        function switchTab(evt, tabId) {
            let container = evt.currentTarget.closest('.tab-container');
            let contents = container.querySelectorAll('.tab-content');
            let buttons = container.querySelectorAll('.tab-btn');
            
            contents.forEach(c => c.classList.remove('active'));
            buttons.forEach(b => b.classList.remove('active'));
            
            document.getElementById(tabId).classList.add('active');
            evt.currentTarget.classList.add('active');
        }

        function openEditModal(id, name, roll, dept, status) {
            document.getElementById('modal_student_id').value = id;
            document.getElementById('modal_full_name').value = name;
            document.getElementById('modal_roll_no').value = roll;
            document.getElementById('modal_department').value = dept;
            document.getElementById('modal_status').value = status;
            document.getElementById('editModal').style.display = 'block';
        }

        function closeEditModal() {
            document.getElementById('editModal').style.display = 'none';
        }

        // Camera QR Scanner
        let html5QrCode;
        function startScanner() {
            let targetElement = document.getElementById("reader");
            if (!targetElement) return;
            
            targetElement.style.display = "block";
            
            html5QrCode = new Html5Qrcode(targetElement.id);
            html5QrCode.start(
                { facingMode: "environment" },
                { fps: 10, qrbox: { width: 250, height: 250 } },
                (decodedText) => {
                    document.getElementById("scan-result").innerText = "Scanned: " + decodedText;

                    if (decodedText.startsWith("http://") || decodedText.startsWith("https://")) {
                        window.location.href = decodedText;
                    } else {
                        let loginInput = document.getElementById("login_username");
                        if (loginInput) loginInput.value = decodedText;
                    }
                    html5QrCode.stop();
                },
                (errorMessage) => {}
            ).catch(err => {
                alert("Camera access failed.");
            });
        }
    </script>
</body>
</html>
"""

# ------------------ SERVER ROUTES ------------------

@app.route('/generate_qr')
def generate_qr():
    local_ip = get_local_ip()
    target_url = f"http://{local_ip}:5000"
    
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(target_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

@app.route('/')
def home():
    local_ip = get_local_ip()
    if 'user_id' not in session:
        return render_template_string(HTML_TEMPLATE, local_ip=local_ip)

    conn = sqlite3.connect('duet_multiport.db')
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
    user = cursor.fetchone()

    if session['role'] == 'student':
        cursor.execute("SELECT * FROM attendance WHERE student_id = ?", (session['user_id'],))
        attendance = cursor.fetchall()
        
        total_att = len(attendance)
        p_att = sum(1 for a in attendance if a[4] == 'Present')
        attendance_pct = round((p_att / total_att * 100), 1) if total_att > 0 else 100.0

        cursor.execute("SELECT * FROM subjects WHERE department = ?", (user[6],))
        subjects = cursor.fetchall()

        cursor.execute("SELECT * FROM timetable WHERE department = ? ORDER BY id ASC", (user[6],))
        timetable = cursor.fetchall()

        cursor.execute("SELECT * FROM bank_accounts")
        bank_accounts = cursor.fetchall()

        cursor.execute("SELECT * FROM fee_vouchers WHERE student_id = ?", (session['user_id'],))
        fee_vouchers = cursor.fetchall()

        unpaid_fee = sum(f[3] for f in fee_vouchers if f[6] != 'Paid')

        cursor.execute("SELECT * FROM results WHERE student_id = ? ORDER BY id DESC", (session['user_id'],))
        results = cursor.fetchall()
        latest_result = results[0] if results else None

        cursor.execute("SELECT * FROM complaints WHERE student_id = ? ORDER BY id DESC", (session['user_id'],))
        complaints = cursor.fetchall()

        conn.close()
        return render_template_string(
            HTML_TEMPLATE, local_ip=local_ip, user=user, attendance=attendance, attendance_pct=attendance_pct,
            subjects=subjects, timetable=timetable, bank_accounts=bank_accounts,
            fee_vouchers=fee_vouchers, unpaid_fee=unpaid_fee, results=results,
            latest_result=latest_result, complaints=complaints
        )

    elif session['role'] == 'admin':
        selected_dept = request.args.get('dept_filter', '')

        cursor.execute("SELECT * FROM users WHERE role = 'student' ORDER BY id DESC")
        students = cursor.fetchall()

        cursor.execute("SELECT * FROM users WHERE role = 'student' AND status = 'Approved'")
        approved_students = cursor.fetchall()

        dept_students = []
        dept_subjects = []
        if selected_dept:
            cursor.execute("SELECT * FROM users WHERE role = 'student' AND status = 'Approved' AND department = ?", (selected_dept,))
            dept_students = cursor.fetchall()

            cursor.execute("SELECT * FROM subjects WHERE department = ?", (selected_dept,))
            dept_subjects = cursor.fetchall()

        cursor.execute('''
            SELECT fee_vouchers.*, users.full_name, users.roll_no 
            FROM fee_vouchers 
            JOIN users ON fee_vouchers.student_id = users.id 
            ORDER BY fee_vouchers.id DESC
        ''')
        all_fees = cursor.fetchall()

        cursor.execute('''
            SELECT complaints.*, users.full_name, users.roll_no 
            FROM complaints 
            JOIN users ON complaints.student_id = users.id 
            ORDER BY complaints.id DESC
        ''')
        all_complaints = cursor.fetchall()

        conn.close()
        return render_template_string(
            HTML_TEMPLATE, local_ip=local_ip, user=user, students=students, approved_students=approved_students,
            selected_dept=selected_dept, dept_students=dept_students, dept_subjects=dept_subjects,
            all_fees=all_fees, all_complaints=all_complaints
        )

# --- Student CRUD (Edit / Delete) ---
@app.route('/admin/edit_student', methods=['POST'])
def edit_student():
    if session.get('role') == 'admin':
        student_id = request.form['student_id']
        full_name = request.form['full_name']
        roll_no = request.form['roll_no']
        department = request.form['department']
        status = request.form['status']

        conn = sqlite3.connect('duet_multiport.db')
        cursor = conn.cursor()
        try:
            cursor.execute('''
                UPDATE users 
                SET full_name = ?, roll_no = ?, department = ?, status = ?
                WHERE id = ?
            ''', (full_name, roll_no, department, status, student_id))
            conn.commit()
            flash("Student Record Updated Successfully!")
        except sqlite3.IntegrityError:
            flash("Roll No already exists for another student!")
        finally:
            conn.close()

    return redirect(url_for('home'))

@app.route('/admin/delete_student/<int:student_id>')
def delete_student(student_id):
    if session.get('role') == 'admin':
        conn = sqlite3.connect('duet_multiport.db')
        cursor = conn.cursor()
        
        # Student aur us se judi saari info delete karna
        cursor.execute("DELETE FROM users WHERE id = ?", (student_id,))
        cursor.execute("DELETE FROM attendance WHERE student_id = ?", (student_id,))
        cursor.execute("DELETE FROM fee_vouchers WHERE student_id = ?", (student_id,))
        cursor.execute("DELETE FROM results WHERE student_id = ?", (student_id,))
        cursor.execute("DELETE FROM complaints WHERE student_id = ?", (student_id,))
        
        conn.commit()
        conn.close()
        flash("Student Record and linked data deleted!")
    return redirect(url_for('home'))

# --- Department-Wise Bulk Attendance Route ---
@app.route('/admin/mark_bulk_attendance', methods=['POST'])
def mark_bulk_attendance():
    if session.get('role') == 'admin':
        department = request.form['department']
        subject = request.form['subject']
        date = request.form['date']

        conn = sqlite3.connect('duet_multiport.db')
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE role = 'student' AND status = 'Approved' AND department = ?", (department,))
        students = cursor.fetchall()

        for st in students:
            st_id = st[0]
            status_key = f"status_{st_id}"
            st_status = request.form.get(status_key, 'Absent')
            
            cursor.execute('''
                INSERT INTO attendance (student_id, subject, date, status)
                VALUES (?, ?, ?, ?)
            ''', (st_id, subject, date, st_status))

        conn.commit()
        conn.close()
        flash(f"Class Attendance marked successfully for {department} ({subject})!")
    return redirect(url_for('home'))

# --- Auth Routes ---
@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    conn = sqlite3.connect('duet_multiport.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user[2], password):
        session['user_id'] = user[0]
        session['username'] = user[1]
        session['role'] = user[3]
        flash("Login Successful!")
    else:
        flash("Invalid Credentials!")

    return redirect(url_for('home'))

@app.route('/register', methods=['POST'])
def register():
    username = request.form['username']
    password = generate_password_hash(request.form['password'])
    full_name = request.form['full_name']
    roll_no = request.form['roll_no']
    department = request.form['department']
    profile_pic = 'default.png'

    if 'profile_pic' in request.files:
        file = request.files['profile_pic']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            profile_pic = filename

    conn = sqlite3.connect('duet_multiport.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (username, password, role, full_name, roll_no, department, profile_pic, status)
            VALUES (?, ?, 'student', ?, ?, ?, ?, 'Pending')
        ''', (username, password, full_name, roll_no, department, profile_pic))
        conn.commit()
        flash("Registration submitted! Pending Admin Approval.")
    except sqlite3.IntegrityError:
        flash("Username or Roll No already exists!")
    finally:
        conn.close()

    return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for('home'))

# --- Admin Functionalities ---
@app.route('/approve/<int:user_id>')
def approve_user(user_id):
    if session.get('role') == 'admin':
        conn = sqlite3.connect('duet_multiport.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET status = 'Approved' WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        flash("Student Approved!")
    return redirect(url_for('home'))

@app.route('/reject/<int:user_id>')
def reject_user(user_id):
    if session.get('role') == 'admin':
        conn = sqlite3.connect('duet_multiport.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET status = 'Rejected' WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        flash("Student Rejected.")
    return redirect(url_for('home'))

@app.route('/admin/reset_password', methods=['POST'])
def admin_reset_password():
    if session.get('role') == 'admin':
        student_id = request.form['student_id']
        new_password = generate_password_hash(request.form['new_password'])
        
        conn = sqlite3.connect('duet_multiport.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (new_password, student_id))
        conn.commit()
        conn.close()
        flash("Student Password Updated Successfully!")
    return redirect(url_for('home'))

@app.route('/admin/add_timetable', methods=['POST'])
def add_timetable():
    if session.get('role') == 'admin':
        conn = sqlite3.connect('duet_multiport.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO timetable (department, day, time_slot, subject, teacher, room_no)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (request.form['department'], request.form['day'], request.form['time_slot'],
              request.form['subject'], request.form['teacher'], request.form['room_no']))
        conn.commit()
        conn.close()
        flash("Timetable slot added!")
    return redirect(url_for('home'))

@app.route('/admin/add_subject', methods=['POST'])
def add_subject():
    if session.get('role') == 'admin':
        conn = sqlite3.connect('duet_multiport.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO subjects (department, subject_code, subject_name, credit_hours)
            VALUES (?, ?, ?, ?)
        ''', (request.form['department'], request.form['subject_code'], request.form['subject_name'], request.form['credit_hours']))
        conn.commit()
        conn.close()
        flash("Subject added!")
    return redirect(url_for('home'))

@app.route('/admin/add_bank', methods=['POST'])
def add_bank():
    if session.get('role') == 'admin':
        conn = sqlite3.connect('duet_multiport.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO bank_accounts (bank_name, account_title, account_no, iban)
            VALUES (?, ?, ?, ?)
        ''', (request.form['bank_name'], request.form['account_title'], request.form['account_no'], request.form['iban']))
        conn.commit()
        conn.close()
        flash("Bank Account Configured!")
    return redirect(url_for('home'))

@app.route('/admin/issue_fee', methods=['POST'])
def issue_fee():
    if session.get('role') == 'admin':
        conn = sqlite3.connect('duet_multiport.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO fee_vouchers (student_id, challan_no, amount, semester, due_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (request.form['student_id'], request.form['challan_no'], request.form['amount'],
              request.form['semester'], request.form['due_date']))
        conn.commit()
        conn.close()
        flash("Fee Voucher Issued!")
    return redirect(url_for('home'))

@app.route('/admin/verify_fee/<int:fee_id>')
def verify_fee(fee_id):
    if session.get('role') == 'admin':
        conn = sqlite3.connect('duet_multiport.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE fee_vouchers SET status = 'Paid' WHERE id = ?", (fee_id,))
        conn.commit()
        conn.close()
        flash("Fee Status Verified as Paid!")
    return redirect(url_for('home'))

@app.route('/admin/publish_result', methods=['POST'])
def publish_result():
    if session.get('role') == 'admin':
        result_card = ''
        if 'result_card' in request.files:
            file = request.files['result_card']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['RESULTS_FOLDER'], filename))
                result_card = filename

        conn = sqlite3.connect('duet_multiport.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO results (student_id, semester, gpa, cgpa, remarks, result_card_file)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (request.form['student_id'], request.form['semester'], request.form['gpa'],
              request.form['cgpa'], request.form['remarks'], result_card))
        conn.commit()
        conn.close()
        flash("Result Published Successfully!")
    return redirect(url_for('home'))

@app.route('/admin/resolve_complaint/<int:comp_id>')
def resolve_complaint(comp_id):
    if session.get('role') == 'admin':
        conn = sqlite3.connect('duet_multiport.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE complaints SET status = 'Resolved' WHERE id = ?", (comp_id,))
        conn.commit()
        conn.close()
        flash("Complaint marked as Resolved!")
    return redirect(url_for('home'))

# --- Student Functionalities ---
@app.route('/student/upload_voucher', methods=['POST'])
def upload_voucher():
    if session.get('role') == 'student':
        voucher_id = request.form['voucher_id']
        if 'receipt' in request.files:
            file = request.files['receipt']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['PAYMENTS_FOLDER'], filename))

                conn = sqlite3.connect('duet_multiport.db')
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE fee_vouchers 
                    SET receipt_file = ?, status = 'Pending Approval' 
                    WHERE id = ? AND student_id = ?
                ''', (filename, voucher_id, session['user_id']))
                conn.commit()
                conn.close()
                flash("Paid receipt submitted!")
    return redirect(url_for('home'))

@app.route('/student/submit_complaint', methods=['POST'])
def submit_complaint():
    if session.get('role') == 'student':
        conn = sqlite3.connect('duet_multiport.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO complaints (student_id, subject, description)
            VALUES (?, ?, ?)
        ''', (session['user_id'], request.form['subject'], request.form['description']))
        conn.commit()
        conn.close()
        flash("Complaint submitted.")
    return redirect(url_for('home'))

# ------------------ MAIN ENTRY ------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
    from flask import Flask

app = Flask(__name__) 