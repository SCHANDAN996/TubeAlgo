# tubealgo/auth.py

import os
import secrets
from flask import render_template, request, redirect, url_for, flash, Blueprint, session
from flask_login import login_user, logout_user, current_user, login_required
from google_auth_oauthlib.flow import Flow
from . import db
from .models import User, get_config_value
from .forms import SignupForm, LoginForm
from .services import user_service

auth = Blueprint('auth', __name__)

LOGIN_SCOPES = [
    'https://www.googleapis.com/auth/userinfo.email', 
    'https://www.googleapis.com/auth/userinfo.profile', 
    'openid'
]
YOUTUBE_SCOPES = [
    'https://www.googleapis.com/auth/youtube', 
    'https://www.googleapis.com/auth/youtube.upload'
]

def get_flow(scopes, redirect_uri):
    """Helper function to create a Google Auth Flow."""
    CLIENT_SECRETS_FILE = {
        "web": {
            "client_id": get_config_value("GOOGLE_CLIENT_ID"),
            "client_secret": get_config_value("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return Flow.from_client_config(CLIENT_SECRETS_FILE, scopes=scopes, redirect_uri=redirect_uri)

@auth.route('/login/google')
def google_login():
    """Handles initial login/signup with Google (basic permissions only)."""
    flow = get_flow(LOGIN_SCOPES, url_for('auth.google_callback', _external=True))
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'] = state
    session['flow_type'] = 'login'
    session['oauth_scopes'] = LOGIN_SCOPES
    return redirect(authorization_url)

@auth.route('/connect/youtube')
@login_required
def connect_youtube():
    """Handles connecting a YouTube channel, requesting ALL permissions."""
    # --- THIS IS THE FIX ---
    # Combine login and YouTube scopes to get a powerful refresh token
    all_scopes = list(set(LOGIN_SCOPES + YOUTUBE_SCOPES))
    
    flow = get_flow(all_scopes, url_for('auth.google_callback', _external=True))
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true', prompt='consent')
    session['state'] = state
    session['flow_type'] = 'youtube'
    session['oauth_scopes'] = all_scopes
    return redirect(authorization_url)

@auth.route('/callback')
def google_callback():
    """Single callback to handle both flows."""
    state = session.pop('state', None)
    flow_type = session.pop('flow_type', 'login')
    scopes_used = session.pop('oauth_scopes', LOGIN_SCOPES)
    
    if not state:
        flash('The authentication state is missing. Please try again.', 'error')
        return redirect(url_for('auth.login'))
    
    flow = get_flow(scopes_used, url_for('auth.google_callback', _external=True))
    
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        flash(f"Error fetching Google token: {e}", "error")
        return redirect(url_for('auth.login'))
        
    credentials = flow.credentials
    user, message, category = user_service.process_google_login(credentials, flow_type)

    if user:
        if not current_user.is_authenticated:
            login_user(user, remember=True)
        flash(message, category)
        return redirect(url_for('dashboard.dashboard'))
    else:
        flash(message, category)
        return redirect(url_for('auth.login'))

# --- Standard routes remain unchanged ---
@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated: return redirect(url_for('dashboard.dashboard'))
    form = SignupForm()
    if form.validate_on_submit():
        referral_code = session.pop('referral_code', None)
        new_user, message, category = user_service.create_new_user(email=form.email.data, password=form.password.data, referred_by_code=referral_code)
        if not new_user:
            flash(message, category)
            return redirect(url_for('auth.signup'))
        flash(message, category)
        return redirect(url_for('auth.login'))
    return render_template('signup.html', form=form)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard.dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.dashboard'))
        else:
            flash('Login unsuccessful. Please check your email and password.', 'error')
    return render_template('login.html', form=form)

@auth.route('/logout')
@login_required
def logout():
    session.clear()
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('core.home'))