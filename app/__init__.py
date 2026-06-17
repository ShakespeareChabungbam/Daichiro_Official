import os
from flask import Flask, render_template
from app.extensions import db, bcrypt, scheduler, csrf, limiter
from dotenv import load_dotenv

def create_app(config_module=None):
    load_dotenv()
    app = Flask(__name__)
    
    # Configuration
    secret = os.environ.get('SECRET_KEY')
    if not secret:
        raise RuntimeError('SECRET_KEY environment variable is required. Set it in .env')
    app.config['SECRET_KEY'] = secret
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://localhost/daichiro_db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,   # test connections before use — prevents stale SSL errors
        'pool_recycle': 300,     # recycle connections every 5 minutes
        'pool_size': 5,
        'max_overflow': 10,
    }

    # Session cookie security
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get("FLASK_DEBUG", "False").lower() not in ("true", "1", "t")  # require HTTPS unless debugging
    app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload
    
    # Scheduler Config — API disabled to prevent unauthenticated job management
    app.config['SCHEDULER_API_ENABLED'] = False
    
    if config_module:
        app.config.from_object(config_module)

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    scheduler.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    
    # Global Security Headers
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Frame-Options']           = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options']    = 'nosniff'
        response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains; preload'
        response.headers['X-XSS-Protection']          = '1; mode=block'
        response.headers['Referrer-Policy']           = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy']        = 'camera=(), microphone=(), geolocation=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://cdn.tailwindcss.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://cdn.tailwindcss.com; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        return response

    # Global Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        app.logger.error(f'Server Error: {e}')
        return render_template('500.html'), 500

    # CSRF token missing — session expired between page load and form submit
    from flask_wtf.csrf import CSRFError
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        from flask import flash, redirect, url_for, request
        flash('Your session has expired. Please log in again.', 'error')
        # Send employee back to employee login, admin back to admin login
        if request.path.startswith('/employee/'):
            return redirect(url_for('admin.login'))
        return redirect(url_for('admin.login'))
    
    # Import blueprints/routes
    from app.routes.main import main_bp
    from app.routes.admin import admin_bp
    from app.routes.client import client_bp
    from app.routes.employee import employee_bp
    from app.routes.developer import dev_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(client_bp, url_prefix='/client')
    app.register_blueprint(employee_bp, url_prefix='/employee')
    app.register_blueprint(dev_bp)

    # Global context: inject contact & social into every template
    @app.context_processor
    def inject_site_contact():
        from app.models import SiteConfig
        return {
            'site_phone_primary':    SiteConfig.get('contact_phone_primary'),
            'site_phone_secondary':  SiteConfig.get('contact_phone_secondary'),
            'site_facebook':         SiteConfig.get('social_facebook'),
            'site_instagram':        SiteConfig.get('social_instagram'),
            'site_youtube':          SiteConfig.get('social_youtube'),
            'site_linkedin':         SiteConfig.get('social_linkedin'),
            'site_location_address': SiteConfig.get('location_address'),
            'site_location_map_url': SiteConfig.get('location_map_url'),
            'dev_credit_text':       SiteConfig.get('developer_credit_text') or 'ARTORYX',
            'dev_credit_link':       SiteConfig.get('developer_credit_link') or '',
            'current_year':          __import__('datetime').datetime.now().year,
        }

    # ── IST datetime filter ──────────────────────────────────────────────────
    # All datetimes are stored as UTC naive. This filter adds +5:30 and formats
    # them as "28 Mar 2026, 04:09 AM" for display throughout the site.
    from datetime import timedelta
    @app.template_filter('to_ist')
    def to_ist(dt):
        if dt is None:
            return '—'
        ist = dt + timedelta(hours=5, minutes=30)
        return ist.strftime('%d %b %Y, %I:%M %p')

    # Setup Background Tasks
    from app.tasks import delete_old_clients, delete_old_assessments, delete_old_appointments

    # Run immediately on startup to clean up any stale data
    with app.app_context():
        delete_old_clients(app)

    # Check every 15 minutes for clients to expire (3-hour lifespan)
    @scheduler.task('interval', id='cleanup_clients_job', minutes=15)
    def run_cleanup():
        delete_old_clients(app)

    # Check once daily for assessments older than 3 months (90 days)
    @scheduler.task('interval', id='cleanup_assessments_job', hours=24)
    def run_assessment_cleanup():
        delete_old_assessments(app)

    # Check once daily for appointments older than 3 months (90 days)
    @scheduler.task('interval', id='cleanup_appointments_job', hours=24)
    def run_appointment_cleanup():
        delete_old_appointments(app)
    scheduler.start()

    return app
