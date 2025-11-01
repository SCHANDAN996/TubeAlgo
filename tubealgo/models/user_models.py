# tubealgo/models/user_models.py

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .. import db, login_manager
from datetime import date, datetime

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # === 1. 'name' कॉलम जोड़ें ===
    name = db.Column(db.String(150), nullable=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    profile_pic_url = db.Column(db.String(512), nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)

    google_access_token = db.Column(db.String(1024), nullable=True)
    google_refresh_token = db.Column(db.String(1024), nullable=True)
    google_token_expiry = db.Column(db.DateTime, nullable=True)

    telegram_chat_id = db.Column(db.String(100), unique=True, nullable=True)
    default_channel_name = db.Column(db.String(100), nullable=True)
    default_social_handles = db.Column(db.Text, nullable=True)
    default_contact_info = db.Column(db.String(200), nullable=True)
    
    # === 2. 'subscription_plan' को 'plan_id' से बदलें और Foreign Key बनाएँ ===
    plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plan.id'), nullable=True)
    subscription_status = db.Column(db.String(50), default='inactive') # e.g., active, inactive, cancelled, past_due
    subscription_end_date = db.Column(db.DateTime, nullable=True)

    last_usage_date = db.Column(db.Date, default=date.today)
    daily_keyword_searches = db.Column(db.Integer, default=0)
    daily_ai_generations = db.Column(db.Integer, default=0)
    daily_bulk_edits = db.Column(db.Integer, default=0)

    referral_code = db.Column(db.String(20), unique=True, nullable=False)
    referred_by = db.Column(db.String(20), nullable=True)
    referral_credits = db.Column(db.Integer, default=0)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default='active') # active, suspended

    last_seen = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)

    dashboard_layout = db.Column(db.Text, nullable=True) # JSON string for layout
    timezone = db.Column(db.String(100), nullable=True) # User's preferred timezone

    # Telegram Notification Preferences
    telegram_notify_new_video = db.Column(db.Boolean, default=True)
    telegram_notify_viral_video = db.Column(db.Boolean, default=True)
    telegram_notify_milestone = db.Column(db.Boolean, default=True)
    telegram_notify_ai_suggestion = db.Column(db.Boolean, default=True)
    telegram_notify_weekly_report = db.Column(db.Boolean, default=False)

    # Relationships
    # === 3. 'plan' रिलेशनशिप जोड़ें ===
    plan = db.relationship('SubscriptionPlan', backref='users')
    channel = db.relationship('YouTubeChannel', backref='user', uselist=False, cascade="all, delete-orphan")
    competitors = db.relationship('Competitor', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    search_history = db.relationship('SearchHistory', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    payments = db.relationship('Payment', backref='user', lazy='dynamic')
    goals = db.relationship('Goal', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    content_ideas = db.relationship('ContentIdea', backref='user', lazy='dynamic', cascade="all, delete-orphan")
    dashboard_cache_rel = db.relationship('DashboardCache', backref='user', uselist=False, cascade="all, delete-orphan")


    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
             return False
        return check_password_hash(self.password_hash, password)

# ... (बाकी की फ़ाइल वैसी ही रहेगी) ...

# Model for storing search history
class SearchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False) # Added ondelete
    topic = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

# Model for Content Planner Ideas
class ContentIdea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False) # Added ondelete
    title = db.Column(db.Text, nullable=False) # Full internal title or AI generated title
    display_title = db.Column(db.String(255), nullable=True) # Shorter title for display on board
    notes = db.Column(db.Text, nullable=True) # For script outline or other notes
    status = db.Column(db.String(50), nullable=False, default='idea', index=True) # idea, scripting, filming, editing, scheduled
    position = db.Column(db.Integer, nullable=False, default=0) # Order within status column
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

# Model for User Goals
class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False) # Added ondelete
    goal_type = db.Column(db.String(50), nullable=False) # e.g., 'subscribers', 'views', 'videos_uploaded'
    target_value = db.Column(db.Integer, nullable=False)
    start_value = db.Column(db.Integer, nullable=False) # Value when goal was set
    target_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Ensure only one active goal per type per user
    __table_args__ = (db.UniqueConstraint('user_id', 'goal_type', 'is_active', name='_user_goal_type_active_uc'),)


@login_manager.user_loader
def load_user(user_id):
    """Loads user for Flask-Login."""
    return User.query.get(int(user_id))