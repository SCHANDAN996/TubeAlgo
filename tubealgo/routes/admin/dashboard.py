# tubealgo/routes/admin/dashboard.py

from flask import render_template
from flask_login import login_required
from . import admin_bp
from ... import db
from ...decorators import admin_required
from ...models import User, APIKeyStatus, get_config_value
from sqlalchemy import func
from datetime import date, datetime
import pytz

@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    total_users = User.query.count()
    subscribed_users = User.query.filter(User.subscription_plan != 'free').count()
    users_today = User.query.filter(func.date(User.created_at) == date.today()).count()
    recent_users = User.query.order_by(User.id.desc()).limit(5).all()

    api_keys_str = get_config_value('YOUTUBE_API_KEYS', '')
    api_keys_list = [key.strip() for key in api_keys_str.split(',') if key.strip()]
    
    try:
        pacific_tz = pytz.timezone('America/Los_Angeles')
        pacific_now = datetime.now(pacific_tz)
        last_reset_pacific = pacific_now.replace(hour=0, minute=0, second=0, microsecond=0)
        last_reset_utc = last_reset_pacific.astimezone(pytz.utc)

        APIKeyStatus.query.filter(
            APIKeyStatus.status == 'exhausted',
            APIKeyStatus.last_failure_at < last_reset_utc
        ).update({'status': 'active', 'last_failure_at': None})
        db.session.commit()
    except Exception as e:
        print(f"Timezone conversion or DB reset failed: {e}")
        db.session.rollback()

    def mask_key_yt(key):
        if key and len(key) > 12:
            return f"{key[:8]}...{key[-4:]}"
        return "Invalid Key Format"
    
    key_identifiers = [mask_key_yt(key) for key in api_keys_list]
    key_statuses_query = APIKeyStatus.query.filter(APIKeyStatus.key_identifier.in_(key_identifiers)).all()
    key_status_map = {status.key_identifier: status for status in key_statuses_query}
    
    exhausted_today_count = sum(1 for status in key_status_map.values() if status.status == 'exhausted')

    return render_template('admin/dashboard.html', 
                           total_users=total_users,
                           subscribed_users=subscribed_users,
                           users_today=users_today,
                           recent_users=recent_users,
                           api_key_count=len(api_keys_list),
                           key_identifiers=key_identifiers,
                           key_status_map=key_status_map,
                           exhausted_today_count=exhausted_today_count)