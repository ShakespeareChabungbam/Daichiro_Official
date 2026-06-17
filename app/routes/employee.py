from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app.models import Employee, Appointment, StudentAssessment, SkillNestAdmission, SiteConfig, Client
from app.extensions import db, bcrypt
from app.utils.email_utils import generate_reset_token, verify_reset_token, send_reset_email
from itsdangerous import SignatureExpired, BadSignature
import re, string, random

employee_bp = Blueprint('employee', __name__)

# ── Helpers ─────────────────────────────────────────────────────────────────

def current_employee():
    eid = session.get('employee_id')
    return Employee.query.get(eid) if eid else None

def perm(key):
    """Decorator: require a specific sub-permission."""
    def decorator(fn):
        from functools import wraps
        @wraps(fn)
        def wrapped(*args, **kwargs):
            emp = current_employee()
            if not emp or not emp.has_permission(key):
                flash('You do not have access to this section.', 'error')
                return redirect(url_for('employee.dashboard'))
            return fn(*args, **kwargs)
        return wrapped
    return decorator

# ── Guards ───────────────────────────────────────────────────────────────────

@employee_bp.before_request
def require_employee_login():
    open_routes = {'employee.login', 'employee.logout', 'employee.forgot_password', 'employee.reset_password'}
    if request.endpoint in open_routes:
        return
    if 'employee_id' not in session:
        return redirect(url_for('employee.login'))
    if session.get('emp_must_change') and request.endpoint != 'employee.change_password':
        return redirect(url_for('employee.change_password'))

    # Dynamic permission mapper for ported routes
    # Value can be a single string OR a list (any match grants access)
    perm_map = {
        # Appointments — landing page accepts ANY appt sub-perm
        'appointments':             ['appt_booking_status', 'appt_pricing', 'appt_history'],
        'appointments_page':        ['appt_booking_status', 'appt_pricing', 'appt_history'],
        'booking_status_page':      'appt_booking_status',
        'set_booking_status':       'appt_booking_status',
        'pricing_page':             'appt_pricing',
        'set_pricing':              'appt_pricing',
        'appointment_history_page': 'appt_history',
        'delete_appointment':       'appt_history',
        'send_invoice':             'appt_history',
        'send_manual_invoice':      'appt_history',
        'mark_appointment_paid':    'appt_history',

        # SkillNest — landing page accepts ANY skillnest sub-perm
        'skillnest':                    ['skillnest_admissions', 'skillnest_settings'],
        'skillnest_page':               ['skillnest_admissions', 'skillnest_settings'],
        'skillnest_records_page':       'skillnest_admissions',
        'skillnest_add_admission_page': 'skillnest_admissions',
        'skillnest_add_manual':         'skillnest_admissions',
        'skillnest_edit':               'skillnest_admissions',
        'skillnest_approve':            'skillnest_admissions',
        'skillnest_reject':             'skillnest_admissions',
        'skillnest_delete':             'skillnest_admissions',
        'skillnest_mark_paid':          'skillnest_admissions',
        'skillnest_settings_page':      'skillnest_settings',
        'skillnest_set_settings':       'skillnest_settings',

        # Assessments — landing page accepts ANY assessments sub-perm
        'assessments':                  ['assessments_view', 'assessments_create_client'],
        'assessments_page':             ['assessments_view', 'assessments_create_client'],
        'assessments_ai_done':          'assessments_view',
        'assessments_pending':          'assessments_view',
        'assessments_in_progress':      'assessments_view',
        'assessments_trash':            'assessments_view',
        'trash_assessment':             'assessments_view',
        'restore_assessment':           'assessments_view',
        'delete_permanent_assessment':  'assessments_view',
        'empty_trash':                  'assessments_view',
        'upload_assessment':            'assessments_create_client',
        'save_scanned_assessment':      'assessments_create_client',
        'reanalyze_assessment':         'assessments_create_client',
        'create_client':                'assessments_create_client',
        'assessment_pdf':               'assessments_view',
        'manual_assessment':            'assessments_create_client',

        'gallery':        'gallery_view',
        'contact_social': 'contact_social',
        'clients_page':   'assessments_view',
    }
    endpoint_name = request.endpoint.split('.')[-1]
    if endpoint_name in perm_map:
        emp = current_employee()
        required = perm_map[endpoint_name]
        # Support single string or list of any-match
        if isinstance(required, list):
            allowed = emp and emp.has_any_perm(*required)
        else:
            allowed = emp and emp.has_permission(required)
        if not allowed:
            flash('You do not have permission to access that section.', 'error')
            return redirect(url_for('employee.dashboard'))


# ── Auth ─────────────────────────────────────────────────────────────────────

@employee_bp.route('/login', methods=['GET', 'POST'])
def login():
    return redirect(url_for('admin.login'))

@employee_bp.route('/logout')
def logout():
    for k in ['employee_id', 'emp_name', 'emp_designation', 'emp_must_change']:
        session.pop(k, None)
    return redirect(url_for('admin.login'))

@employee_bp.route('/change-password', methods=['GET', 'POST'])
def change_password():
    emp = current_employee()
    if not emp:
        return redirect(url_for('admin.login'))
    must_change = session.get('emp_must_change', False)
    template = 'employee/force_change_password.html' if must_change else 'employee/change_password.html'
    if request.method == 'POST':
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')
        errors = []
        if len(new_pw) < 8:           errors.append('At least 8 characters required.')
        if not re.search(r'[A-Z]', new_pw): errors.append('Must include uppercase letter.')
        if not re.search(r'[a-z]', new_pw): errors.append('Must include lowercase letter.')
        if not re.search(r'\d', new_pw):    errors.append('Must include a number.')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-]', new_pw): errors.append('Must include a special character.')
        if new_pw != confirm_pw:       errors.append('Passwords do not match.')
        if emp.temp_password_hash and new_pw == emp.temp_password_hash:
            errors.append('You cannot reuse the generated password.')
        if errors:
            for e in errors: flash(e, 'error')
            return render_template(template, emp=emp)
        emp.password_hash = bcrypt.generate_password_hash(new_pw).decode('utf-8')
        emp.must_change_password = False
        emp.temp_password_hash = None
        db.session.commit()
        session['emp_must_change'] = False
        flash('Password changed successfully! Welcome.', 'success')
        return redirect(url_for('employee.dashboard'))
    return render_template(template, emp=emp, active_page='change_password')


@employee_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    emp = current_employee()
    if not emp:
        return redirect(url_for('admin.login'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        # Check email uniqueness (excluding self)
        if email:
            existing = Employee.query.filter_by(email=email).first()
            if existing and existing.id != emp.id:
                flash('That email is already used by another account.', 'error')
                return render_template('employee/profile.html', emp=emp)
        emp.email = email or None
        emp.phone = phone or None
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('employee.profile'))
    return render_template('employee/profile.html', emp=emp, active_page='profile')


@employee_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    return redirect(url_for('admin.forgot_password'))


@employee_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    return redirect(url_for('admin.reset_password', token=token))

# ── Dashboard ────────────────────────────────────────────────────────────────

@employee_bp.route('/dashboard')
def dashboard():
    emp = current_employee()
    if not emp: return redirect(url_for('admin.login'))
    
    appointments = Appointment.query.order_by(Appointment.date.asc()).all()
    clients = Client.query.order_by(Client.created_at.desc()).all()
    assessments = StudentAssessment.query.order_by(StudentAssessment.created_at.desc()).all()
    
    return render_template('employee/dashboard.html', emp=emp, perms=emp.permissions or {}, active_page='dashboard', appointments=appointments, clients=clients, assessments=assessments)


# ── PORTED ADMIN ROUTES ──

# Provide emp to templates using context_processor so all templates have access to emp.has_permission()
@employee_bp.context_processor
def inject_emp():
    return dict(emp=current_employee())

@employee_bp.route('/clients')
def clients_page():
    clients = Client.query.order_by(Client.created_at.desc()).all()
    return render_template('employee/clients.html', clients=clients, active_page='clients')

@employee_bp.route('/appointments')
def appointments_page():
    """Hub — shows 3 navigation cards."""
    appointments = Appointment.query.order_by(Appointment.created_at.desc()).all()
    counselling_fee = SiteConfig.get('counselling_fee')
    offer_price = SiteConfig.get('offer_price')
    package_price = SiteConfig.get('package_price')
    package_offer_price = SiteConfig.get('package_offer_price')
    booking_closed = SiteConfig.get('booking_closed', '0')
    return render_template('employee/appointments.html',
                           appointments=appointments,
                           active_page='appointments',
                           counselling_fee=counselling_fee,
                           offer_price=offer_price,
                           package_price=package_price,
                           package_offer_price=package_offer_price,
                           booking_closed=booking_closed)

@employee_bp.route('/appointments/booking-status')
def booking_status_page():
    booking_closed = SiteConfig.get('booking_closed', '0')
    booking_message = SiteConfig.get('booking_message')
    booking_reopen_date = SiteConfig.get('booking_reopen_date')
    return render_template('employee/booking_status.html',
                           active_page='appointments',
                           booking_closed=booking_closed,
                           booking_message=booking_message,
                           booking_reopen_date=booking_reopen_date)

@employee_bp.route('/appointments/pricing')
def pricing_page():
    counselling_fee = SiteConfig.get('counselling_fee')
    offer_price = SiteConfig.get('offer_price')
    package_price = SiteConfig.get('package_price')
    package_offer_price = SiteConfig.get('package_offer_price')
    offer_label = SiteConfig.get('offer_label')
    offer_expiry = SiteConfig.get('offer_expiry')
    return render_template('employee/pricing_management.html',
                           active_page='appointments',
                           counselling_fee=counselling_fee,
                           offer_price=offer_price,
                           package_price=package_price,
                           package_offer_price=package_offer_price,
                           offer_label=offer_label,
                           offer_expiry=offer_expiry)

@employee_bp.route('/appointments/history')
def appointment_history_page():
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=45)
    # Auto-purge appointments older than 45 days
    Appointment.query.filter(Appointment.created_at < cutoff).delete()
    db.session.commit()
    appointments = Appointment.query.order_by(Appointment.created_at.desc()).all()
    session_fee   = SiteConfig.get('counselling_fee')
    session_offer = SiteConfig.get('offer_price')
    package_fee   = SiteConfig.get('package_price')
    package_offer = SiteConfig.get('package_offer_price')
    return render_template('employee/appointment_history.html',
                           active_page='appointments',
                           appointments=appointments,
                           session_fee=session_fee,
                           session_offer=session_offer,
                           package_fee=package_fee,
                           package_offer=package_offer)

@employee_bp.route('/appointments/<int:appt_id>/delete', methods=['POST'])
def delete_appointment(appt_id):
    appt = db.session.get(Appointment, appt_id)
    if not appt: abort(404)
    db.session.delete(appt)
    db.session.commit()
    flash(f'Booking for {appt.name} has been deleted.', 'success')
    return redirect(url_for('employee.appointment_history_page'))

@employee_bp.route('/appointments/<int:appt_id>/send-invoice', methods=['POST'])
def send_invoice(appt_id):
    """Manually send the invoice to the client's email (admin/staff triggered)."""
    from app.utils.email_utils import send_invoice_email
    appt = db.session.get(Appointment, appt_id)
    if not appt:
        abort(404)

    # Allow admin to override the recipient, subject, and add a note
    custom_to    = request.form.get('custom_to_email', '').strip()
    custom_subj  = request.form.get('custom_subject', '').strip() or None
    custom_note  = request.form.get('custom_note', '').strip() or None
    to_email     = custom_to if custom_to else appt.email

    if not to_email:
        flash(f'No email address provided for {appt.name}. Cannot send invoice.', 'error')
        return redirect(url_for('employee.appointment_history_page'))

    # Parse fees_paid "offer|original" as fallback
    offer_fee = original_fee = None
    if appt.fees_paid and '|' in appt.fees_paid:
        parts = appt.fees_paid.split('|', 1)
        offer_fee, original_fee = parts[0].strip(), parts[1].strip()
    elif appt.fees_paid:
        offer_fee = original_fee = appt.fees_paid.strip()

    is_pkg = appt.package and any(k in appt.package.lower() for k in ('recommended', 'complete', 'package'))
    pkg_label = 'Recommended Package — Counselling' if is_pkg else 'Single Counselling Session'
    import datetime as _dt
    booked_on = (appt.created_at + _dt.timedelta(hours=5, minutes=30)).strftime('%d %b %Y, %I:%M %p') if appt.created_at else '—'
    inv_no    = f'INV-{appt_id:04d}'

    # Use form overrides from editable invoice summary inputs
    ov_name    = request.form.get('ov_name', '').strip()
    ov_package = request.form.get('ov_package', '').strip()
    ov_amount  = request.form.get('ov_amount', '').strip()
    ov_booked  = request.form.get('ov_booked', '').strip()
    ov_ref     = request.form.get('ov_ref', '').strip()

    final_name    = ov_name    or appt.name
    final_package = ov_package or pkg_label
    final_booked  = ov_booked  or booked_on
    final_inv_no  = ov_ref     or inv_no
    if ov_amount:
        amt_clean = ov_amount.lstrip('\u20b9Rs. ').strip()
        final_offer = final_original = amt_clean
    else:
        final_offer    = offer_fee    or ''
        final_original = original_fee or ''

    ok = send_invoice_email(
        to_email=to_email,
        name=final_name,
        package=final_package,
        offer_fee=final_offer,
        original_fee=final_original,
        booked_on=final_booked,
        inv_no=final_inv_no,
        subject=custom_subj,
        custom_note=custom_note
    )
    if ok:
        flash(f'✅ Invoice sent to {to_email} for {final_name}.', 'success')
    else:
        flash(f'Failed to send invoice to {to_email}. Check email settings.', 'error')
    return redirect(url_for('employee.appointment_history_page'))

@employee_bp.route('/send-manual-invoice', methods=['POST'])
def send_manual_invoice():
    """Send a fully manual invoice — no appointment record required."""
    from app.utils.email_utils import send_invoice_email
    to_email    = request.form.get('manual_to_email', '').strip()
    custom_subj = request.form.get('manual_subject', '').strip() or None
    custom_note = request.form.get('manual_note', '').strip() or None
    m_name      = request.form.get('manual_name', '').strip()
    m_package   = request.form.get('manual_package', '').strip()
    m_amount    = request.form.get('manual_amount', '').strip()
    m_booked    = request.form.get('manual_booked', '').strip()
    m_ref       = request.form.get('manual_ref', '').strip()

    if not to_email:
        flash('Recipient email address is required.', 'error')
        return redirect(url_for('employee.appointment_history_page'))

    amt_clean = m_amount.lstrip('\u20b9Rs. ').strip() if m_amount else ''

    ok = send_invoice_email(
        to_email=to_email,
        name=m_name or 'Client',
        package=m_package or 'Counselling Session',
        offer_fee=amt_clean,
        original_fee=amt_clean,
        booked_on=m_booked,
        inv_no=m_ref,
        subject=custom_subj,
        custom_note=custom_note
    )
    if ok:
        flash(f'✅ Manual invoice sent to {to_email}.', 'success')
    else:
        flash(f'Failed to send manual invoice to {to_email}. Check email settings.', 'error')
    return redirect(url_for('employee.appointment_history_page'))

@employee_bp.route('/set-pricing', methods=['POST'])
def set_pricing():

    """Save all appointment pricing fields in one go."""
    def save_int(key, form_key):
        val = request.form.get(form_key, '').strip()
        if val:
            try:
                v = int(float(val))   # float() first → handles "299.987", int() → truncates to 299
                if v < 0: raise ValueError
                SiteConfig.set(key, str(v))
            except (ValueError, TypeError):
                flash(f'Invalid value for {form_key}. Please enter a valid number.', 'error')
                return False
        else:
            SiteConfig.set(key, None)
        return True

    ok = True
    ok = save_int('counselling_fee', 'session_price') and ok
    ok = save_int('offer_price', 'session_offer_price') and ok
    ok = save_int('package_price', 'package_price') and ok
    ok = save_int('package_offer_price', 'package_offer_price') and ok

    offer_label = request.form.get('offer_label', '').strip()
    SiteConfig.set('offer_label', offer_label or None)

    offer_expiry = request.form.get('offer_expiry', '').strip()
    SiteConfig.set('offer_expiry', offer_expiry or None)

    if ok:
        flash('Pricing updated successfully! Changes are now live on the booking page.', 'success')
    return redirect(url_for('employee.pricing_page'))

@employee_bp.route('/set-booking-status', methods=['POST'])
def set_booking_status():
    """Open or close bookings with an optional message and reopen date."""
    closed = request.form.get('booking_closed', '0').strip()
    SiteConfig.set('booking_closed', '1' if closed == '1' else '0')

    message = request.form.get('booking_message', '').strip()
    SiteConfig.set('booking_message', message or None)

    reopen_date = request.form.get('booking_reopen_date', '').strip()
    SiteConfig.set('booking_reopen_date', reopen_date or None)

    if closed == '1':
        flash('Bookings have been CLOSED. Clients will see the closed notice on the booking page.', 'success')
    else:
        flash('Bookings are now OPEN. Clients can book again.', 'success')
    return redirect(url_for('employee.booking_status_page'))

@employee_bp.route('/appointment/<int:appointment_id>/mark-paid', methods=['POST'])
def mark_appointment_paid(appointment_id):
    appointment = db.session.get(Appointment, appointment_id)
    if not appointment: abort(404)
    appointment.payment_status = 'Paid'
    db.session.commit()
    flash(f'Booking for {appointment.name} marked as Paid.', 'success')
    return redirect(url_for('employee.appointment_history_page'))

def _auto_purge_assessments():
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=90)
    StudentAssessment.query.filter(StudentAssessment.created_at < cutoff).delete()
    db.session.commit()

@employee_bp.route('/assessments')
def assessments_page():
    _auto_purge_assessments()
    assessments = StudentAssessment.query.filter(StudentAssessment.status != 'trashed').order_by(StudentAssessment.created_at.desc()).all()
    all_trash = StudentAssessment.query.filter_by(status='trashed').count()
    clients = Client.query.order_by(Client.created_at.desc()).all()
    active_clients = {c.username: c for c in clients}
    all_ai_done  = [a for a in assessments if a.ai_response]
    all_pending  = [a for a in assessments if not a.ai_response and a.status != 'in_progress']
    all_progress = [a for a in assessments if a.status == 'in_progress']
    return render_template('employee/assessments.html', assessments=assessments, clients=clients,
                           active_clients=active_clients, active_page='assessments',
                           all_ai_done=all_ai_done, all_pending=all_pending, all_progress=all_progress)

@employee_bp.route('/assessments/ai-done')
def assessments_ai_done():
    _auto_purge_assessments()
    assessments = StudentAssessment.query.filter(StudentAssessment.status != 'trashed').order_by(StudentAssessment.created_at.desc()).all()
    clients = Client.query.order_by(Client.created_at.desc()).all()
    active_clients = {c.username: c for c in clients}
    records = [a for a in assessments if a.ai_response]
    return render_template('employee/assessments_group.html', records=records, active_clients=active_clients,
                           active_page='assessments', group_key='ai-done',
                           group_title='AI Analysis Complete', group_icon='🧠',
                           group_color='emerald', back_url=url_for('employee.assessments_page'))

@employee_bp.route('/assessments/pending')
def assessments_pending():
    _auto_purge_assessments()
    assessments = StudentAssessment.query.filter(StudentAssessment.status != 'trashed').order_by(StudentAssessment.created_at.desc()).all()
    clients = Client.query.order_by(Client.created_at.desc()).all()
    active_clients = {c.username: c for c in clients}
    records = [a for a in assessments if not a.ai_response and a.status != 'in_progress']
    return render_template('employee/assessments_group.html', records=records, active_clients=active_clients,
                           active_page='assessments', group_key='pending',
                           group_title='Pending AI Analysis', group_icon='⏳',
                           group_color='indigo', back_url=url_for('employee.assessments_page'))

@employee_bp.route('/assessments/in-progress')
def assessments_in_progress():
    _auto_purge_assessments()
    assessments = StudentAssessment.query.filter(StudentAssessment.status != 'trashed').order_by(StudentAssessment.created_at.desc()).all()
    clients = Client.query.order_by(Client.created_at.desc()).all()
    active_clients = {c.username: c for c in clients}
    records = [a for a in assessments if a.status == 'in_progress']
    return render_template('employee/assessments_group.html', records=records, active_clients=active_clients,
                           active_page='assessments', group_key='progress',
                           group_title='In Progress', group_icon='🔄',
                           group_color='amber', back_url=url_for('employee.assessments_page'))

@employee_bp.route('/assessments/trash')
def assessments_trash():
    _auto_purge_assessments()
    records = StudentAssessment.query.filter_by(status='trashed').order_by(StudentAssessment.created_at.desc()).all()
    clients = Client.query.all()
    active_clients = {c.username: c for c in clients}
    return render_template('employee/assessments_group.html', records=records, active_clients=active_clients,
                           active_page='assessments', group_key='trash',
                           group_title='Trash Bin', group_icon='🗑️',
                           group_color='red', back_url=url_for('employee.assessments_page'))

@employee_bp.route('/assessment/<int:assessment_id>/trash', methods=['POST'])
def trash_assessment(assessment_id):
    assessment = db.session.get(StudentAssessment, assessment_id)
    if not assessment: abort(404)
    try:
        assessment.status = 'trashed'
        db.session.commit()
        return jsonify({'success': True, 'message': 'Moved to Trash Bin.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error moving to trash.'}), 500

@employee_bp.route('/assessment/<int:assessment_id>/restore', methods=['POST'])
def restore_assessment(assessment_id):
    assessment = db.session.get(StudentAssessment, assessment_id)
    if not assessment: abort(404)
    try:
        # Deduce original status
        if assessment.ai_response:
            assessment.status = 'ai_done'
        elif assessment.current_step >= 5:
            assessment.status = 'submitted'  # completed assessments use 'submitted'
        else:
            assessment.status = 'in_progress'
        db.session.commit()
        return jsonify({'success': True, 'message': 'Assessment Restored.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error restoring.'}), 500

@employee_bp.route('/assessment/<int:assessment_id>/delete_permanent', methods=['POST'])
def delete_permanent_assessment(assessment_id):
    assessment = db.session.get(StudentAssessment, assessment_id)
    if not assessment: abort(404)
    try:
        db.session.delete(assessment)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Permanently Deleted.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error deleting.'}), 500

@employee_bp.route('/assessments/empty_trash', methods=['POST'])
def empty_trash():
    try:
        trashed_items = StudentAssessment.query.filter_by(status='trashed').all()
        count = len(trashed_items)
        for item in trashed_items:
            db.session.delete(item)
        db.session.commit()
        return jsonify({'success': True, 'message': f'Emptied {count} items from Trash Bin.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error emptying trash.'}), 500

@employee_bp.route('/client/create', methods=['POST'])
def create_client():
    client_name = request.form.get('client_name', '').strip()
    
    # Generate unique random username and password
    chars = string.ascii_letters + string.digits
    while True:
        temp_username = 'student_' + ''.join(random.choice(string.digits) for _ in range(5))
        if not Client.query.filter_by(username=temp_username).first():
            break
    temp_password = ''.join(random.choice(chars) for _ in range(10))
    
    hashed_temp = bcrypt.generate_password_hash(temp_password).decode('utf-8')
    new_client = Client(username=temp_username, password_hash=hashed_temp, display_name=client_name or None, temp_password_hash=temp_password)
    try:
        db.session.add(new_client)
        db.session.commit()
        name_label = f" ({client_name})" if client_name else ""
        flash(f'Credentials Generated{name_label}! Username: {temp_username} | Password: {temp_password}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error generating client: {str(e)}', 'error')
        
    return redirect(url_for('employee.assessments_page'))

@employee_bp.route('/assessment/<int:assessment_id>/pdf')
def assessment_pdf(assessment_id):
    assessment = db.session.get(StudentAssessment, assessment_id)
    if not assessment: abort(404)
    # Parse career_vision if stored as string
    career_vision = assessment.career_vision
    if isinstance(career_vision, str):
        try:
            career_vision = json.loads(career_vision)
        except (json.JSONDecodeError, TypeError):
            career_vision = {'raw': career_vision}
    return render_template('employee/assessment_pdf.html', a=assessment, career_vision=career_vision)

@employee_bp.route('/upload-assessment', methods=['GET', 'POST'])
def upload_assessment():
    if request.method == 'POST':
        files = request.files.getlist('photos')
        if not files or all(f.filename == '' for f in files):
            flash('Please select at least one photo.', 'error')
            return redirect(url_for('employee.upload_assessment'))

        # Get API key
        from google import genai as new_genai
        from google.genai import types as genai_types
        api_key = SiteConfig.get('gemini_api_key') or os.environ.get('GEMINI_API_KEY')
        if not api_key:
            flash('Gemini API key is required for photo scanning. Please set it in the dashboard first.', 'error')
            return redirect(url_for('employee.upload_assessment'))

        # Read and COMPRESS all uploaded images before sending to Gemini
        image_bytes_list = []
        for f in files:
            if f.filename == '':
                continue
            img_data = f.read()

            # Compress image using Pillow
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(img_data))
                if img.mode in ('RGBA', 'P', 'LA'):
                    img = img.convert('RGB')
                max_size = 2048  # Higher resolution preserves handwriting detail
                if max(img.width, img.height) > max_size:
                    ratio = max_size / max(img.width, img.height)
                    img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
                output = io.BytesIO()
                img.save(output, format='JPEG', quality=92, optimize=True)  # Higher quality = readable handwriting
                img_data = output.getvalue()
            except Exception:
                pass

            image_bytes_list.append(img_data)

        if not image_bytes_list:
            flash('No valid images found.', 'error')
            return redirect(url_for('employee.upload_assessment'))

        # Use Gemini Vision to extract assessment data
        client = new_genai.Client(api_key=api_key)
        gemini_model = SiteConfig.get('gemini_model') or 'gemini-2.0-flash'

        extraction_prompt = """You are a precise OCR and form-data extraction system. You are looking at photos of a printed "Student Career Interest & Aptitude Questionnaire" form from Daichiro Professional Skills Academy. The student has filled in the form by hand.

Your job: read every section carefully and extract ALL marked/written data into the exact JSON structure below.

=== HOW TO READ EACH SECTION ===

SECTION A — PERSONAL INFORMATION (handwritten fields at the top)
  Read the text the student wrote next to: Full Name, Class/Grade, School Name, Contact Number, Email.

SECTION B — INTERESTS (checkbox grids — multiple selections possible)
  Look for ticks (✓), crosses (✗), filled circles (●), or any ink mark inside or next to a checkbox box.
  Sub-sections:
  1. Activities Enjoyed (10 options in a grid)
  2. Favourite Subjects (16 options in a grid)
  3. Professions of Interest (10 options in a grid)

SECTION C — APTITUDE SELF-ASSESSMENT (rating scale 1–5)
  This section has 9 skill rows. Each row has 5 circular bubbles numbered 1 to 5 from left to right.
  The student fills/marks ONE bubble per row.
  Look at which circle is filled (darkened, circled, ticked, or has any mark) for each row.
  Rows in order:
    Row 1: "Solving logical or numerical problems" → key: logical
    Row 2: "Understanding scientific concepts" → key: science
    Row 3: "Writing or expressing yourself clearly" → key: writing
    Row 4: "Using computers or apps" → key: computers
    Row 5: "Creating or designing something" → key: design
    Row 6: "Speaking in public or leading a team" → key: speaking
    Row 7: "Planning or organizing tasks" → key: planning
    Row 8: "Helping others solve their problems" → key: helping
    Row 9: "Learning new technologies quickly" → key: tech
  Output each as a number string "1", "2", "3", "4", or "5". If unclear, use "3".

SECTION D — PERSONALITY & VALUES (checkbox list — multiple selections)
  Look for ticks or marks next to personality statements.

SECTION E — CAREER VISION (handwritten short answers)
  Read the written answers for: current careers considering, 5-year goals, ideal future life.

=== EXACT OPTION LISTS (use EXACTLY these strings, do not paraphrase) ===

Activities (Section B):
  "Solving math problems or puzzles", "Drawing, painting, or designing", "Writing stories or essays",
  "Playing computer games or coding", "Helping others with their problems",
  "Working with tools or machines", "Participating in debates or public speaking",
  "Taking care of animals or nature", "Organizing events or planning tasks",
  "Selling or promoting products/services"

Subjects (Section B):
  "Mathematics", "Science - Physics", "Chemistry", "Biology", "English", "Languages",
  "Computer Science / IT", "Social Science", "History", "Business Studies", "Economics",
  "Art", "Music", "Drama", "Physical Education", "Environmental Studies"

Professions (Section B):
  "Doctor / Nurse", "Engineer / Scientist", "Teacher / Professor", "Artist / Designer",
  "Business Owner / Entrepreneur", "Lawyer / Judge", "Software Developer / Game Designer",
  "Police / Army Officer", "Social Worker / Counselor", "YouTuber / Influencer / Filmmaker"

Personality Statements (Section D — match exactly):
  "I enjoy solving problems or challenges", "I like to express myself creatively",
  "I prefer working independently", "I like working with others in a team",
  "I care about helping people and making a difference", "I like leading and taking responsibility",
  "I enjoy experimenting and learning how things work",
  "I like keeping things organized and structured",
  "I enjoy physical activity or outdoor work"

=== OUTPUT ===
Return ONLY valid JSON, no explanation, no markdown:
{
  "personal_info": {
    "full_name": "",
    "class_grade": "",
    "school_name": "",
    "contact_number": "",
    "email": ""
  },
  "interests": {
    "activities": [],
    "subjects": [],
    "professions": []
  },
  "aptitude": {
    "logical": "3",
    "science": "3",
    "writing": "3",
    "computers": "3",
    "design": "3",
    "speaking": "3",
    "planning": "3",
    "helping": "3",
    "tech": "3"
  },
  "personality": [],
  "career_vision": {
    "current_careers": "",
    "five_year_goals": "",
    "ideal_life": ""
  }
}
"""

        # Build content parts for Gemini (new SDK format)
        content_parts = [extraction_prompt]
        for img_data in image_bytes_list:
            content_parts.append(
                genai_types.Part.from_bytes(data=img_data, mime_type='image/jpeg')
            )

        try:
            response = client.models.generate_content(
                model=gemini_model,
                contents=content_parts
            )
            text = response.text.strip()
            # Strip markdown code fences if present
            if text.startswith('```'):
                text = text.split('```')[1]
                if text.startswith('json'):
                    text = text[4:]
                text = text.strip()
            if text.endswith('```'):
                text = text[:-3].strip()
            extracted = json.loads(text)

            # Store in session for the review page
            session['scanned_assessment'] = extracted
            flash('Assessment digitized successfully! Please review the extracted data below.', 'success')
            return render_template('employee/review_scanned.html',
                                   data=extracted,
                                   active_page='assessments')

        except Exception as e:
            from flask import current_app
            current_app.logger.error(f"Photo scan error: {e}", exc_info=True)
            str_e = str(e)
            if '503' in str_e or 'UNAVAILABLE' in str_e or 'high demand' in str_e.lower():
                flash('Google Gemini API is currently experiencing high demand. Please try again later or switch your model in settings.', 'error')
            else:
                flash('Error scanning photos. Please check your API key and model.', 'error')
            return redirect(url_for('employee.upload_assessment'))

    return render_template('employee/upload_assessment.html', active_page='assessments')

@employee_bp.route('/save-scanned-assessment', methods=['POST'])
def save_scanned_assessment():
    """Save reviewed/edited scanned assessment and run AI analysis."""
    try:
        # Get the edited data from the form
        personal_info = {
            'full_name': request.form.get('full_name', ''),
            'class_grade': request.form.get('class_grade', ''),
            'school_name': request.form.get('school_name', ''),
            'contact_number': request.form.get('contact_number', ''),
            'email': request.form.get('email', '')
        }

        activities = request.form.getlist('activities')
        subjects = request.form.getlist('subjects')
        professions = request.form.getlist('professions')
        interests = {'activities': activities, 'subjects': subjects, 'professions': professions}

        aptitude = {
            'logical': request.form.get('apt_logical', '3'),
            'science': request.form.get('apt_science', '3'),
            'writing': request.form.get('apt_writing', '3'),
            'computers': request.form.get('apt_computers', '3'),
            'design': request.form.get('apt_design', '3'),
            'speaking': request.form.get('apt_speaking', '3'),
            'planning': request.form.get('apt_planning', '3'),
            'helping': request.form.get('apt_helping', '3'),
            'tech': request.form.get('apt_tech', '3'),
        }

        personality = request.form.getlist('personality')

        career_vision = {
            'current_careers': request.form.get('vision_careers', ''),
            'five_year_goals': request.form.get('vision_goals', ''),
            'ideal_life': request.form.get('vision_life', '')
        }

        # Run AI analysis (same as client assessment)
        ai_data = _run_ai_analysis(personal_info, interests, aptitude, personality, career_vision)

        # Save to database
        new_assessment = StudentAssessment(
            client_username='scan_upload',
            personal_info=personal_info,
            interests=interests,
            aptitude=aptitude,
            personality=personality,
            career_vision=json.dumps(career_vision),
            ai_response=ai_data,
            status='ai_done'
        )
        db.session.add(new_assessment)
        db.session.commit()

        session.pop('scanned_assessment', None)
        flash(f'Assessment for {personal_info["full_name"]} saved and analyzed successfully!', 'success')
        return redirect(url_for('employee.assessments_page'))

    except Exception as e:
        db.session.rollback()
        from flask import current_app
        current_app.logger.error(f"Assessment save error: {e}", exc_info=True)
        flash('Error saving assessment. An internal error occurred.', 'error')
        return redirect(url_for('employee.upload_assessment'))

@employee_bp.route('/assessment/<int:assessment_id>/reanalyze', methods=['POST'])
def reanalyze_assessment(assessment_id):
    """Re-run AI analysis on an existing assessment. Returns JSON for AJAX."""
    assessment = db.session.get(StudentAssessment, assessment_id)
    if not assessment: abort(404)
    try:
        career_vision = assessment.career_vision
        if isinstance(career_vision, str):
            try:
                career_vision = json.loads(career_vision)
            except:
                career_vision = {'current_careers': career_vision, 'five_year_goals': '', 'ideal_life': ''}

        ai_data = _run_ai_analysis(
            assessment.personal_info or {},
            assessment.interests or {},
            assessment.aptitude or {},
            assessment.personality or [],
            career_vision if isinstance(career_vision, dict) else {}
        )
        assessment.ai_response = ai_data
        assessment.status = 'ai_done'
        db.session.commit()
        name = assessment.personal_info.get('full_name', 'student') if assessment.personal_info else 'student'
        return jsonify({'success': True, 'message': f'AI analysis complete for {name}!', 'name': name})
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Reanalyze error: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'An internal error occurred during analysis.'}), 500

def _run_ai_analysis(personal_info, interests, aptitude, personality, career_vision):
    """Shared AI analysis function used by both client assessment and admin scan upload."""
    from google import genai

    assessment_summary = f"""
SECTION A — PERSONAL INFORMATION:
Full Name: {personal_info.get('full_name','')}
Class/Grade: {personal_info.get('class_grade','')}
School Name: {personal_info.get('school_name','')}

SECTION B — INTERESTS:
Activities Enjoyed: {', '.join(interests.get('activities',[]))}
Favourite Subjects: {', '.join(interests.get('subjects',[]))}
Professions of Interest: {', '.join(interests.get('professions',[]))}

SECTION C — APTITUDE SELF-ASSESSMENT (1=Not Confident, 5=Very Confident):
Solving logical/numerical problems: {aptitude.get('logical','3')}
Understanding scientific concepts: {aptitude.get('science','3')}
Writing or expressing yourself clearly: {aptitude.get('writing','3')}
Using computers or apps: {aptitude.get('computers','3')}
Creating or designing something: {aptitude.get('design','3')}
Speaking in public or leading a team: {aptitude.get('speaking','3')}
Planning or organizing tasks: {aptitude.get('planning','3')}
Helping others solve their problems: {aptitude.get('helping','3')}
Learning new technologies quickly: {aptitude.get('tech','3')}

SECTION D — PERSONALITY & VALUES:
{', '.join(personality) if personality else 'None selected'}

SECTION E — CAREER VISION:
Currently considering: {career_vision.get('current_careers','')}
5-year goals: {career_vision.get('five_year_goals','')}
Ideal future life: {career_vision.get('ideal_life','')}
"""

    api_key = SiteConfig.get('gemini_api_key') or os.environ.get('GEMINI_API_KEY')
    if not api_key:
        # Mock fallback
        return {
            "profile_summary": f"{personal_info.get('full_name','Student')} is a {personal_info.get('class_grade','')} student at {personal_info.get('school_name','')}. Note: This is a template response — set a Gemini API key for personalized analysis.",
            "pathways": [
                {"title": "Pathway 1 (70% Fit)", "why": "Based on selected interests.", "options": ["Option A", "Option B", "Option C"]},
                {"title": "Pathway 2 (65% Fit)", "why": "Based on aptitude scores.", "options": ["Option A", "Option B", "Option C"]},
                {"title": "Pathway 3 (60% Fit)", "why": "Based on personality traits.", "options": ["Option A", "Option B", "Option C"]}
            ],
            "roadmap": [
                {"year": 1, "focus": "Foundation", "milestones": ["Step 1", "Step 2", "Step 3"]},
                {"year": 2, "focus": "Growth", "milestones": ["Step 1", "Step 2", "Step 3"]},
                {"year": 3, "focus": "Specialization", "milestones": ["Step 1", "Step 2", "Step 3"]},
                {"year": 4, "focus": "Experience", "milestones": ["Step 1", "Step 2", "Step 3"]},
                {"year": 5, "focus": "Launch", "milestones": ["Step 1", "Step 2", "Step 3"]}
            ]
        }

    client = genai.Client(api_key=api_key)
    gemini_model = SiteConfig.get('gemini_model') or 'gemini-2.0-flash'

    prompt = f"""You are a highly experienced Senior Professional Psychologist and Career Counselor with 25+ years of practice in India, specializing in adolescent development and career guidance.

=== ABSOLUTE RULES ===

RULE 1 — HYPER-PERSONALIZATION IS MANDATORY:
- Address the student by their FIRST NAME directly in the summary.
- Quote their specific ratings and answers back to them.
- Spot contradictions and name them gently.

RULE 2 — AGE-APPROPRIATE GUIDANCE:
The student's current Class/Grade is: "{personal_info.get('class_grade','')}"
Calibrate your ENTIRE response to their exact class/stage.

RULE 3 — NORTH EAST INDIA + PAN-INDIA CONTEXT:
Suggest local NE institutions and top Indian institutions where appropriate.

RULE 4 — BREVITY IS POWER:
- Profile summary: MAX 4 sentences.
- Pathway "why": MAX 1-2 sentences.

RULE 5 — COLLEGE NAMES IN THE ROADMAP ARE MANDATORY:
In the 5-year roadmap milestones, you MUST name at least 2-3 specific, real colleges or universities that are directly relevant to the student's top career pathway. Include a mix of:
- North East India institutions (e.g. NIT Silchar, Assam University, Manipur University, NIT Manipur, RGIIM Shillong, Cotton University, Gauhati University, NEHU Shillong, Tezpur University, AIIMS Guwahati, NIPER Guwahati, ICAR Research Centres in NE India, DM College Imphal, Manipur Institute of Technology)
- Top national institutions (e.g. IITs, IIMs, AIIMS Delhi, NIFT, NID Ahmedabad, Film & Television Institute of India, St. Xavier's College, Delhi University, Christ University Bangalore, Symbiosis Pune, Manipal University)
Name them naturally inside the milestone text, for example: "Research admission requirements for NIT Silchar and Tezpur University for your chosen engineering stream."

=== STUDENT DATA ===

{assessment_summary}

=== OUTPUT FORMAT (JSON ONLY) ===

{{
  "profile_summary": "4 sentences MAX. Address by name. Quote their data.",
  "pathways": [
    {{"title": "Pathway Name (XX% Fit)", "why": "1-2 sentences.", "options": ["Action 1", "Action 2", "Action 3"]}}
  ],
  "roadmap": [
    {{"year": 1, "focus": "Theme", "milestones": ["Action 1", "Action 2", "Action 3"]}},
    {{"year": 2, "focus": "...", "milestones": ["...", "...", "..."]}},
    {{"year": 3, "focus": "...", "milestones": ["...", "...", "..."]}},
    {{"year": 4, "focus": "...", "milestones": ["Prepare for entrance exams for [specific college names relevant to the pathway]", "...", "..."]}},
    {{"year": 5, "focus": "...", "milestones": ["Apply to [specific college names] for [relevant course]", "...", "..."]}}
  ]
}}

3 pathways with XX% Fit, 3 options each. 3 milestones per year for 5 years. College names MUST appear in at least 2 roadmap years."""

    try:
        response = client.models.generate_content(
            model=gemini_model,
            contents=prompt
        )
        text = response.text.strip()
        # Strip markdown code fences if present
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
            text = text.strip()
        # Also strip trailing ```
        if text.endswith('```'):
            text = text[:-3].strip()
        return json.loads(text)
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"AI Generation error: {e}", exc_info=True)
        str_e = str(e)
        if '503' in str_e or 'UNAVAILABLE' in str_e or 'high demand' in str_e.lower():
            error_msg = f"Gemini API ({gemini_model}) is temporarily experiencing high demand."
            action_msg = "This is a temporary issue on Google's end. Please wait and try again or select a different model."
        else:
            error_msg = "AI analysis failed. Please check your API key and model selection."
            action_msg = "API error occurred. Check the Gemini AI settings page."
        
        return {
            "profile_summary": f"{personal_info.get('full_name','Student')} — {error_msg}",
            "pathways": [
                {"title": "Retry Required", "why": action_msg, "options": ["Try re-analyzing again later", "Check model selection", "Verify API key is correct"]}
            ],
            "roadmap": [
                {"year": i, "focus": "Pending", "milestones": ["Re-analyze when API is available", "Select a less busy model", "Ensure quota not exceeded"]} for i in range(1, 6)
            ]
        }


# ══════════════════════════════════════════
#  SKILLNEST ADMIN ROUTES
# ══════════════════════════════════════════

@employee_bp.route('/skillnest')
def skillnest_page():
    admissions = SkillNestAdmission.query.order_by(SkillNestAdmission.created_at.desc()).all()
    admission_fee = SiteConfig.get('skillnest_fee')
    total_seats_raw = SiteConfig.get('skillnest_total_seats')
    show_seats = SiteConfig.get('skillnest_show_seats', '0')
    admission_closed = SiteConfig.get('skillnest_admission_closed', '0')
    total_seats = int(total_seats_raw) if total_seats_raw else None
    seats_taken = SkillNestAdmission.query.filter(
        SkillNestAdmission.status == 'approved'
    ).count() if total_seats else 0
    seats_left = max(0, total_seats - seats_taken) if total_seats else None
    return render_template('employee/skillnest_admin.html',
                           admissions=admissions,
                           admission_fee=admission_fee,
                           total_seats=total_seats,
                           show_seats=show_seats,
                           admission_closed=admission_closed,
                           seats_taken=seats_taken,
                           seats_left=seats_left,
                           active_page='skillnest')

@employee_bp.route('/skillnest/settings')
def skillnest_settings_page():
    """SkillNest settings & configuration page."""
    admission_fee = SiteConfig.get('skillnest_fee')
    total_seats_raw = SiteConfig.get('skillnest_total_seats')
    show_seats = SiteConfig.get('skillnest_show_seats', '0')
    admission_closed = SiteConfig.get('skillnest_admission_closed', '0')
    total_seats = int(total_seats_raw) if total_seats_raw else None
    seats_taken = SkillNestAdmission.query.filter(
        SkillNestAdmission.status == 'approved'
    ).count() if total_seats else 0
    seats_left = max(0, total_seats - seats_taken) if total_seats else None
    admission_reg_fee = SiteConfig.get('skillnest_admission_reg_fee')
    show_monthly_fee = SiteConfig.get('skillnest_show_monthly_fee', '1')
    return render_template('employee/skillnest_settings.html',
                           admission_fee=admission_fee,
                           admission_reg_fee=admission_reg_fee,
                           show_monthly_fee=show_monthly_fee,
                           total_seats=total_seats,
                           show_seats=show_seats,
                           admission_closed=admission_closed,
                           seats_taken=seats_taken,
                           seats_left=seats_left,
                           active_page='skillnest')

@employee_bp.route('/skillnest/add-admission')
def skillnest_add_admission_page():
    """SkillNest add manual admission page."""
    return render_template('employee/skillnest_add.html',
                           active_page='skillnest')

@employee_bp.route('/skillnest/records')
def skillnest_records_page():
    """SkillNest admission records page."""
    admissions = SkillNestAdmission.query.order_by(SkillNestAdmission.created_at.desc()).all()
    admission_fee = SiteConfig.get('skillnest_fee')
    total_seats_raw = SiteConfig.get('skillnest_total_seats')
    total_seats = int(total_seats_raw) if total_seats_raw else None
    seats_taken = SkillNestAdmission.query.filter(
        SkillNestAdmission.status == 'approved'
    ).count() if total_seats else 0
    seats_left = max(0, total_seats - seats_taken) if total_seats else None
    return render_template('employee/skillnest_records.html',
                           admissions=admissions,
                           admission_fee=admission_fee,
                           total_seats=total_seats,
                           seats_taken=seats_taken,
                           seats_left=seats_left,
                           active_page='skillnest')

@employee_bp.route('/skillnest/set-settings', methods=['POST'])
def skillnest_set_settings():
    """Save fee, total seats, and show_seats toggle."""
    # Fee
    fee = request.form.get('fee', '').strip()
    if fee:
        try:
            fee_val = int(fee)
            if fee_val < 0:
                raise ValueError
            SiteConfig.set('skillnest_fee', str(fee_val))
        except (ValueError, TypeError):
            flash('Invalid fee amount. Please enter a valid number.', 'error')
            return redirect(url_for('employee.skillnest_settings_page'))
    else:
        SiteConfig.set('skillnest_fee', None)

    # Total seats
    seats = request.form.get('total_seats', '').strip()
    if seats:
        try:
            seats_val = int(seats)
            if seats_val < 0:
                raise ValueError
            SiteConfig.set('skillnest_total_seats', str(seats_val))
        except (ValueError, TypeError):
            flash('Invalid seat count. Please enter a valid number.', 'error')
            return redirect(url_for('employee.skillnest_settings_page'))
    else:
        SiteConfig.set('skillnest_total_seats', None)

    # Admission (one-time) fee
    admission_reg_fee = request.form.get('admission_reg_fee', '').strip()
    if admission_reg_fee:
        try:
            arv = int(admission_reg_fee)
            if arv < 0:
                raise ValueError
            SiteConfig.set('skillnest_admission_reg_fee', str(arv))
        except (ValueError, TypeError):
            flash('Invalid admission fee amount.', 'error')
            return redirect(url_for('employee.skillnest_settings_page'))
    else:
        SiteConfig.set('skillnest_admission_reg_fee', None)

    # Show monthly fee toggle
    show_monthly_fee = '1' if request.form.get('show_monthly_fee') else '0'
    SiteConfig.set('skillnest_show_monthly_fee', show_monthly_fee)

    # Show seats toggle
    show_seats = '1' if request.form.get('show_seats') else '0'
    SiteConfig.set('skillnest_show_seats', show_seats)

    # Admission closed toggle
    admission_closed = '1' if request.form.get('admission_closed') else '0'
    SiteConfig.set('skillnest_admission_closed', admission_closed)

    flash('SkillNest settings updated successfully.', 'success')
    return redirect(url_for('employee.skillnest_settings_page'))

@employee_bp.route('/skillnest/add-manual', methods=['POST'])
def skillnest_add_manual():
    """Admin manually registers a walk-in admission."""
    child_name    = request.form.get('child_name', '').strip()
    child_age     = request.form.get('child_age', '').strip()
    class_grade   = request.form.get('class_grade', '').strip()
    school_name   = request.form.get('school_name', '').strip()
    gender        = request.form.get('gender', '').strip()

    # Build DOB string from day/month/year selects
    dob_day   = request.form.get('dob_day', '').strip()
    dob_month = request.form.get('dob_month', '').strip()
    dob_year  = request.form.get('dob_year', '').strip()
    dob = f"{dob_day}/{dob_month}/{dob_year}" if dob_day and dob_month and dob_year else None

    # Section 02
    father_name   = request.form.get('father_name', '').strip()
    mother_name   = request.form.get('mother_name', '').strip()
    parent_name   = father_name or mother_name  # backward-compat field
    parent_mobile = request.form.get('parent_mobile', '').strip()
    alt_contact   = request.form.get('alt_contact', '').strip()
    parent_email  = request.form.get('parent_email', '').strip()
    address       = request.form.get('address', '').strip()

    # Section 03
    subjects_help    = request.form.get('subjects_help', '').strip()
    homework_support = request.form.get('homework_support', '').strip()
    child_strengths  = request.form.get('child_strengths', '').strip()
    areas_to_improve = request.form.get('areas_to_improve', '').strip()

    # Section 04
    child_behavior    = request.form.get('child_behavior', '').strip()
    medical_condition = request.form.get('medical_condition', '').strip()

    notes = request.form.get('notes', '').strip()

    if not child_name or not parent_mobile:
        flash('Child name and primary contact number are required.', 'error')
        return redirect(url_for('employee.skillnest_add_admission_page'))

    # Manual closure check (admin can still add with override flag)
    if SiteConfig.get('skillnest_admission_closed', '0') == '1' and not request.form.get('force_add'):
        flash('Admissions are currently closed. Tick "Force Add" to override.', 'error')
        return redirect(url_for('employee.skillnest_add_admission_page'))

    # Seat check
    total_seats_raw = SiteConfig.get('skillnest_total_seats')
    if total_seats_raw:
        total_seats = int(total_seats_raw)
        seats_taken = SkillNestAdmission.query.filter(
            SkillNestAdmission.status == 'approved'
        ).count()
        if seats_taken >= total_seats:
            flash('No seats available. All seats are filled.', 'error')
            return redirect(url_for('employee.skillnest_add_admission_page'))

    try:
        admission = SkillNestAdmission(
            child_name=child_name,
            dob=dob or None,
            child_age=int(child_age) if child_age and child_age.isdigit() else None,
            gender=gender or None,
            class_grade=class_grade or None,
            school_name=school_name or None,
            father_name=father_name or None,
            mother_name=mother_name or None,
            parent_name=parent_name or None,
            parent_mobile=parent_mobile,
            alt_contact=alt_contact or None,
            parent_email=parent_email or None,
            address=address or None,
            subjects_help=subjects_help or None,
            homework_support=homework_support or None,
            child_strengths=child_strengths or None,
            areas_to_improve=areas_to_improve or None,
            child_behavior=child_behavior or None,
            medical_condition=medical_condition or None,
            notes=notes or None,
            status='approved'
        )
        db.session.add(admission)
        db.session.commit()
        flash(f'✅ Manual admission for {child_name} added successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding admission: {str(e)}', 'error')
    return redirect(url_for('employee.skillnest_records_page'))

@employee_bp.route('/skillnest/<int:admission_id>/edit', methods=['GET', 'POST'])
def skillnest_edit(admission_id):
    a = SkillNestAdmission.query.get_or_404(admission_id)
    if request.method == 'POST':
        a.child_name = request.form.get('child_name', '').strip()
        dob_day = request.form.get('dob_day', '').strip()
        dob_month = request.form.get('dob_month', '').strip()
        dob_year = request.form.get('dob_year', '').strip()
        a.dob = f"{dob_day}/{dob_month}/{dob_year}" if dob_day and dob_month and dob_year else None
        
        c_age = request.form.get('child_age', '').strip()
        a.child_age = int(c_age) if c_age.isdigit() else None
        a.gender = request.form.get('gender', '').strip() or None
        a.class_grade = request.form.get('class_grade', '').strip() or None
        a.school_name = request.form.get('school_name', '').strip() or None
        a.father_name = request.form.get('father_name', '').strip() or None
        a.mother_name = request.form.get('mother_name', '').strip() or None
        a.parent_mobile = request.form.get('parent_mobile', '').strip()
        a.alt_contact = request.form.get('alt_contact', '').strip() or None
        a.parent_email = request.form.get('parent_email', '').strip() or None
        a.address = request.form.get('address', '').strip() or None
        a.subjects_help = request.form.get('subjects_help', '').strip() or None
        a.homework_support = request.form.get('homework_support', '').strip() or None
        a.child_strengths = request.form.get('child_strengths', '').strip() or None
        a.areas_to_improve = request.form.get('areas_to_improve', '').strip() or None
        a.child_behavior = request.form.get('child_behavior', '').strip() or None
        a.medical_condition = request.form.get('medical_condition', '').strip() or None
        
        a.batch_assigned = request.form.get('batch_assigned', '').strip() or None
        a.preferred_timing = request.form.get('preferred_timing', '').strip() or None
        a.evening_snack = request.form.get('evening_snack', '').strip() or None
        a.fees_paid = request.form.get('fees_paid', '').strip() or None
        a.payment_status = request.form.get('payment_status', '').strip() or None
        a.notes = request.form.get('notes', '').strip() or None
        
        try:
            db.session.commit()
            flash(f"✅ Record for {a.child_name} updated successfully.", "success")
            return redirect(url_for('employee.skillnest_records_page'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating record: {str(e)}", "error")

    return render_template('employee/skillnest_edit.html', a=a, active_page='skillnest')

@employee_bp.route('/skillnest/<int:admission_id>/approve', methods=['POST'])
def skillnest_approve(admission_id):
    admission = SkillNestAdmission.query.get_or_404(admission_id)
    admission.status = 'approved'
    db.session.commit()
    flash(f'{admission.child_name} has been approved! ✓', 'success')
    return redirect(url_for('employee.skillnest_records_page'))

@employee_bp.route('/skillnest/<int:admission_id>/reject', methods=['POST'])
def skillnest_reject(admission_id):
    admission = SkillNestAdmission.query.get_or_404(admission_id)
    admission.status = 'rejected'
    db.session.commit()
    flash(f'{admission.child_name} has been rejected.', 'success')
    return redirect(url_for('employee.skillnest_records_page'))

@employee_bp.route('/skillnest/<int:admission_id>/mark-paid', methods=['POST'])
def skillnest_mark_paid(admission_id):
    admission = SkillNestAdmission.query.get_or_404(admission_id)
    admission.payment_status = 'Paid'
    db.session.commit()
    flash(f'Payment marked as Paid for {admission.child_name}.', 'success')
    return redirect(url_for('employee.skillnest_records_page'))

@employee_bp.route('/skillnest/<int:admission_id>/delete', methods=['POST'])
def skillnest_delete(admission_id):
    admission = SkillNestAdmission.query.get_or_404(admission_id)
    name = admission.child_name
    db.session.delete(admission)
    db.session.commit()
    flash(f'Admission record for {name} deleted.', 'success')
    return redirect(url_for('employee.skillnest_records_page'))


# ══════════════════════════════════════════
#  GALLERY ROUTE
# ══════════════════════════════════════════

@employee_bp.route('/gallery')
@perm('gallery_view')
def gallery():
    import os
    from app.routes.admin import PHOTO_SLOTS
    img_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'img')
    slots = {}
    for key, meta in PHOTO_SLOTS.items():
        filepath = os.path.join(img_dir, meta['filename'])
        mtime = None
        if os.path.exists(filepath):
            mtime = int(os.path.getmtime(filepath))
        slots[key] = {**meta, 'mtime': mtime}
    return render_template('employee/gallery.html', slots=slots, active_page='gallery')


@employee_bp.route('/gallery/upload', methods=['POST'])
@perm('gallery_view')
def gallery_upload():
    import os
    from app.routes.admin import PHOTO_SLOTS, _allowed_photo
    from werkzeug.utils import secure_filename

    photo_key = request.form.get('photo_key', '').strip()
    if photo_key not in PHOTO_SLOTS:
        flash('Invalid photo slot.', 'error')
        return redirect(url_for('employee.gallery'))

    file = request.files.get('photo')
    if not file or file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('employee.gallery'))

    if not _allowed_photo(file):
        flash('Invalid file. Please upload a real JPG, PNG, GIF, or WebP image.', 'error')
        return redirect(url_for('employee.gallery'))

    slot = PHOTO_SLOTS[photo_key]
    img_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'img')
    save_path = os.path.join(img_dir, secure_filename(slot['filename']))
    try:
        file.save(save_path)
        flash(f'✅ {slot["label"]} updated successfully! Changes are now live on the site.', 'success')
    except Exception as e:
        flash(f'Error saving photo: {str(e)}', 'error')

    return redirect(url_for('employee.gallery'))



# ══════════════════════════════════════════
#  CONTACT & SOCIAL ROUTE
# ══════════════════════════════════════════

@employee_bp.route('/contact-social', methods=['GET', 'POST'])
@perm('contact_social')
def contact_social():
    if request.method == 'POST':
        fields = {
            'contact_phone_primary':   request.form.get('phone_primary', '').strip(),
            'contact_phone_secondary': request.form.get('phone_secondary', '').strip(),
            'location_address':        request.form.get('location_address', '').strip(),
            'location_map_url':        request.form.get('location_map_url', '').strip(),
            'social_facebook':         request.form.get('social_facebook', '').strip(),
            'social_instagram':        request.form.get('social_instagram', '').strip(),
            'social_youtube':          request.form.get('social_youtube', '').strip(),
            'social_linkedin':         request.form.get('social_linkedin', '').strip(),
        }
        for key, value in fields.items():
            SiteConfig.set(key, value if value else None)
        flash('Contact & Social settings saved.', 'success')
        return redirect(url_for('employee.contact_social'))

    class Config:
        pass
    config = Config()
    config.phone_primary    = SiteConfig.get('contact_phone_primary', '')
    config.phone_secondary  = SiteConfig.get('contact_phone_secondary', '')
    config.location_address = SiteConfig.get('location_address', '')
    config.location_map_url = SiteConfig.get('location_map_url', '')
    config.social_facebook  = SiteConfig.get('social_facebook', '')
    config.social_instagram = SiteConfig.get('social_instagram', '')
    config.social_youtube   = SiteConfig.get('social_youtube', '')
    config.social_linkedin  = SiteConfig.get('social_linkedin', '')
    return render_template('employee/contact_social.html', config=config, active_page='contact_social')


# ══════════════════════════════════════════
#  ADDITIONAL ASSESSMENT ROUTES
# ══════════════════════════════════════════

@employee_bp.route('/assessments/manual', methods=['GET', 'POST'])
@perm('assessments_view')
def manual_assessment():
    import json as _json
    if request.method == 'POST':
        personal_info = {
            'full_name':      request.form.get('full_name', '').strip(),
            'class_grade':    request.form.get('class_grade', '').strip(),
            'school_name':    request.form.get('school_name', '').strip(),
            'contact_number': request.form.get('contact_number', '').strip(),
            'email':          request.form.get('email', '').strip(),
        }
        interests = {
            'activities':  request.form.getlist('activities'),
            'subjects':    request.form.getlist('subjects'),
            'professions': request.form.getlist('professions'),
        }
        aptitude = {
            'logical':   request.form.get('apt_logical',   '3'),
            'science':   request.form.get('apt_science',   '3'),
            'writing':   request.form.get('apt_writing',   '3'),
            'computers': request.form.get('apt_computers', '3'),
            'design':    request.form.get('apt_design',    '3'),
            'speaking':  request.form.get('apt_speaking',  '3'),
            'planning':  request.form.get('apt_planning',  '3'),
            'helping':   request.form.get('apt_helping',   '3'),
            'tech':      request.form.get('apt_tech',      '3'),
        }
        personality = request.form.getlist('personality')
        career_vision = {
            'current_careers': request.form.get('vision_careers', '').strip(),
            'five_year_goals': request.form.get('vision_goals',   '').strip(),
            'ideal_life':      request.form.get('vision_life',    '').strip(),
        }
        run_ai = request.form.get('action') == 'analyze'
        ai_data = None
        status = 'ai_done' if run_ai else 'completed'
        if run_ai:
            try:
                ai_data = _run_ai_analysis(personal_info, interests, aptitude, personality, career_vision)
            except Exception as e:
                flash(f'AI analysis failed: {str(e)[:120]}. Data saved without AI report.', 'error')
                status = 'completed'
        try:
            assessment = StudentAssessment(
                client_username='employee_manual',
                personal_info=personal_info,
                interests=interests,
                aptitude=aptitude,
                personality=personality,
                career_vision=_json.dumps(career_vision),
                ai_response=ai_data,
                status=status,
            )
            db.session.add(assessment)
            db.session.commit()
            name = personal_info['full_name'] or 'Student'
            if run_ai and ai_data:
                flash(f'✅ Assessment for {name} saved with AI analysis!', 'success')
            else:
                flash(f'✅ Assessment for {name} saved. You can run AI analysis later from the list.', 'success')
            return redirect(url_for('employee.assessments_page'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving assessment: {str(e)}', 'error')
    return render_template('employee/manual_assessment.html', active_page='assessments')


@employee_bp.route('/assessments/view')
@perm('assessments_view')
def assessments_view():
    assessments = StudentAssessment.query.order_by(StudentAssessment.created_at.desc()).all()
    return render_template('employee/assessments_view.html', assessments=assessments, active_page='assessments')


@employee_bp.route('/assessments/create-client', methods=['GET', 'POST'])
@perm('assessments_create_client')
def assessments_create_client():
    if request.method == 'POST':
        client_name = request.form.get('name', '').strip()
        chars = string.ascii_letters + string.digits
        while True:
            temp_username = 'student_' + ''.join(random.choice(string.digits) for _ in range(5))
            if not Client.query.filter_by(username=temp_username).first():
                break
        temp_password = ''.join(random.choice(chars) for _ in range(10))
        hashed_temp = bcrypt.generate_password_hash(temp_password).decode('utf-8')
        new_client = Client(
            username=temp_username,
            password_hash=hashed_temp,
            display_name=client_name or None,
            temp_password_hash=temp_password
        )
        try:
            db.session.add(new_client)
            db.session.commit()
            label = f' ({client_name})' if client_name else ''
            flash(f'Credentials Generated{label}! Username: {temp_username} | Password: {temp_password}', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error generating client: {str(e)}', 'error')
        return redirect(url_for('employee.assessments_create_client'))
    clients = Client.query.order_by(Client.created_at.desc()).all()
    return render_template('employee/assessments_create_client.html', clients=clients, active_page='assessments')
