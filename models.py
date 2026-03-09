from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import uuid

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user') # 'user', 'admin', or 'worker'
    department = db.Column(db.String(50), default='General')
    is_verified = db.Column(db.Boolean, default=False)
    otp = db.Column(db.String(6), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)

class Request(db.Model):
    # Primary Key - Required for SQLAlchemy
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4())[:8])
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.String(20), nullable=False)
    end_date = db.Column(db.String(20))
    priority = db.Column(db.String(20), default='medium')
    description = db.Column(db.Text, nullable=False)
    file_path = db.Column(db.String(200))
    # Price Field
    price = db.Column(db.Float, default=0.0) 
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    admin_notes = db.Column(db.Text)

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('requests', lazy=True))
    worker = db.relationship('User', foreign_keys=[worker_id], backref=db.backref('assigned_tasks', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'type': self.type,
            'startDate': self.start_date,
            'endDate': self.end_date,
            'priority': self.priority,
            'description': self.description,
            'file_path': self.file_path,
            'price': self.price, # Ensure price is included for Admin/Worker views
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'admin_notes': self.admin_notes,
            'user': self.user.name,
            'userDept': self.user.department,
            'worker': self.worker.name if self.worker else None
        }