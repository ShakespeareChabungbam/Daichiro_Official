"""
DeveloperX — Private portal for site owner to edit the "Powered by ARTORYX" credit.
Route: /developerX  (not linked from any public/admin/employee page)
"""
import os
from functools import wraps
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash)
from werkzeug.security import check_password_hash, generate_password_hash
from app.models import SiteConfig
from app.utils.email_utils import generate_reset_token, verify_reset_token, send_reset_email
from app.extensions import limiter

dev_bp = Blueprint('developer', __name__, url_prefix='/developerX')

# ── Constants ─────────────────────────────────────────────────────────────────
# Loaded from environment — never hardcoded in source
_DEV_EMAIL_ENV    = os.environ.get('DEV_EMAIL', '')
DEV_SESSION_KEY   = 'developerX_auth'
RESET_SALT        = 'developerX-reset'


def _dev_email():
    """Return developer email from env or SiteConfig fallback."""
    return _DEV_EMAIL_ENV or SiteConfig.get('dev_email', '')


# ── Auth guard ────────────────────────────────────────────────────────────────
def dev_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get(DEV_SESSION_KEY):
            return redirect(url_for('developer.login'))
        return f(*args, **kwargs)
    return decorated


def _get_or_init_hash():
    """Return stored password hash; bootstrap only if env INITIAL_DEV_PASSWORD set."""
    stored = SiteConfig.get('dev_password_hash')
    if not stored:
        initial = os.environ.get('INITIAL_DEV_PASSWORD', '')
        if initial:
            stored = generate_password_hash(initial, method='pbkdf2:sha256:600000')
            SiteConfig.set('dev_password_hash', stored)
    return stored


# ── Login ─────────────────────────────────────────────────────────────────────
@dev_bp.route('/', methods=['GET', 'POST'])
@limiter.limit('5 per minute', methods=['POST'])
def login():
    if session.get(DEV_SESSION_KEY):
        return redirect(url_for('developer.dashboard'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        pw_hash  = _get_or_init_hash()

        if pw_hash and email == _dev_email().lower() and check_password_hash(pw_hash, password):
            session[DEV_SESSION_KEY] = True
            return redirect(url_for('developer.dashboard'))

        flash('Invalid credentials.', 'error')

    return render_template('developer/login.html')


# ── Dashboard ─────────────────────────────────────────────────────────────────
@dev_bp.route('/dashboard', methods=['GET', 'POST'])
@dev_required
def dashboard():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'credit':
            text = request.form.get('credit_text', '').strip()
            link = request.form.get('credit_link', '').strip()
            SiteConfig.set('developer_credit_text', text or 'ARTORYX')
            SiteConfig.set('developer_credit_link', link)
            flash('Credit updated successfully.', 'success')

        elif action == 'password':
            current  = request.form.get('current_password', '').strip()
            new_pw   = request.form.get('new_password', '').strip()
            confirm  = request.form.get('confirm_password', '').strip()
            pw_hash  = _get_or_init_hash()

            if not pw_hash or not check_password_hash(pw_hash, current):
                flash('Current password is incorrect.', 'error')
            elif new_pw != confirm:
                flash('New passwords do not match.', 'error')
            elif len(new_pw) < 10:
                flash('Password must be at least 10 characters.', 'error')
            else:
                SiteConfig.set('dev_password_hash',
                               generate_password_hash(new_pw, method='pbkdf2:sha256:600000'))
                flash('Password changed successfully.', 'success')

        return redirect(url_for('developer.dashboard'))

    return render_template('developer/dashboard.html',
                           credit_text=SiteConfig.get('developer_credit_text') or 'ARTORYX',
                           credit_link=SiteConfig.get('developer_credit_link') or '')


# ── Logout ────────────────────────────────────────────────────────────────────
@dev_bp.route('/logout')
def logout():
    session.pop(DEV_SESSION_KEY, None)
    return redirect(url_for('developer.login'))


# ── Forgot password ───────────────────────────────────────────────────────────
@dev_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit('5 per minute', methods=['POST'])
def forgot_password():
    sent = False
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        dev_e = _dev_email().lower()
        if dev_e and email == dev_e:
            token     = generate_reset_token(dev_e, salt=RESET_SALT)
            reset_url = url_for('developer.reset_password', token=token, _external=True)
            send_reset_email(dev_e, reset_url, name='Developer')
        # Always show "sent" to avoid email enumeration
        sent = True

    return render_template('developer/forgot_password.html', sent=sent)


# ── Reset password ────────────────────────────────────────────────────────────
@dev_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit('5 per minute', methods=['POST'])
def reset_password(token):
    email = verify_reset_token(token, salt=RESET_SALT, max_age=3600)
    dev_e = _dev_email().lower()
    if not email or not dev_e or email.lower() != dev_e:
        flash('This reset link is invalid or has expired.', 'error')
        return redirect(url_for('developer.login'))

    if request.method == 'POST':
        new_pw  = request.form.get('password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()

        if new_pw != confirm:
            flash('Passwords do not match.', 'error')
        elif len(new_pw) < 10:
            flash('Password must be at least 10 characters.', 'error')
        else:
            SiteConfig.set('dev_password_hash',
                           generate_password_hash(new_pw, method='pbkdf2:sha256:600000'))
            flash('Password updated. Please log in.', 'success')
            return redirect(url_for('developer.login'))

    return render_template('developer/reset_password.html', token=token)
