# tubealgo/routes/core_routes.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_wtf import FlaskForm
from flask_login import current_user
from tubealgo import db
from tubealgo.models import SubscriptionPlan

core_bp = Blueprint('core', __name__)

@core_bp.route('/')
def home():
    return render_template('index.html')

@core_bp.route('/about')
def about():
    return render_template('about.html')

@core_bp.route('/contact')
def contact():
    return render_template('contact.html')

@core_bp.route('/pricing')
def pricing():
    # Create a form instance for CSRF token
    form = FlaskForm()
    
    # Fetch all subscription plans from database (excluding free plan)
    plans = SubscriptionPlan.query.filter(SubscriptionPlan.plan_id != 'free').all()
    
    return render_template('pricing.html', form=form, plans=plans)

@core_bp.route('/privacy')
def privacy():
    return render_template('privacy.html')

@core_bp.route('/terms')
def terms():
    return render_template('terms.html')

@core_bp.route('/refund-policy')
def refund_policy():
    return render_template('refund_policy.html')

@core_bp.route('/shipping-policy')
def shipping_policy():
    return render_template('shipping_policy.html')

@core_bp.route('/data-disclaimer')
def data_disclaimer():
    return render_template('data_disclaimer.html')

@core_bp.route('/instant-analysis', methods=['POST'])
def instant_analysis():
    from tubealgo.services.channel_fetcher import analyze_channel
    channel_url = request.form.get('channel_url', '').strip()
    
    if not channel_url:
        flash('Please enter a channel URL or handle.', 'error')
        return redirect(url_for('core.home'))
    
    try:
        result = analyze_channel(channel_url)
        if 'error' in result:
            flash(f"Analysis failed: {result['error']}", 'error')
            return redirect(url_for('core.home'))
        
        return render_template('analysis_result.html', data=result)
    
    except Exception as e:
        flash(f"An error occurred during analysis: {str(e)}", 'error')
        return redirect(url_for('core.home'))

@core_bp.route('/health')
def health_check():
    """Health check endpoint for Render"""
    try:
        from tubealgo import db
        db.session.execute('SELECT 1')
        return {'status': 'healthy', 'database': 'connected'}, 200
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}, 500
