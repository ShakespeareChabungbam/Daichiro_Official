from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from app.models import Appointment, SiteConfig, SkillNestAdmission
from app.extensions import db
from datetime import datetime
import os

main_bp = Blueprint('main', __name__)

@main_bp.before_request
def block_admin():
    if 'admin_id' in session:
        return redirect(url_for('admin.dashboard'))

@main_bp.route('/')
def index():
    # Cache-busting: pass image mtimes so updated photos show immediately
    img_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'img')
    def _mtime(fname):
        try:
            return int(os.path.getmtime(os.path.join(img_dir, fname)))
        except OSError:
            return 1
    skillnest_seats = SiteConfig.get('skillnest_total_seats', '10')
    # Priority: offer_price (discounted) > counselling_fee (original) > 399
    offer_price = SiteConfig.get('offer_price')
    counselling_fee = SiteConfig.get('counselling_fee')
    session_price = offer_price or counselling_fee or '399'
    return render_template('index.html',
                           img_v1=_mtime('1.jpg'),
                           img_v2=_mtime('2.jpg'),
                           img_vd=_mtime('DirectorPhoto.jpg'),
                           skillnest_seats=skillnest_seats,
                           offer_price=session_price)

@main_bp.route('/about')
def about():
    return render_template('about.html')

@main_bp.route('/sunday-programs')
def sunday_programs():
    contact_phone = SiteConfig.get('contact_phone_primary') or '9366862651'
    contact_location = SiteConfig.get('location_address') or 'Old Lambulane, Imphal'
    return render_template('sunday_programs.html', contact_phone=contact_phone, contact_location=contact_location)

@main_bp.route('/skillnest')
def skillnest():
    skillnest_seats = SiteConfig.get('skillnest_total_seats', '10')
    return render_template('skillnest.html', skillnest_seats=skillnest_seats)

@main_bp.route('/skillnest/apply', methods=['GET'])
def skillnest_apply_page():
    admission_fee = SiteConfig.get('skillnest_fee')
    admission_reg_fee = SiteConfig.get('skillnest_admission_reg_fee')
    show_monthly_fee = SiteConfig.get('skillnest_show_monthly_fee', '1')  # default visible
    total_seats_raw = SiteConfig.get('skillnest_total_seats')
    show_seats = SiteConfig.get('skillnest_show_seats', '0')
    admission_closed = SiteConfig.get('skillnest_admission_closed', '0') == '1'
    total_seats = int(total_seats_raw) if total_seats_raw else None
    seats_taken = SkillNestAdmission.query.filter(
        SkillNestAdmission.status == 'approved'
    ).count() if total_seats else 0
    seats_left = max(0, total_seats - seats_taken) if total_seats else None
    seats_full = (seats_left == 0) if total_seats else False
    return render_template('skillnest_apply.html',
                           admission_fee=admission_fee,
                           admission_reg_fee=admission_reg_fee,
                           show_monthly_fee=show_monthly_fee,
                           total_seats=total_seats,
                           show_seats=show_seats,
                           seats_left=seats_left,
                           seats_full=seats_full,
                           admission_closed=admission_closed)

@main_bp.route('/skillnest/apply', methods=['POST'])
def skillnest_apply():
    child_name    = request.form.get('child_name', '').strip()
    dob           = request.form.get('dob', '').strip()
    child_age     = request.form.get('child_age', '').strip()
    gender        = request.form.get('gender', '').strip()
    school_name   = request.form.get('school_name', '').strip()
    class_grade   = request.form.get('class_grade', '').strip()
    father_name   = request.form.get('father_name', '').strip()
    mother_name   = request.form.get('mother_name', '').strip()
    parent_mobile = request.form.get('parent_mobile', '').strip()
    alt_contact   = request.form.get('alt_contact', '').strip()
    parent_email  = request.form.get('parent_email', '').strip()
    address       = request.form.get('address', '').strip()
    subjects_help     = request.form.get('subjects_help', '').strip()
    homework_support  = request.form.get('homework_support', '').strip()
    child_strengths   = request.form.get('child_strengths', '').strip()
    areas_to_improve  = request.form.get('areas_to_improve', '').strip()
    child_behavior    = request.form.get('child_behavior', '').strip()
    medical_condition = request.form.get('medical_condition', '').strip()
    preferred_timing  = request.form.get('preferred_timing', '').strip()
    evening_snack     = request.form.get('evening_snack', '').strip()

    if not child_name or not parent_mobile:
        flash('Child name and contact number are required.', 'error')
        return redirect(url_for('main.skillnest_apply_page'))

    # Manual closure check
    if SiteConfig.get('skillnest_admission_closed', '0') == '1':
        flash('Admissions are currently closed. Please contact us for more information.', 'error')
        return redirect(url_for('main.skillnest_apply_page'))

    # Seat availability check
    total_seats_raw = SiteConfig.get('skillnest_total_seats')
    if total_seats_raw:
        total_seats = int(total_seats_raw)
        seats_taken = SkillNestAdmission.query.filter(
            SkillNestAdmission.status == 'approved'
        ).count()
        if seats_taken >= total_seats:
            flash('Sorry, all seats for SkillNest are currently full. Please contact us for more information.', 'error')
            return redirect(url_for('main.skillnest_apply_page'))

    try:
        admission = SkillNestAdmission(
            child_name=child_name,
            dob=dob or None,
            child_age=int(child_age) if child_age else None,
            gender=gender or None,
            school_name=school_name or None,
            class_grade=class_grade or None,
            father_name=father_name or None,
            mother_name=mother_name or None,
            parent_name=father_name or mother_name or None,
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
            preferred_timing=preferred_timing or None,
            evening_snack=evening_snack or None,
            payment_status='Paid',
        )
        db.session.add(admission)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('Error submitting application. Please try again.', 'error')
        return redirect(url_for('main.skillnest_apply_page'))

    return redirect(url_for('main.skillnest_applied', child_name=child_name))


@main_bp.route('/skillnest/applied')
def skillnest_applied():
    child_name = request.args.get('child_name', 'your child')
    return render_template('skillnest_applied.html', child_name=child_name)

@main_bp.route('/book', methods=['GET'])
def book_page():
    counselling_fee = SiteConfig.get('counselling_fee')
    offer_price = SiteConfig.get('offer_price')
    package_price = SiteConfig.get('package_price')
    package_offer_price = SiteConfig.get('package_offer_price')
    offer_label = SiteConfig.get('offer_label')
    offer_expiry = SiteConfig.get('offer_expiry')
    booking_closed = SiteConfig.get('booking_closed', '0')
    booking_message = SiteConfig.get('booking_message')
    booking_reopen_date = SiteConfig.get('booking_reopen_date')
    return render_template('book.html',
        counselling_fee=counselling_fee,
        offer_price=offer_price,
        package_price=package_price,
        package_offer_price=package_offer_price,
        offer_label=offer_label,
        offer_expiry=offer_expiry,
        booking_closed=booking_closed,
        booking_message=booking_message,
        booking_reopen_date=booking_reopen_date
    )

@main_bp.route('/book/form', methods=['GET'])
def book_form_page():
    pkg_id = request.args.get('package', 'single')
    counselling_fee = SiteConfig.get('counselling_fee')

    packages = {
        'single': {
            'label': 'Single Session',
            'price': '₹{} / session'.format(SiteConfig.get('offer_price') or SiteConfig.get('counselling_fee') or '399'),
            'fee':   SiteConfig.get('offer_price') or SiteConfig.get('counselling_fee') or '399',
            'features': [
                'Choose ONE session type per booking',
                'Student Counselling — for the child/student',
                'Parent Counselling — for parents only',
                'Parent–Child Joint Session — both together',
                '45 – 60 minutes · One-time',
            ]
        },
        'recommended': {
            'label': 'Complete Package',
            'price': '₹{} / package'.format(SiteConfig.get('package_offer_price') or SiteConfig.get('package_price') or '999'),
            'fee':   SiteConfig.get('package_offer_price') or SiteConfig.get('package_price') or '999',
            'features': [
                'All 3 session types included',
                'Student Counselling session',
                'Parent Counselling session',
                'Parent–Child Joint session',
                'Structured follow-up plan · Best for families',
            ]
        }
    }

    pkg = packages.get(pkg_id, packages['single'])
    return render_template(
        'book_form.html',
        pkg_id=pkg_id,
        pkg_label=pkg['label'],
        pkg_price=pkg['price'],
        pkg_features=pkg['features'],
        counselling_fee=pkg['fee']
    )

@main_bp.route('/book', methods=['POST'])
def book_counseling():
    import re
    # Server-side guard — cannot be bypassed by direct POST
    if SiteConfig.get('booking_closed', '0') == '1':
        flash('Bookings are currently closed. Please check back later.', 'error')
        return redirect(url_for('main.book_page'))
    name = request.form.get('name', '').strip()
    address = request.form.get('address', '').strip()
    mobile = request.form.get('mobile', '').strip()
    whatsapp = request.form.get('whatsapp', '').strip()
    email = request.form.get('email', '').strip()
    package = request.form.get('package', '').strip()

    def normalise_phone(val):
        digits = re.sub(r'\D', '', val)
        if digits.startswith('91') and len(digits) == 12:
            digits = digits[2:]
        elif digits.startswith('0') and len(digits) == 11:
            digits = digits[1:]
        return digits

    if not name or not mobile:
        flash('Name and mobile number are required.', 'error')
        return redirect(url_for('main.book_page'))

    mobile = normalise_phone(mobile)
    if not re.match(r'^[5-9]\d{9}$', mobile):
        flash('Please enter a valid 10-digit Indian mobile number (starts with 5–9).', 'error')
        return redirect(url_for('main.book_page'))

    if whatsapp:
        whatsapp = normalise_phone(whatsapp)
        if not re.match(r'^[5-9]\d{9}$', whatsapp):
            flash('WhatsApp number must be a valid 10-digit Indian number (starts with 5–9).', 'error')
            return redirect(url_for('main.book_page'))

    try:
        # ── Lock price at booking time (never changes with future price edits) ──
        is_pkg = package and any(k in package.lower() for k in ('recommended', 'complete', 'package'))
        if is_pkg:
            booked_offer = SiteConfig.get('package_offer_price') or SiteConfig.get('package_price') or '999'
            booked_orig  = SiteConfig.get('package_price') or '999'
        else:
            booked_offer = SiteConfig.get('offer_price') or SiteConfig.get('counselling_fee') or '399'
            booked_orig  = SiteConfig.get('counselling_fee') or '399'

        new_appointment = Appointment(
            name=name,
            address=address,
            mobile=mobile,
            whatsapp=whatsapp or None,
            email=email,
            contact=mobile,  # backwards compat
            payment_status='Pending',
            package=package or None,
            fees_paid='{offer}|{orig}'.format(offer=booked_offer, orig=booked_orig)
        )
        db.session.add(new_appointment)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash('Error booking appointment. Please try again.', 'error')
        return redirect(url_for('main.book_page'))
        
    return redirect(url_for('main.booking_confirmed', name=name, date=''))

@main_bp.route('/booking-confirmed')
def booking_confirmed():
    name = request.args.get('name', 'Guest')
    date = request.args.get('date', '')
    return render_template('booking_confirmed.html', name=name, date=date)


# ══════════════════════════════════════════════════════
#  SEO — SITEMAP & ROBOTS
# ══════════════════════════════════════════════════════

@main_bp.route('/sitemap.xml')
def sitemap():
    from flask import make_response
    pages = [
        ('https://daichiro.in/',                '1.0', 'weekly'),
        ('https://daichiro.in/about',           '0.8', 'monthly'),
        ('https://daichiro.in/skillnest',       '0.9', 'weekly'),
        ('https://daichiro.in/skillnest/apply', '0.8', 'weekly'),
        ('https://daichiro.in/book',            '0.9', 'weekly'),
    ]
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for loc, priority, changefreq in pages:
        xml.append('  <url>')
        xml.append(f'    <loc>{loc}</loc>')
        xml.append(f'    <priority>{priority}</priority>')
        xml.append(f'    <changefreq>{changefreq}</changefreq>')
        xml.append(f'    <lastmod>{datetime.utcnow().strftime("%Y-%m-%d")}</lastmod>')
        xml.append('  </url>')
    xml.append('</urlset>')
    response = make_response('\n'.join(xml))
    response.headers['Content-Type'] = 'application/xml'
    return response


@main_bp.route('/robots.txt')
def robots():
    from flask import make_response
    content = """User-agent: *
Allow: /
Disallow: /admin/
Disallow: /employee/
Disallow: /client/

Sitemap: https://daichiro.in/sitemap.xml
"""
    response = make_response(content)
    response.headers['Content-Type'] = 'text/plain'
    return response
