# tubealgo/decorators.py

from functools import wraps
from flask import flash, redirect, url_for, abort, request, jsonify
from flask_login import current_user
from tubealgo import db
from tubealgo.models import SubscriptionPlan
from datetime import date
from .services.youtube_manager import get_user_videos, update_video_details, get_single_video

# --- यहाँ बदलाव शुरू ---

# 1. एक कस्टम Exception क्लास बनाएं
class RateLimitExceeded(Exception):
    pass

def check_limits(feature):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                # API अनुरोधों के लिए JSON एरर भेजें
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.accept_mimetypes:
                    return jsonify({'error': 'Authentication required.'}), 401
                flash("Please log in to access this feature.", "error")
                return redirect(url_for('auth.login'))

            plan = SubscriptionPlan.query.filter_by(plan_id=current_user.subscription_plan).first()
            if not plan:
                plan = SubscriptionPlan.query.filter_by(plan_id='free').first()

            if current_user.last_usage_date != date.today():
                current_user.last_usage_date = date.today()
                current_user.daily_keyword_searches = 0
                current_user.daily_ai_generations = 0

            # 2. handle_limit_error को हटाकर RateLimitExceeded एरर को raise करें
            if feature == 'add_competitor' and (plan.competitors_limit != -1 and current_user.competitors.count() >= plan.competitors_limit):
                raise RateLimitExceeded(f"You've reached the maximum of {plan.competitors_limit} competitors for your plan. Please upgrade.")
            
            elif feature == 'keyword_search':
                if plan.keyword_searches_limit != -1 and current_user.daily_keyword_searches >= plan.keyword_searches_limit:
                    raise RateLimitExceeded(f"You've reached your daily limit of {plan.keyword_searches_limit} keyword searches. Please upgrade.")
                current_user.daily_keyword_searches += 1
            
            elif feature == 'ai_generation':
                if plan.ai_generations_limit != -1 and current_user.daily_ai_generations >= plan.ai_generations_limit:
                    raise RateLimitExceeded(f"You've reached your daily limit of {plan.ai_generations_limit} AI generations. Please upgrade.")
                current_user.daily_ai_generations += 1

            elif feature == 'discover_tools' and not plan.has_discover_tools:
                raise RateLimitExceeded("The Discover tool is a premium feature. Please upgrade to access it.")

            db.session.commit()
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- यहाँ बदलाव खत्म ---

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function