# tubealgo/models/system_models.py

import os
import json
from datetime import datetime
from .. import db
from sqlalchemy.exc import OperationalError, ProgrammingError
import traceback

# --- SystemLog, log_system_event, is_admin_telegram_user ---
class SystemLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    log_type = db.Column(db.String(50), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text, nullable=True)

def log_system_event(message, log_type='INFO', details=None, traceback_info=None):
    """Logs an event to the database and sends a notification for critical errors."""
    try:
        from ..services.notification_service import send_telegram_message

        details_str = ""
        if details:
            if isinstance(details, dict):
                if traceback_info:
                    details['traceback'] = traceback_info
                details_str = json.dumps(details, indent=2, default=str)
            else:
                details_str = str(details)
                if traceback_info:
                    details_str += f"\n\nTraceback:\n{traceback_info}"
        elif traceback_info:
             details_str = f"Traceback:\n{traceback_info}"

        log_entry = SystemLog(
            log_type=log_type,
            message=message,
            details=details_str
        )
        db.session.add(log_entry)
        db.session.commit()

        CRITICAL_LOG_TYPES = ['QUOTA_EXCEEDED', 'ERROR', 'PROJECT_QUOTA_EXCEEDED']
        if log_type in CRITICAL_LOG_TYPES:
            admin_chat_id = get_setting('ADMIN_TELEGRAM_CHAT_ID')
            if admin_chat_id:
                alert_title = "Critical Alert" if log_type == 'ERROR' else "Quota Alert"
                icon = "🚨" if log_type == 'ERROR' else "⚠️"

                telegram_message = (
                    f"{icon} *{alert_title}: {log_type}*\n\n"
                    f"*Message:* {message}\n\n"
                )
                if details_str:
                    truncated_details = details_str[:1000] + ('...' if len(details_str) > 1000 else '')
                    telegram_message += f"*Details:* ```\n{truncated_details}\n```"

                send_telegram_message(admin_chat_id, telegram_message)

    except Exception as e:
        print(f"!!! FAILED TO LOG SYSTEM EVENT (Original message: {message}): {e}\n{traceback.format_exc()}")
        db.session.rollback()


def is_admin_telegram_user(chat_id):
    admin_chat_id = get_setting('ADMIN_TELEGRAM_CHAT_ID')
    if admin_chat_id and str(chat_id) == str(admin_chat_id):
        return True
    return False

# --- SiteSetting Model ---
class SiteSetting(db.Model):
    key = db.Column(db.String(100), primary_key=True, unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)

def get_setting(key, default=None):
    """
    Safely gets a setting from the database.
    Returns default if the table doesn't exist or another DB error occurs.
    """
    try:
        setting = SiteSetting.query.get(key)
        if setting and setting.value is not None:
            val_lower = setting.value.lower()
            if val_lower == 'true': return True
            if val_lower == 'false': return False
            return setting.value
        return default
    except (OperationalError, ProgrammingError) as db_err:
        db.session.rollback()
        return default
    except Exception as e:
        db.session.rollback()
        return default

def get_config_value(key, default=None):
    """
    Gets a configuration value, prioritizing the database over environment variables.
    """
    db_value = get_setting(key)

    if db_value is not None:
        return db_value

    return os.environ.get(key, default)

# --- ApiCache, APIKeyStatus, DashboardCache ---
class ApiCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(255), unique=True, nullable=False, index=True)
    cache_value = db.Column(db.JSON, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)

class APIKeyStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key_identifier = db.Column(db.String(20), unique=True, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='active', index=True)
    last_failure_at = db.Column(db.DateTime, nullable=True, index=True)

class DashboardCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, unique=True)
    data = db.Column(db.JSON, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

# === नया मॉडल जोड़ा गया ===
class CompetitorAnalysisCache(db.Model):
    """Stores cached analysis data for competitors"""
    id = db.Column(db.Integer, primary_key=True)
    competitor_id = db.Column(
        db.Integer, 
        db.ForeignKey('competitor.id', ondelete='CASCADE'), 
        nullable=False, 
        unique=True
    )
    data = db.Column(db.JSON, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
