# tubealgo/routes/playlist_manager_routes.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from ..forms import PlaylistForm
from ..services.youtube_manager import (
    get_user_playlists, create_playlist, get_single_playlist, update_playlist,
    get_competitors_playlists
)
from ..services.ai_service import generate_playlist_suggestions
from ..decorators import check_limits, RateLimitExceeded
from ..models import SubscriptionPlan
from .utils import get_credentials
from .. import db

playlist_manager_bp = Blueprint('playlist_manager', __name__)

@playlist_manager_bp.route('/playlists')
@login_required
def manage_playlists():
    creds = get_credentials()
    if not creds:
        flash('Please connect your Google account to manage playlists.', 'warning')
        return redirect(url_for('auth_google.connect_youtube'))

    playlists = []
    try:
        playlist_data = get_user_playlists(creds)
        if isinstance(playlist_data, dict) and 'error' in playlist_data:
            flash(f"An API error occurred: {playlist_data['error']}", 'error')
            if 'invalid_grant' in playlist_data['error']:
                return redirect(url_for('auth_google.connect_youtube'))
        elif playlist_data:
            playlists = playlist_data
    except Exception as e:
        flash('An unexpected error occurred.', 'error')
    
    form = FlaskForm()  
    return render_template('manage_playlists.html', playlists=playlists, form=form)

@playlist_manager_bp.route('/playlists/create', methods=['GET', 'POST'])
@login_required
def create_playlist_route():
    form = PlaylistForm()
    if request.method == 'GET':
        prefill_title = request.args.get('title')
        prefill_desc = request.args.get('desc')
        if prefill_title:
            form.title.data = prefill_title
        if prefill_desc:
            form.description.data = prefill_desc
            
    if form.validate_on_submit():
        creds = get_credentials()
        if not creds:
            flash('Please connect your Google account to create playlists.', 'warning')
            return redirect(url_for('auth_google.connect_youtube'))
        
        result = create_playlist(
            creds,
            title=form.title.data,
            description=form.description.data,
            privacy_status=form.privacy_status.data
        )
        if 'error' in result:
            flash(f"Error creating playlist: {result['error']}", 'error')
        else:
            flash(f"Playlist '{form.title.data}' created successfully!", 'success')
        return redirect(url_for('playlist_manager.manage_playlists'))
        
    return render_template('create_playlist.html', form=form)

@playlist_manager_bp.route('/playlists/edit/<playlist_id>', methods=['GET', 'POST'])
@login_required
def edit_playlist_route(playlist_id):
    creds = get_credentials()
    if not creds:
        flash('Please connect your Google account to edit playlists.', 'warning')
        return redirect(url_for('auth_google.connect_youtube'))

    playlist_details = get_single_playlist(creds, playlist_id)
    if 'error' in playlist_details:
        flash(playlist_details['error'], 'error')
        return redirect(url_for('playlist_manager.manage_playlists'))
    
    form = PlaylistForm()
    if request.method == 'GET':
        form.title.data = playlist_details.get('snippet', {}).get('title')
        form.description.data = playlist_details.get('snippet', {}).get('description')
        form.privacy_status.data = playlist_details.get('status', {}).get('privacyStatus')

    if form.validate_on_submit():
        result = update_playlist(
            creds,
            playlist_id=playlist_id,
            title=form.title.data,
            description=form.description.data,
            privacy_status=form.privacy_status.data
        )
        if 'error' in result:
            flash(f"Error updating playlist: {result['error']}", 'error')
        else:
            flash(f"Playlist '{form.title.data}' updated successfully!", 'success')
        return redirect(url_for('playlist_manager.manage_playlists'))

    return render_template('edit_playlist.html', form=form, playlist=playlist_details)

@playlist_manager_bp.route('/playlists/generate-ideas', methods=['POST'])
@login_required
def generate_playlist_ideas():
    try:
        @check_limits(feature='ai_generation')
        def do_generation():
            creds = get_credentials()
            if not creds:
                return jsonify({'error': 'Please connect your Google Account first.'}), 400

            if current_user.competitors.count() == 0:
                return jsonify({
                    'error': 'no_competitors', 
                    'message': 'Add competitors to get AI-powered playlist suggestions.',
                    'action_url': url_for('competitor.competitors', next=url_for('playlist_manager.manage_playlists'))
                }), 400

            plan = SubscriptionPlan.query.filter_by(plan_id=current_user.subscription_plan).first() or SubscriptionPlan.query.filter_by(plan_id='free').first()
            suggestion_limit = plan.playlist_suggestions_limit if plan else 3
            user_playlists = get_user_playlists(creds)
            user_playlist_titles = [p['title'] for p in user_playlists if 'title' in p]
            
            competitor_video_titles_or_error = get_competitors_playlists(current_user)
            
            if isinstance(competitor_video_titles_or_error, dict) and 'error' in competitor_video_titles_or_error:
                return jsonify(competitor_video_titles_or_error), 500

            competitor_video_titles = competitor_video_titles_or_error

            suggestions = generate_playlist_suggestions(current_user, user_playlist_titles, competitor_video_titles, limit=suggestion_limit)
            return jsonify(suggestions)
        return do_generation()
    except RateLimitExceeded as e:
        return jsonify({'error': {'details': str(e)}}), 429