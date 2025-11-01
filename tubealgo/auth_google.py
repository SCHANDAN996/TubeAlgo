# tubealgo/auth_google.py

import os
from flask import render_template, request, redirect, url_for, flash, Blueprint, session
from flask_login import login_user, current_user, login_required
from google_auth_oauthlib.flow import Flow
from . import db # <-- THIS IS THE CORRECTED IMPORT
from .models import get_config_value
from .services import user_service

auth_google_bp = Blueprint('auth_google', __name__)

LOGIN_SCOPES = [
    'https://www.googleapis.com/auth/userinfo.email', 
    'https://www.googleapis.com/auth/userinfo.profile', 
    'openid'
]

YOUTUBE_SCOPES = [
    'https://www.googleapis.com/auth/youtube', 
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/yt-analytics.readonly',
    'https://www.googleapis.com/auth/youtube.force-ssl'
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

@auth_google_bp.route('/login/google')
def google_login():
    """Handles initial login/signup with Google (basic permissions only)."""
    flow = get_flow(LOGIN_SCOPES, url_for('auth_google.google_callback', _external=True))
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'] = state
    session['flow_type'] = 'login'
    session['oauth_scopes'] = LOGIN_SCOPES
    return redirect(authorization_url)

@auth_google_bp.route('/connect/youtube')
@login_required
def connect_youtube():
    """Handles connecting a YouTube channel, requesting ALL permissions."""
    
    # Clear old tokens to ensure a fresh authorization with new scopes
    current_user.google_access_token = None
    current_user.google_refresh_token = None
    current_user.google_token_expiry = None
    db.session.commit()
    
    all_scopes = list(set(LOGIN_SCOPES + YOUTUBE_SCOPES))
    
    flow = get_flow(all_scopes, url_for('auth_google.google_callback', _external=True))
    # 'prompt=consent' forces Google to show the permission screen every time
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true', prompt='consent')
    session['state'] = state
    session['flow_type'] = 'youtube'
    session['oauth_scopes'] = all_scopes
    return redirect(authorization_url)

@auth_google_bp.route('/callback')
def google_callback():
    """Single callback to handle both flows."""
    state = session.pop('state', None)
    flow_type = session.pop('flow_type', 'login')
    scopes_used = session.pop('oauth_scopes', LOGIN_SCOPES)
    
    if not state:
        flash('The authentication state is missing. Please try again.', 'error')
        return redirect(url_for('auth_local.login'))
    
    flow = get_flow(scopes_used, url_for('auth_google.google_callback', _external=True))
    
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        flash(f"Error fetching Google token: {e}", "error")
        return redirect(url_for('auth_local.login'))
        
    credentials = flow.credentials
    user, message, category = user_service.process_google_login(credentials, flow_type)

    if user:
        if not current_user.is_authenticated:
            login_user(user, remember=True)
        flash(message, category)
        return redirect(url_for('dashboard.dashboard'))
    else:
        flash(message, category)
        return redirect(url_for('auth_local.login'))