# tubealgo/models/payment_models.py

from .. import db
from datetime import datetime

class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_type = db.Column(db.String(20), nullable=False, default='percentage')
    discount_value = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    valid_until = db.Column(db.DateTime, nullable=True)
    max_uses = db.Column(db.Integer, default=100)
    times_used = db.Column(db.Integer, default=0)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    razorpay_payment_id = db.Column(db.String(100), nullable=True) # Can be null for other gateways
    razorpay_order_id = db.Column(db.String(100), unique=True, nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), nullable=False, default='INR')
    plan_id = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='captured')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
class SubscriptionPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    slashed_price = db.Column(db.Integer, nullable=True)
    competitors_limit = db.Column(db.Integer, nullable=False)
    keyword_searches_limit = db.Column(db.Integer, nullable=False)
    ai_generations_limit = db.Column(db.Integer, nullable=False)
    has_discover_tools = db.Column(db.Boolean, default=False)
    has_ai_suggestions = db.Column(db.Boolean, default=False)
    playlist_suggestions_limit = db.Column(db.Integer, nullable=False, default=3)
    is_popular = db.Column(db.Boolean, default=False)
    
    # === बदलाव यहाँ है: नया कॉलम जोड़ा गया ===
    has_comment_reply = db.Column(db.Boolean, nullable=False, default=False)
    # === बदलाव यहाँ खत्म है ===