import os
import random
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_from_directory, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv

from models import db, User, Request

# Load environment variables from the .env file
load_dotenv()

app = Flask(__name__)

# Configs
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-dev-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///requestflow.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Real Email Configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- REAL EMAIL SENDER ---
def send_otp_email(recipient_email, otp):
    sender_email = app.config['MAIL_USERNAME']
    sender_password = app.config['MAIL_PASSWORD']
    
    if not sender_email or not sender_password:
        raise ValueError("Email credentials are not set in the .env file!")

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = "Your RequestFlow Verification Code"

    body = f"""
    Welcome to RequestFlow!
    
    Your 6-digit verification code is: {otp}
    
    This code will expire in 10 minutes. Please enter this code on the verification page to activate your account.
    """
    msg.attach(MIMEText(body, 'plain'))

    try:
        # Connect to Gmail's SMTP server
        server = smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT'])
        server.starttls() # Secure the connection
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        print(f"✅ Real OTP email successfully sent to: {recipient_email}")
    except Exception as e:
        print(f"❌ Failed to send email. Error: {e}")

# --- ROUTES ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        if not current_user.is_verified:
            return redirect(url_for('verify'))
        if current_user.role == 'admin':
            return redirect(url_for('admin'))
        if current_user.role == 'worker':
            return redirect(url_for('worker'))
        return redirect(url_for('portal'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            if not user.is_verified:
                session['verify_user_id'] = user.id
                
                # Generate a new OTP if they try to log in unverified
                new_otp = str(random.randint(100000, 999999))
                user.otp = new_otp
                user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
                db.session.commit()
                
                send_otp_email(user.email, new_otp) # Sends real email
                flash('Please verify your account. A new code was sent to your email.', 'info')
                return redirect(url_for('verify'))
                
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid email or password', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'user') 
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return redirect(url_for('register'))
            
        otp = str(random.randint(100000, 999999))
        expiry = datetime.utcnow() + timedelta(minutes=10)
        
        new_user = User(
            name=name, 
            email=email, 
            password_hash=generate_password_hash(password),
            role=role,
            is_verified=False,
            otp=otp,
            otp_expiry=expiry
        )
        db.session.add(new_user)
        db.session.commit()
        
        # Triggers the real email send
        send_otp_email(email, otp)
        session['verify_user_id'] = new_user.id
        
        return redirect(url_for('verify'))
    return render_template('register.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify():
    user_id = session.get('verify_user_id')
    if not user_id:
        return redirect(url_for('login'))
        
    user = db.session.get(User, user_id)
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        entered_otp = request.form.get('otp')
        
        if user.otp_expiry and datetime.utcnow() > user.otp_expiry:
            flash('Your verification code has expired. Please log in again to receive a new one.', 'error')
            session.pop('verify_user_id', None)
            return redirect(url_for('login'))

        if entered_otp == user.otp:
            user.is_verified = True
            user.otp = None
            user.otp_expiry = None
            db.session.commit()
            
            session.pop('verify_user_id', None)
            login_user(user)
            flash('Account verified successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid OTP. Please try again.', 'error')
            
    return render_template('verify.html', email=user.email)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/portal')
@login_required
def portal():
    if current_user.role != 'user': return redirect(url_for('index'))
    return render_template('portal.html', user=current_user)

@app.route('/admin')
@login_required
def admin():
    if current_user.role != 'admin': return redirect(url_for('index'))
    return render_template('admin.html', user=current_user)

@app.route('/worker')
@login_required
def worker():
    if current_user.role != 'worker': return redirect(url_for('index'))
    return render_template('worker.html', user=current_user)

# --- USER API ---

@app.route('/api/requests', methods=['GET', 'POST'])
@login_required
def api_requests():
    if request.method == 'POST':
        file = request.files.get('file')
        file_path = None
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            file_path = filename

        # Fix: Extract the price from the form and convert to float
        # Use a default of 0.0 if the price is missing or invalid
        try:
            raw_price = request.form.get('price', 0)
            calculated_price = float(raw_price)
        except (ValueError, TypeError):
            calculated_price = 0.0

        new_req = Request(
            user_id=current_user.id,
            title=request.form.get('title'),
            type=request.form.get('type'),
            start_date=request.form.get('startDate'),
            end_date=request.form.get('endDate'),
            priority=request.form.get('priority', 'medium'),
            description=request.form.get('description'),
            file_path=file_path,
            price=calculated_price  # Assign the decimal value here
        )
        
        db.session.add(new_req)
        db.session.commit()
        return jsonify({'message': 'Success', 'id': new_req.id}), 201

    requests = Request.query.filter_by(user_id=current_user.id).order_by(Request.created_at.desc()).all()
    return jsonify([r.to_dict() for r in requests])

@app.route('/api/requests/<req_id>', methods=['DELETE'])
@login_required
def withdraw_request(req_id):
    req = Request.query.filter_by(id=req_id, user_id=current_user.id).first()
    if req and req.status == 'pending':
        db.session.delete(req)
        db.session.commit()
        return jsonify({'message': 'Withdrawn'})
    return jsonify({'error': 'Cannot withdraw'}), 400

# --- ADMIN API ---

@app.route('/api/admin/requests', methods=['GET'])
@login_required
def api_admin_requests():
    if current_user.role != 'admin': return jsonify({'error': 'Unauthorized'}), 403
    requests = Request.query.filter(Request.status.in_(['pending', 'in_progress', 'completed'])).order_by(
        db.case((Request.priority == 'urgent', 1), (Request.priority == 'high', 2), (Request.priority == 'medium', 3), else_=4)
    ).all()
    return jsonify([r.to_dict() for r in requests])

@app.route('/api/admin/requests/<req_id>/<action>', methods=['POST'])
@login_required
def api_admin_action(req_id, action):
    if current_user.role != 'admin': return jsonify({'error': 'Unauthorized'}), 403
    if action not in ['approve', 'reject']: return jsonify({'error': 'Invalid action'}), 400
    
    req = db.session.get(Request, req_id)
    if not req: return jsonify({'error': 'Not found'}), 404
    
    data = request.get_json() or {}
    req.status = action + 'd'
    req.admin_notes = data.get('notes', '')
    db.session.commit()
    return jsonify({'message': f'Request {action}d'})

@app.route('/api/admin/profile', methods=['POST'])
@login_required
def api_admin_profile():
    if current_user.role != 'admin': return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    current_user.name = data.get('name', current_user.name)
    current_user.email = data.get('email', current_user.email)
    if data.get('password'):
        current_user.password_hash = generate_password_hash(data.get('password'))
    db.session.commit()
    return jsonify({'message': 'Profile updated successfully'})

@app.route('/api/admin/stats', methods=['GET'])
@login_required
def api_admin_stats():
    if current_user.role != 'admin': return jsonify({'error': 'Unauthorized'}), 403
    return jsonify({
        'pending': Request.query.filter_by(status='pending').count(),
        'approved': Request.query.filter_by(status='approved').count(),
        'urgent': Request.query.filter_by(status='pending', priority='urgent').count(),
        'total': Request.query.count()
    })

# --- WORKER API ---

@app.route('/api/worker/requests', methods=['GET'])
@login_required
def api_worker_requests():
    if current_user.role != 'worker': return jsonify({'error': 'Unauthorized'}), 403
    requests = Request.query.filter(
        db.or_(
            Request.status == 'approved', 
            Request.worker_id == current_user.id
        )
    ).order_by(Request.created_at.desc()).all()
    return jsonify([r.to_dict() for r in requests])

# --- WORKER API ADDITIONS ---

@app.route('/api/worker/profile', methods=['GET', 'POST'])
@login_required
def api_worker_profile():
    if current_user.role != 'worker': return jsonify({'error': 'Unauthorized'}), 403
    
    if request.method == 'POST':
        data = request.get_json()
        current_user.name = data.get('name', current_user.name)
        current_user.email = data.get('email', current_user.email)
        current_user.department = data.get('department', current_user.department)
        
        if data.get('password'):
            current_user.password_hash = generate_password_hash(data.get('password'))
            
        db.session.commit()
        return jsonify({'message': 'Profile updated successfully'})
    
    return jsonify({
        'name': current_user.name,
        'email': current_user.email,
        'department': current_user.department
    })

@app.route('/api/worker/history', methods=['GET'])
@login_required
def api_worker_history():
    if current_user.role != 'worker': return jsonify({'error': 'Unauthorized'}), 403
    
    # Fetch only tasks completed by THIS specific worker
    completed_tasks = Request.query.filter_by(
        worker_id=current_user.id, 
        status='completed'
    ).order_by(Request.created_at.desc()).all()
    
    return jsonify([r.to_dict() for r in completed_tasks])

@app.route('/api/worker/requests/<req_id>/<action>', methods=['POST'])
@login_required
def api_worker_action(req_id, action):
    if current_user.role != 'worker': return jsonify({'error': 'Unauthorized'}), 403
    
    req = db.session.get(Request, req_id)
    if not req: return jsonify({'error': 'Not found'}), 404

    if action == 'claim' and req.status == 'approved':
        req.status = 'in_progress'
        req.worker_id = current_user.id
        db.session.commit()
        return jsonify({'message': 'Task claimed successfully'})
        
    elif action == 'complete' and req.status == 'in_progress' and req.worker_id == current_user.id:
        req.status = 'completed'
        db.session.commit()
        return jsonify({'message': 'Task marked as completed'})

    return jsonify({'error': 'Invalid action or state'}), 400

# --- FILE SERVING ---
@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)