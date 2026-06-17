from datetime import datetime, timezone
from app.extensions import db

class Admin(db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(150), nullable=True)

class Client(db.Model):
    __tablename__ = 'clients'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    temp_password_hash = db.Column(db.String(255), nullable=True)  # bcrypt hash of temp pw only — cleared after first login
    display_name = db.Column(db.String(150), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

class Appointment(db.Model):
    __tablename__ = 'appointments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(300), nullable=True)
    mobile = db.Column(db.String(20), nullable=True)
    whatsapp = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(150), nullable=True)
    # contact kept for backwards compatibility
    contact = db.Column(db.String(150), nullable=True)
    date = db.Column(db.DateTime, nullable=True)
    payment_status = db.Column(db.String(50), default='Pending')
    package = db.Column(db.String(100), nullable=True)  # e.g. 'Single Session' or 'Recommended Package'
    fees_paid = db.Column(db.String(100), nullable=True)  # "offer_price|original_price" locked at booking time

    # Store timestamp of booking
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class StudentAssessment(db.Model):
    __tablename__ = 'student_assessments'
    id = db.Column(db.Integer, primary_key=True)
    client_username = db.Column(db.String(80))
    personal_info = db.Column(db.JSON)
    interests = db.Column(db.JSON)
    aptitude = db.Column(db.JSON)
    personality = db.Column(db.JSON)
    career_vision = db.Column(db.Text)
    ai_response = db.Column(db.JSON)
    # Auto-save tracking
    status = db.Column(db.String(20), default='in_progress')  # in_progress | completed | ai_done | ai_failed
    current_step = db.Column(db.Integer, default=1)  # 1-5 (which section)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class SkillNestAdmission(db.Model):
    __tablename__ = 'skillnest_admissions'
    id = db.Column(db.Integer, primary_key=True)
    # ── Student Information ──────────────────────
    child_name = db.Column(db.String(150), nullable=False)
    dob = db.Column(db.String(20), nullable=True)           # Date of Birth
    child_age = db.Column(db.Integer, nullable=True)
    gender = db.Column(db.String(20), nullable=True)        # Male / Female / Other
    school_name = db.Column(db.String(200), nullable=True)
    class_grade = db.Column(db.String(50), nullable=True)
    # ── Parent / Guardian Details ────────────────
    father_name = db.Column(db.String(150), nullable=True)
    mother_name = db.Column(db.String(150), nullable=True)
    parent_name = db.Column(db.String(150), nullable=True)  # kept for compat
    parent_mobile = db.Column(db.String(20), nullable=False)
    alt_contact = db.Column(db.String(20), nullable=True)
    parent_email = db.Column(db.String(150), nullable=True)
    address = db.Column(db.String(300), nullable=True)
    # ── Academic & Learning ──────────────────────
    subjects_help = db.Column(db.Text, nullable=True)
    homework_support = db.Column(db.String(10), nullable=True)  # Yes / No
    child_strengths = db.Column(db.Text, nullable=True)
    areas_to_improve = db.Column(db.Text, nullable=True)
    # ── Behaviour & Health ───────────────────────
    child_behavior = db.Column(db.String(100), nullable=True)
    medical_condition = db.Column(db.Text, nullable=True)
    # ── Program Details ──────────────────────────
    preferred_timing = db.Column(db.String(50), nullable=True)  # 1-3PM / 3-5PM / Flexible
    evening_snack = db.Column(db.String(10), nullable=True)     # Yes / No
    # ── Status & Admin ───────────────────────────
    status = db.Column(db.String(20), default='pending')        # pending | approved | rejected
    payment_status = db.Column(db.String(50), default='Paid')
    batch_assigned = db.Column(db.String(100), nullable=True)
    fees_paid = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)                   # remarks
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Employee(db.Model):
    __tablename__ = 'employees'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    designation = db.Column(db.String(150), nullable=True)
    username = db.Column(db.String(100), unique=True, nullable=False)  # derived from name
    password_hash = db.Column(db.String(255), nullable=False)
    temp_password_hash = db.Column(db.String(255), nullable=True)  # bcrypt hash of temp pw only — cleared after first login
    must_change_password = db.Column(db.Boolean, default=True, nullable=False)
    email = db.Column(db.String(150), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    # JSON: {"appointments": true, "skillnest": true, "assessments": true, "gallery": true}
    permissions = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def has_permission(self, key):
        """Check a specific permission key, e.g. 'appt_history' or legacy 'appointments'."""
        if not self.permissions:
            return False
        # Direct key check
        val = self.permissions.get(key)
        if val is not None:
            return bool(val)
        # Legacy: if 'appointments' is True, grant all appt_ sub-perms
        legacy_map = {
            'appt_booking_status': 'appointments',
            'appt_pricing':        'appointments',
            'appt_history':        'appointments',
            'skillnest_admissions':'skillnest',
            'skillnest_settings':  'skillnest',
            'assessments_view':    'assessments',
            'assessments_create_client': 'assessments',
            'gallery_view':        'gallery',
            'contact_social':      'contact_social',
        }
        parent = legacy_map.get(key)
        if parent:
            return bool(self.permissions.get(parent, False))
        return False

    def has_any_perm(self, *keys):
        """Return True if any of the given keys is permitted."""
        return any(self.has_permission(k) for k in keys)

class SiteConfig(db.Model):

    """Key-value store for site-wide settings (e.g. counselling_fee)."""
    __tablename__ = 'site_config'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String(500), nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @classmethod
    def get(cls, key, default=None):
        row = cls.query.filter_by(key=key).first()
        return row.value if row else default

    @classmethod
    def set(cls, key, value):
        row = cls.query.filter_by(key=key).first()
        if row:
            row.value = value
            row.updated_at = datetime.now(timezone.utc)
        else:
            row = cls(key=key, value=value)
            db.session.add(row)
        db.session.commit()


