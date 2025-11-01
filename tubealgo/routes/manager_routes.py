# tubealgo/routes/manager_routes.py

import os
import re
import threading
import json
import uuid
from datetime import timedelta, datetime
from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify, abort, current_app
from flask_login import login_required, current_user
from google.auth.exceptions import RefreshError
from flask_wtf import FlaskForm
from ..forms import VideoForm, UploadForm, PlaylistForm
from ..services.youtube_manager import (
    get_user_videos, update_video_details, get_single_video, 
    upload_video, set_video_thumbnail, get_user_playlists,
    create_playlist, get_single_playlist, update_playlist,
    get_competitors_playlists
)
from ..services.ai_service import generate_titles_and_tags, generate_description, generate_playlist_suggestions
from ..decorators import check_limits, RateLimitExceeded
from ..models import get_setting, log_system_event, SubscriptionPlan
from .utils import get_credentials

manager_bp = Blueprint('manager', __name__, url_prefix='/manage')

def _parse_duration(duration_str):
    """Parses ISO 8601 duration string (e.g., PT1M35S) into total seconds."""
    if not duration_str: return 0
    duration_regex = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
    parts = duration_regex.match(duration_str)
    if not parts: return 0
    parts = parts.groups()
    time_params = {name: int(value) for name, value in zip(["hours", "minutes", "seconds"], parts) if value}
    return timedelta(**time_params).total_seconds()

def _upload_to_youtube_in_background(app, creds_json, video_filepath, thumbnail_filepath, metadata):
    """Background task to upload video and thumbnail, and then clean up files."""
    with app.app_context():
        try:
            from google.oauth2.credentials import Credentials
            
            print("BACKGROUND TASK: Started uploading to YouTube.")
            creds = Credentials.from_authorized_user_info(json.loads(creds_json))
            
            upload_result = upload_video(creds, video_filepath, metadata)

            if 'error' in upload_result:
                log_system_event("Background YouTube upload failed", "ERROR", details=upload_result)
                return

            video_id = upload_result.get('id')
            print(f"BACKGROUND TASK: Video uploaded to YouTube with ID: {video_id}")

            if thumbnail_filepath:
                thumb_result = set_video_thumbnail(creds, video_id, thumbnail_filepath)
                if 'error' in thumb_result:
                    log_system_event("Background thumbnail upload failed", "ERROR", details=thumb_result)
                else:
                    print(f"BACKGROUND TASK: Thumbnail set for video ID: {video_id}")
        
        except Exception as e:
            log_system_event("Exception in background upload task", "ERROR", details=str(e))
        
        finally:
            folder_path = os.path.dirname(video_filepath)
            
            if os.path.exists(video_filepath):
                try:
                    os.remove(video_filepath)
                    print(f"BACKGROUND TASK: Deleted temp video file: {video_filepath}")
                except Exception as e:
                    log_system_event("Cleanup Error", "ERROR", f"Failed to delete temp video file: {video_filepath}. Error: {e}")
            
            if thumbnail_filepath and os.path.exists(thumbnail_filepath):
                try:
                    os.remove(thumbnail_filepath)
                    print(f"BACKGROUND TASK: Deleted temp thumbnail file: {thumbnail_filepath}")
                except Exception as e:
                    log_system_event("Cleanup Error", "ERROR", f"Failed to delete temp thumbnail file: {thumbnail_filepath}. Error: {e}")

            try:
                if os.path.exists(folder_path) and not os.listdir(folder_path):
                    os.rmdir(folder_path)
                    print(f"BACKGROUND TASK: Deleted temp directory: {folder_path}")
            except Exception as e:
                 log_system_event("Cleanup Error", "ERROR", f"Failed to delete temp directory: {folder_path}. Error: {e}")


@manager_bp.route('/')
@login_required
def index():
    return redirect(url_for('manager.manage_videos'))

def handle_api_error(error_dict):
    if isinstance(error_dict, dict) and 'error' in error_dict:
        error_message = str(error_dict['error'])
        if 'quotaExceeded' in error_message:
            log_system_event(
                message="YouTube API quota has been exceeded.",
                log_type='QUOTA_EXCEEDED',
                details={'error': error_message}
            )
            flash('Something went wrong on our end. Our team has been notified and we are working on it. Please try again later.', 'error')
        elif 'invalid_grant' in error_message:
            flash('Your permission has expired. Please grant permission again to manage your YouTube account.', 'warning')
            return redirect(url_for('auth.connect_youtube'))
        else:
            log_system_event(
                message="An unhandled API error occurred in YT Manager.",
                log_type='ERROR',
                details={'error': error_message, 'user_id': current_user.id}
            )
            flash(f'An API error occurred. If the problem persists, please contact support.', 'error')
    return None

@manager_bp.route('/videos')
@login_required
def manage_videos():
    creds = get_credentials()
    if not creds:
        flash('Please connect your Google account with YouTube permission to manage videos.', 'warning')
        return redirect(url_for('auth.connect_youtube'))
    
    videos = []
    try:
        video_data = get_user_videos(creds)
        redirect_response = handle_api_error(video_data)
        if redirect_response:
            return redirect_response
        if video_data and 'error' not in video_data:
            videos = video_data
    except RefreshError:
        flash('Your permission has expired. Please grant permission to manage your YouTube videos.', 'warning')
        return redirect(url_for('auth.connect_youtube'))
    except Exception as e:
        log_system_event(f"Unexpected error in manage_videos: {str(e)}", 'ERROR', {'user_id': current_user.id})
        flash('An unexpected error occurred. Our team has been notified.', 'error')
        
    return render_template('manage_videos.html', videos=videos)

@manager_bp.route('/playlists')
@login_required
def manage_playlists():
    creds = get_credentials()
    if not creds:
        flash('Please connect your Google account with YouTube permission to manage playlists.', 'warning')
        return redirect(url_for('auth.connect_youtube'))

    playlists = []
    try:
        playlist_data = get_user_playlists(creds)
        redirect_response = handle_api_error(playlist_data)
        if redirect_response:
            return redirect_response
        if playlist_data and 'error' not in playlist_data:
            playlists = playlist_data
    except RefreshError:
        flash('Your permission has expired. Please grant permission to manage your YouTube playlists.', 'warning')
        return redirect(url_for('auth.connect_youtube'))
    except Exception as e:
        log_system_event(f"Unexpected error in manage_playlists: {str(e)}", 'ERROR', {'user_id': current_user.id})
        flash('An unexpected error occurred. Our team has been notified.', 'error')
    
    form = FlaskForm()  
    return render_template('manage_playlists.html', playlists=playlists, form=form)

@manager_bp.route('/playlists/create', methods=['GET', 'POST'])
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
            return redirect(url_for('auth.connect_youtube'))
        
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
        return redirect(url_for('manager.manage_playlists'))
        
    return render_template('create_playlist.html', form=form)

@manager_bp.route('/playlists/generate-ideas', methods=['POST'])
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
                    'action_url': url_for('competitor.competitors', next=url_for('manager.manage_playlists'))
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

@manager_bp.route('/playlists/edit/<playlist_id>', methods=['GET', 'POST'])
@login_required
def edit_playlist_route(playlist_id):
    creds = get_credentials()
    if not creds:
        flash('Please connect your Google account to edit playlists.', 'warning')
        return redirect(url_for('auth.connect_youtube'))

    playlist_details = get_single_playlist(creds, playlist_id)
    if 'error' in playlist_details:
        flash(playlist_details['error'], 'error')
        return redirect(url_for('manager.manage_playlists'))
    
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
        return redirect(url_for('manager.manage_playlists'))

    return render_template('edit_playlist.html', form=form, playlist=playlist_details)

@manager_bp.route('/edit/<video_id>', methods=['GET', 'POST'])
@login_required
def edit_video(video_id):
    creds = get_credentials()
    if not creds:
        flash('Please connect your Google account to manage videos.', 'warning')
        return redirect(url_for('auth.connect_youtube'))

    video_details = get_single_video(creds, video_id)
    if 'error' in video_details:
        flash(video_details['error'], 'error')
        return redirect(url_for('manager.manage_videos'))

    duration_str = video_details.get('contentDetails', {}).get('duration', 'PT0S')
    total_seconds = _parse_duration(duration_str)
    
    is_video_short = total_seconds > 0 and total_seconds <= 61
    
    form = VideoForm(obj=video_details['snippet'])
    
    is_scheduled = video_details['status'].get('publishAt') and datetime.fromisoformat(video_details['status']['publishAt'].replace('Z', '')) > datetime.utcnow()
    current_visibility = 'schedule' if is_scheduled else video_details['status'].get('privacyStatus', 'private')

    if request.method == 'GET':
        form.tags.data = ", ".join(video_details['snippet'].get('tags', []))
        if is_scheduled:
            form.publish_at.data = datetime.fromisoformat(video_details['status']['publishAt'].replace('Z', ''))

    if form.validate_on_submit():
        visibility_choice = form.visibility.data
        publish_at_time = form.publish_at.data

        final_visibility = 'private' if visibility_choice == 'schedule' and publish_at_time else visibility_choice

        update_result = update_video_details(
            creds, video_id, 
            form.title.data, 
            form.description.data, 
            [tag.strip() for tag in request.form.get('tags', '').split(',') if tag.strip()],
            final_visibility,
            publish_at_time
        )
        if 'error' in update_result:
            flash(f"Error updating video details: {update_result['error']}", 'error')
        else:
            flash('Video details updated successfully!', 'success')

        thumbnail_file = form.thumbnail.data
        if thumbnail_file and thumbnail_file.filename and not is_video_short:
            upload_folder = os.path.join(current_app.instance_path, 'uploads', str(uuid.uuid4()))
            os.makedirs(upload_folder, exist_ok=True)
            thumb_filename = f"thumb_{thumbnail_file.filename}"
            thumbnail_filepath = os.path.join(upload_folder, thumb_filename)
            thumbnail_file.save(thumbnail_filepath)

            thumb_result = set_video_thumbnail(creds, video_id, thumbnail_filepath)
            
            if os.path.exists(thumbnail_filepath):
                os.remove(thumbnail_filepath)
                os.rmdir(upload_folder)

            if 'error' in thumb_result:
                flash(f"Error setting thumbnail: {thumb_result['error']}", 'error')
            else:
                flash('Thumbnail updated successfully!', 'success')
        
        return redirect(url_for('manager.manage_videos'))

    return render_template(
        'edit_video.html', 
        video=video_details, 
        form=form, 
        current_visibility=current_visibility, 
        has_competitors=current_user.competitors.count() > 0,
        is_video_short=is_video_short
    )

@manager_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if not get_setting('feature_video_upload', True):
        abort(404)
    
    form = UploadForm()
    creds = get_credentials()

    if not creds:
        if request.method == 'POST':
            return jsonify({'error': 'Authentication expired. Please reconnect your Google account.'}), 401
        flash('Please connect your Google account to upload videos.', 'warning')
        return redirect(url_for('auth.connect_youtube'))

    if request.method == 'POST':
        form = UploadForm()

        if form.validate_on_submit():
            video_file = form.video_file.data
            thumbnail_file = form.thumbnail.data
            
            upload_folder = os.path.join(current_app.instance_path, 'uploads', str(uuid.uuid4()))
            os.makedirs(upload_folder, exist_ok=True)
            
            video_filepath = os.path.join(upload_folder, video_file.filename)
            video_file.save(video_filepath)

            thumbnail_filepath = None
            if thumbnail_file and thumbnail_file.filename:
                thumb_filename = f"thumb_{thumbnail_file.filename}"
                thumbnail_filepath = os.path.join(upload_folder, thumb_filename)
                thumbnail_file.save(thumbnail_filepath)

            visibility_choice = form.visibility.data
            publish_at_str = request.form.get('publish_at')
            publish_at_time = None
            if visibility_choice == 'schedule' and publish_at_str:
                try:
                    publish_at_time = datetime.fromisoformat(publish_at_str)
                except ValueError:
                    return jsonify({'error': 'Invalid schedule date format.'}), 400
            
            final_visibility = 'private' if visibility_choice == 'schedule' and publish_at_time else visibility_choice

            metadata = {
                "title": form.title.data,
                "description": form.description.data,
                "tags": [tag.strip() for tag in request.form.get('tags', '').split(',') if tag.strip()],
                "privacy_status": final_visibility,
                "publish_at": publish_at_time
            }
            
            thread = threading.Thread(
                target=_upload_to_youtube_in_background,
                args=(current_app._get_current_object(), creds.to_json(), video_filepath, thumbnail_filepath, metadata)
            )
            thread.start()

            return jsonify({
                'success': True, 
                'message': 'Upload Started! We will process it in the background.', 
                'redirect_url': url_for('manager.manage_videos')
            })
        else:
            error_message = "Invalid form data. Please check all fields."
            if form.errors:
                first_error_key = next(iter(form.errors))
                error_message = f"{first_error_key.replace('_', ' ').title()}: {form.errors[first_error_key][0]}"

            return jsonify({'error': error_message, 'details': form.errors}), 400

    return render_template('upload_video.html', form=form, has_competitors=current_user.competitors.count() > 0)


@manager_bp.route('/api/generate-titles', methods=['POST'])
@login_required
def api_generate_titles():
    try:
        @check_limits(feature='ai_generation')
        def do_api_generation():
            data = request.json
            topic = data.get('topic')
            if not topic:
                return jsonify({'error': 'bad_request', 'message': 'Topic is required.'}), 400
            results = generate_titles_and_tags(current_user, topic)
            return jsonify(results)
        return do_api_generation()
    except RateLimitExceeded as e:
        return jsonify({'error': str(e), 'details': str(e)}), 429

@manager_bp.route('/api/generate-tags', methods=['POST'])
@login_required
def api_generate_tags():
    try:
        @check_limits(feature='ai_generation')
        def do_api_generation():
            data = request.json
            topic = data.get('topic')
            exclude_tags = data.get('exclude_tags', [])
            if not topic:
                return jsonify({'error': 'bad_request', 'message': 'Topic is required.'}), 400
            
            results = generate_titles_and_tags(current_user, topic, exclude_tags=exclude_tags)

            if 'tags' in results and current_user.channel and current_user.channel.channel_title:
                channel_name_tag = current_user.channel.channel_title
                
                if isinstance(results.get('tags'), dict) and 'main_keywords' in results['tags']:
                    all_tags_lower = [tag.lower() for cat_tags in results['tags'].values() for tag in cat_tags]
                    
                    if channel_name_tag.lower() not in all_tags_lower:
                        results['tags']['main_keywords'].insert(0, channel_name_tag)

            return jsonify(results)
        return do_api_generation()
    except RateLimitExceeded as e:
        return jsonify({'error': str(e), 'details': str(e)}), 429

@manager_bp.route('/api/generate-description', methods=['POST'])
@login_required
def api_generate_description():
    try:
        @check_limits(feature='ai_generation')
        def do_api_generation():
            data = request.json
            topic = data.get('topic')
            title = data.get('title')
            language = data.get('language', 'English')
            
            if not topic or not title:
                return jsonify({'error': 'Topic and title are required.'}), 400
                
            result = generate_description(current_user, topic, title, language)
            return jsonify(result)
        return do_api_generation()
    except RateLimitExceeded as e:
        return jsonify({'error': str(e), 'details': str(e)}), 429