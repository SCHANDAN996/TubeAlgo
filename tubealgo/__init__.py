# tubealgo/__init__.py

import os
from flask import Flask, url_for, session, g, render_template, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, timezone, timedelta
from celery import Celery, Task
from celery.schedules import crontab
import config
from sqlalchemy import text, inspect
from sqlalchemy.exc import OperationalError
import pytz
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_sse import sse

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

def limiter_key_func():
    """Return a unique identifier for rate limiting (user ID or IP address)."""
    if current_user and current_user.is_authenticated:
        return str(current_user.id)
    return get_remote_address()

# Initialize Flask-Limiter
limiter = Limiter(key_func=limiter_key_func, default_limits=["200 per day", "50 per hour"])

# Initialize Celery
celery = Celery(__name__)


def localize_datetime(utc_dt, fmt='%d %b %Y, %I:%M %p'):
    """Jinja filter to convert a UTC datetime object to a user's preferred timezone."""
    if not utc_dt:
        return ""

    user_tz_str = 'Asia/Kolkata' # Default timezone
    try:
        # Get user's timezone if logged in and set
        if current_user and current_user.is_authenticated and hasattr(current_user, 'timezone') and current_user.timezone:
            user_tz_str = current_user.timezone
        user_tz = pytz.timezone(user_tz_str)
    except pytz.UnknownTimeZoneError:
        # Fallback to default if user's timezone is invalid
        user_tz = pytz.timezone('Asia/Kolkata')

    # Ensure utc_dt is a datetime object
    if not isinstance(utc_dt, datetime):
        try:
            # Handle ISO format strings (potentially with 'Z')
            if isinstance(utc_dt, str):
                 utc_dt = utc_dt.replace('Z', '+00:00')
                 utc_dt = datetime.fromisoformat(utc_dt)
            # Handle other datetime-like objects if possible
            elif hasattr(utc_dt, 'isoformat'):
                 utc_dt_str = utc_dt.isoformat().replace('Z', '+00:00')
                 utc_dt = datetime.fromisoformat(utc_dt_str)
            else:
                 # If it's not a recognizable format, return as string
                 return str(utc_dt)
        except (ValueError, TypeError):
             # Log the error for debugging
             print(f"Could not parse datetime input: {utc_dt}")
             return str(utc_dt) # Fallback

    # Make timezone-aware if naive (assume UTC)
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=pytz.utc)

    # Convert to user's timezone
    try:
        local_dt = utc_dt.astimezone(user_tz)
        return local_dt.strftime(fmt)
    except Exception as e:
         # Log the localization error
         print(f"Error localizing datetime ({utc_dt}) to {user_tz_str}: {e}")
         # Fallback to UTC display if localization fails
         return utc_dt.strftime(fmt) + " UTC"


def create_app():
    """Flask application factory."""
    # Define paths relative to the application's root
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    static_folder_path = os.path.join(project_root, 'static')
    template_folder_path = os.path.join(project_root, 'tubealgo', 'templates')
    instance_folder_path = os.path.join(project_root, 'instance')

    # Initialize Flask app
    app = Flask(
        __name__.split('.')[0], # Use root package name
        instance_path=instance_folder_path,
        instance_relative_config=True, # Load config relative to instance folder
        static_folder=static_folder_path,
        template_folder=template_folder_path
    )

    # Load configuration from config.py and .env file
    app.config.from_object(config.Config)

    # Create instance folder if it doesn't exist
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass # Ignore error if folder already exists

    # Configure Redis URL for SSE
    app.config["REDIS_URL"] = app.config.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    app.register_blueprint(sse, url_prefix='/stream')

    # *** UPDATED: Configure Celery with connection retry ***
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
        broker_connection_retry_on_startup=True,
        task_ignore_result=True,
        broker_connection_retry=True,
        broker_connection_max_retries=10,
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
    )
    
    # Define Celery beat schedule for periodic tasks
    celery.conf.beat_schedule = {
        'take-daily-snapshots-every-day': {
            'task': 'tubealgo.jobs.take_daily_snapshots',
            'schedule': crontab(hour=0, minute=5, day_of_week='*'), # Run daily at 00:05 UTC
        },
        'check-for-new-videos-every-hour': {
            'task': 'tubealgo.jobs.check_for_new_videos',
            'schedule': crontab(minute=0, hour='*'), # Run at the start of every hour
        },
        'update-all-dashboards-every-4-hours': {
            'task': 'tubealgo.jobs.update_all_dashboards',
            'schedule': crontab(minute=15, hour='*/4'), # Run every 4 hours at xx:15
        },
         'take-video-snapshots-every-3-hours': {
            'task': 'tubealgo.jobs.take_video_snapshots',
            'schedule': crontab(minute=30, hour='*/3'), # Run every 3 hours at xx:30
        },
        'cleanup-old-snapshots-daily': {
            'task': 'tubealgo.jobs.cleanup_old_snapshots',
            'schedule': crontab(hour=1, minute=0, day_of_week='*'), # Run daily at 01:00 UTC
        },
    }

    # Configure Celery Task context to work within Flask app context
    class ContextTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    celery.Task = ContextTask
    app.celery = celery # Attach celery instance to app

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth_local.login' # Route to redirect unauthenticated users
    login_manager.login_message_category = "error" # Flash message category

    # Initialize Flask-Limiter
    limiter_storage_uri = app.config.get("REDIS_URL", "memory://") # Use Redis if available
    limiter.init_app(app)

    # --- Request Hooks ---
    @app.before_request
    def before_request_handler():
        """Update user's last_seen timestamp."""
        if current_user.is_authenticated:
            # Update only periodically (e.g., every 5 minutes) to reduce DB writes
            five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
            # Handle case where last_seen might be None initially
            last_seen_time = current_user.last_seen or datetime.utcnow() - timedelta(days=1)

            if last_seen_time < five_minutes_ago:
                current_user.last_seen = datetime.utcnow()
                try:
                    # Attempt to commit without adding, as user object is already managed
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    # Log error more quietly in production
                    app.logger.error(f"Error updating last_seen for user {current_user.id}: {e}")

    @app.after_request
    def add_security_headers(response):
        """Add common security headers to responses."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'" # Prevent clickjacking
        # Remove deprecated headers if set by default by the framework/server
        response.headers.pop('X-Frame-Options', None)
        response.headers.pop('X-XSS-Protection', None)
        # Prevent caching of dynamic HTML pages to avoid showing stale data
        if response.mimetype == 'text/html':
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    # --- Context Processors ---
    @app.context_processor
    def override_url_for():
        """Make url_for available in templates without needing explicit import."""
        return dict(url_for=url_for)

    @app.context_processor
    def inject_now_and_settings():
        """Inject current UTC time and get_setting function into templates."""
        from .models import get_setting # Local import to avoid circular dependency
        return {'now': datetime.utcnow, 'get_setting': get_setting}

    @app.context_processor
    def inject_csrf_token():
        """Make CSRF token generation available in templates."""
        return dict(csrf_token=generate_csrf)

    # --- Register Jinja Filters ---
    app.jinja_env.filters['relative_time'] = format_relative_time
    app.jinja_env.filters['localize'] = localize_datetime

    # --- Register Error Handlers ---
    @app.errorhandler(500)
    def internal_error(error):
        """Handle internal server errors (500)."""
        db.session.rollback() # Rollback potentially broken transactions
        app.logger.error(f"Internal Server Error: {error}", exc_info=True) # Log detailed error
        return render_template('errors/500.html'), 500

    @app.errorhandler(404)
    def not_found_error(error):
        """Handle page not found errors (404)."""
        return render_template('errors/404.html'), 404

    # --- Simplified Application context block for startup checks ---
    with app.app_context():
        try:
            print("Checking database connection...")
            db.session.execute(text('SELECT 1')) # Simple check
            print("Database connection seems OK.")

            # Initialize AI clients here as it relies on config loaded into app
            print("Initializing AI clients within app context...")
            from .services.ai_service import initialize_ai_clients
            initialize_ai_clients()

            # Seed plans only if the table exists (created by create_tables.py)
            seed_plans()

        except Exception as e:
            # Log a warning, but allow the app to continue starting
            print(f"WARNING: Could not verify DB connection or initialize services on startup: {e}")
            db.session.rollback()


    # --- Import and register Blueprints ---
    from .auth_local import auth_local_bp
    app.register_blueprint(auth_local_bp, url_prefix='/')

    from .auth_google import auth_google_bp
    app.register_blueprint(auth_google_bp, url_prefix='/')

    from .routes.core_routes import core_bp
    app.register_blueprint(core_bp, url_prefix='/')

    from .routes.dashboard_routes import dashboard_bp
    app.register_blueprint(dashboard_bp, url_prefix='/')

    from .routes.competitor_routes import competitor_bp
    app.register_blueprint(competitor_bp, url_prefix='/')

    from .routes.analysis_routes import analysis_bp
    app.register_blueprint(analysis_bp, url_prefix='/')

    from .routes.api_routes import api_bp
    app.register_blueprint(api_bp)

    from .routes.ai_api_routes import ai_api_bp
    app.register_blueprint(ai_api_bp)

    from .routes.tool_routes import tool_bp
    app.register_blueprint(tool_bp, url_prefix='/')

    from .routes.settings_routes import settings_bp
    app.register_blueprint(settings_bp, url_prefix='/')

    from .routes.payment_routes import payment_bp
    app.register_blueprint(payment_bp, url_prefix='/payment')

    from .routes.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    from .routes.video_manager_routes import video_manager_bp
    app.register_blueprint(video_manager_bp, url_prefix='/manage')

    from .routes.playlist_manager_routes import playlist_manager_bp
    app.register_blueprint(playlist_manager_bp, url_prefix='/manage')

    from .routes.ab_test_routes import ab_test_bp
    app.register_blueprint(ab_test_bp, url_prefix='/manage')

    from .routes.report_routes import report_bp
    app.register_blueprint(report_bp)

    from .routes.video_analytics_routes import video_analytics_bp
    app.register_blueprint(video_analytics_bp)

    from .routes.planner_routes import planner_bp
    app.register_blueprint(planner_bp)

    from .routes.goal_routes import goal_bp
    app.register_blueprint(goal_bp)

    from .routes.user_routes import user_bp
    app.register_blueprint(user_bp)

    # Exempt specific blueprints from CSRF protection if they handle external webhooks/APIs
    csrf.exempt(api_bp)
    csrf.exempt(ai_api_bp)
    csrf.exempt(payment_bp)

    # Import models at the end to ensure db is initialized and blueprints are registered
    from . import models

    # Return the configured app instance
    return app

# --- Helper Functions ---

def format_relative_time(dt_input):
    """Jinja filter to format datetime object or string into relative time (e.g., '5 minutes ago')."""
    if not dt_input: return ""
    dt_obj = None
    # Convert input to datetime object if it's a string
    if isinstance(dt_input, str):
        try: dt_obj = datetime.fromisoformat(dt_input.replace('Z', '+00:00'))
        except ValueError: return dt_input # Return original string if parsing fails
    elif isinstance(dt_input, datetime): dt_obj = dt_input
    else: return str(dt_input) # Return string representation if not datetime or string

    if not dt_obj: return str(dt_input) # Fallback

    # Ensure the datetime object is timezone-aware (assume UTC if naive)
    if dt_obj.tzinfo is None: dt_obj = dt_obj.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    diff = now - dt_obj
    seconds = diff.total_seconds()

    # Handle future dates
    if seconds < 0: return "in the future"
    # Provide human-readable relative time
    if seconds < 60: return "just now"
    minutes = seconds / 60
    if minutes < 60: return f"{int(minutes)} minute{'s' if int(minutes) > 1 else ''} ago"
    hours = minutes / 60
    if hours < 24: return f"{int(hours)} hour{'s' if int(hours) > 1 else ''} ago"
    days = hours / 24
    if days < 7: return f"{int(days)} day{'s' if int(days) > 1 else ''} ago"
    weeks = days / 7
    if weeks < 4.345: return f"{int(weeks)} week{'s' if int(weeks) > 1 else ''} ago"
    months = days / 30.437
    if months < 12: return f"{int(months)} month{'s' if int(months) > 1 else ''} ago"
    years = days / 365.25
    return f"{int(years)} year{'s' if int(years) > 1 else ''} ago"

def seed_plans():
    """Seeds the database with default subscription plans if table exists and is empty."""
    from .models import SubscriptionPlan
    from sqlalchemy import inspect
    try:
        inspector = inspect(db.engine)
        if inspector.has_table(SubscriptionPlan.__tablename__):
            if SubscriptionPlan.query.count() == 0:
                print("Seeding subscription plans...")
                free_plan = SubscriptionPlan(
                    plan_id='free', name='Free', price=0, competitors_limit=2,
                    keyword_searches_limit=5, ai_generations_limit=3, playlist_suggestions_limit=3, has_comment_reply=False
                )
                creator_plan = SubscriptionPlan(
                    plan_id='creator', name='Creator', price=39900, slashed_price=79900,
                    competitors_limit=10, keyword_searches_limit=50, ai_generations_limit=30,
                    has_discover_tools=True, has_ai_suggestions=True, playlist_suggestions_limit=10,
                    is_popular=True, has_comment_reply=False
                )
                pro_plan = SubscriptionPlan(
                    plan_id='pro', name='Pro', price=99900, slashed_price=199900,
                    competitors_limit=-1, keyword_searches_limit=-1, ai_generations_limit=-1,
                    has_discover_tools=True, has_ai_suggestions=True, playlist_suggestions_limit=-1,
                    has_comment_reply=True
                )
                db.session.add_all([free_plan, creator_plan, pro_plan])
                db.session.commit()
                print("Plans seeded successfully.")
    except OperationalError as e:
        print(f"Skipping seed_plans due to database error (OperationalError): {e}")
        db.session.rollback()
    except Exception as e:
        print(f"Error seeding plans: {e}")
        db.session.rollback()
