# tubealgo/routes/competitor_routes.py

from flask import render_template, request, redirect, url_for, flash, Blueprint, jsonify
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from tubealgo import db
from tubealgo.models import Competitor, SubscriptionPlan, User, ContentIdea
from tubealgo.services.channel_fetcher import analyze_channel
from tubealgo.services.discovery_fetcher import (
    get_youtube_categories, get_top_channels_by_category, 
    find_similar_channels
)
from tubealgo.services.notification_service import send_telegram_photo_with_caption
from tubealgo.services.ai_service import generate_idea_from_competitor, analyze_transcript_with_ai
from tubealgo.routes.api_routes import get_full_competitor_package
from tubealgo.routes.utils import get_video_info_dict
from tubealgo.decorators import check_limits, RateLimitExceeded
import json
from youtube_transcript_api import YouTubeTranscriptApi


competitor_bp = Blueprint('competitor', __name__)

@competitor_bp.route('/competitors', methods=['GET'])
@login_required
def competitors():
    user_competitors_query = current_user.competitors.order_by(Competitor.position.asc()).all()
    competitors_list = [{"id": comp.id, "channel_id_youtube": comp.channel_id_youtube, "channel_title": comp.channel_title} for comp in user_competitors_query]
    
    # Pass the form object to the template for CSRF token
    form = FlaskForm() 
    
    plan = SubscriptionPlan.query.filter_by(plan_id=current_user.subscription_plan).first() or SubscriptionPlan.query.filter_by(plan_id='free').first()
    
    return render_template('competitors.html', 
                           competitors=user_competitors_query,
                           competitors_json=json.dumps(competitors_list),
                           form=form,
                           competitor_limit=plan.competitors_limit if plan else 0,
                           active_page='competitors')

@competitor_bp.route('/competitors/add', methods=['POST'])
@login_required
def add_competitor():
    try:
        plan = SubscriptionPlan.query.filter_by(plan_id=current_user.subscription_plan).first() or SubscriptionPlan.query.filter_by(plan_id='free').first()
        limit = plan.competitors_limit if plan else 0
        if limit != -1 and current_user.competitors.count() >= limit:
            return jsonify({'success': False, 'error': f"You have reached your limit of {limit} competitors."}), 403

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Invalid request. Missing JSON data.'}), 400

        channel_id_from_selection = data.get('channel_id_hidden')
        channel_query_from_input = data.get('channel_url')
        
        search_input = None
        if channel_id_from_selection and channel_id_from_selection.strip().startswith('UC'):
            search_input = channel_id_from_selection.strip()
        elif channel_query_from_input and channel_query_from_input.strip():
            search_input = channel_query_from_input.strip()

        if not search_input:
            return jsonify({'success': False, 'error': 'Please enter a channel name or URL.'}), 400
        
        analysis_data = analyze_channel(search_input)
        if 'error' in analysis_data:
            return jsonify({'success': False, 'error': analysis_data['error']}), 400
        
        existing = Competitor.query.filter_by(user_id=current_user.id, channel_id_youtube=analysis_data['id']).first()
        if existing:
            return jsonify({'success': False, 'error': f"'{analysis_data['Title']}' is already in your list."}), 409

        Competitor.query.filter_by(user_id=current_user.id).update({Competitor.position: Competitor.position + 1})
        db.session.flush()

        new_competitor = Competitor(
            user_id=current_user.id, 
            channel_id_youtube=analysis_data['id'], 
            channel_title=analysis_data['Title'], 
            thumbnail_url=analysis_data.get('Thumbnail URL', ''), 
            position=1 
        )
        db.session.add(new_competitor)
        db.session.commit()

        # *** UPDATED: Safe background task queuing ***
        try:
            from tubealgo.jobs import perform_full_analysis
            perform_full_analysis.apply_async(
                args=[new_competitor.id],
                retry=True,
                retry_policy={
                    'max_retries': 3,
                    'interval_start': 0,
                    'interval_step': 0.2,
                    'interval_max': 0.5,
                }
            )
        except Exception as celery_error:
            # Log but don't fail the request
            print(f"WARNING: Background task failed to queue: {celery_error}")
            # Data will load on-demand from frontend

        return jsonify({
            'success': True,
            'competitor': {
                "id": new_competitor.id, 
                "channel_id_youtube": new_competitor.channel_id_youtube, 
                "channel_title": new_competitor.channel_title
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'An unexpected server error occurred: {str(e)}'}), 500

@competitor_bp.route('/competitors/delete/<int:competitor_id>', methods=['POST'])
@login_required
def delete_competitor(competitor_id):
    comp = Competitor.query.get_or_404(competitor_id)
    if comp.user_id != current_user.id:
        return redirect(url_for('competitor.competitors'))
    
    from tubealgo.models import ApiCache
    cache_key = f"competitor_package_v6:{competitor_id}" 
    ApiCache.query.filter_by(cache_key=cache_key).delete()
    
    deleted_position = comp.position
    db.session.delete(comp)
    
    Competitor.query.filter(Competitor.user_id == current_user.id, Competitor.position > deleted_position).update({Competitor.position: Competitor.position - 1})
    db.session.commit()
    flash(f"'{comp.channel_title}' has been removed.", 'success')
    return redirect(url_for('competitor.competitors'))

@competitor_bp.route('/competitors/move/<int:competitor_id>/<direction>', methods=['POST'])
@login_required
def move_competitor(competitor_id, direction):
    comp_to_move = Competitor.query.get_or_404(competitor_id)
    if comp_to_move.user_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    current_pos = comp_to_move.position
    
    if direction == 'up':
        swap_pos = current_pos - 1
    elif direction == 'down':
        swap_pos = current_pos + 1
    else:
        return jsonify({'success': False, 'error': 'Invalid direction'}), 400

    comp_to_swap = Competitor.query.filter_by(user_id=current_user.id, position=swap_pos).first()

    if comp_to_swap:
        comp_to_move.position, comp_to_swap.position = comp_to_swap.position, comp_to_move.position
        db.session.commit()
        return jsonify({'success': True, 'message': 'Position updated.'})
    
    return jsonify({'success': False, 'error': 'Move out of bounds'}), 400

@competitor_bp.route('/discover', methods=['GET', 'POST'])
@login_required
def discover():
    categories = get_youtube_categories()
    top_channels, similar_channels = [], []
    selected_category_id, searched_channel_name = None, ""
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        if form_type == 'category_search':
            selected_category_id = request.form.get('category_id')
            if selected_category_id:
                top_channels = get_top_channels_by_category(selected_category_id)
                if not top_channels: flash('No popular channels found for this category.', 'info')
        elif form_type == 'similar_search':
            searched_channel_name = request.form.get('channel_url')
            if searched_channel_name:
                source_data = analyze_channel(searched_channel_name)
                if 'error' in source_data:
                    flash(source_data['error'], 'error')
                else:
                    similar_channels = find_similar_channels(source_data['id'])
                    if not similar_channels: flash(f"Could not find channels similar to '{source_data['Title']}'.", 'info')
    return render_template('discover.html', categories=categories, top_channels=top_channels, similar_channels=similar_channels, selected_category_id=selected_category_id, searched_channel_name=searched_channel_name, active_page='discover')

@competitor_bp.route('/video/<video_id>/send/telegram')
@login_required
def send_video_to_telegram(video_id):
    if not current_user.telegram_chat_id:
        flash('Please set your Telegram Chat ID in settings first.', 'error')
        return redirect(url_for('analysis.video_analysis', video_id=video_id))
    
    video_info = get_video_info_dict(video_id)
    if 'error' in video_info:
        flash(video_info['error'], 'error')
        return redirect(url_for('analysis.video_analysis', video_id=video_id))
    
    caption = (
        f"📊 *Video Analysis for:* {video_info['title']}\n\n"
        f"👀 Views: *{video_info['views']:,}*\n"
        f"👍 Likes: *{video_info['likes']:,}*\n"
        f"💬 Comments: *{video_info['comments']:,}*\n\n"
        f"[Watch on YouTube](https://youtu.be/{video_info['id']})"
    )
    send_telegram_photo_with_caption(current_user.telegram_chat_id, video_info['thumbnail_url'], caption)
    flash('Analysis has been sent to your Telegram!', 'success')
    return redirect(url_for('analysis.video_analysis', video_id=video_id))

@competitor_bp.route('/api/competitor/add-idea-from-video', methods=['POST'])
@login_required
def add_idea_from_competitor_video():
    try:
        @check_limits(feature='ai_generation')
        def do_generation():
            data = request.json
            title = data.get('title')
            if not title:
                return jsonify({'error': 'Video title is required'}), 400

            ai_result = generate_idea_from_competitor(title)
            if 'error' in ai_result or 'new_title' not in ai_result:
                return jsonify({'error': 'AI could not generate an idea.'}), 500
            
            new_title = ai_result['new_title']

            max_position = db.session.query(db.func.max(ContentIdea.position)).filter_by(user_id=current_user.id, status='idea').scalar() or -1
            
            new_idea = ContentIdea(
                user_id=current_user.id,
                title=new_title,
                display_title=new_title,
                status='idea',
                position=max_position + 1
            )
            db.session.add(new_idea)
            db.session.commit()
            
            return jsonify({'success': True, 'message': f"Idea '{new_title}' added to your planner!"})

        return do_generation()
    except RateLimitExceeded as e:
        return jsonify({'error': str(e)}), 429
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'An unexpected error occurred.'}), 500

@competitor_bp.route('/api/competitor/analyze-transcript/<string:video_id>', methods=['POST'])
@login_required
def analyze_transcript(video_id):
    try:
        @check_limits(feature='ai_generation')
        def do_analysis():
            try:
                transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
                full_transcript = " ".join([item['text'] for item in transcript_list])
            except Exception as e:
                error_message = str(e)
                if "Could not retrieve a transcript for the video" in error_message:
                    error_message = "Transcripts are disabled for this video."
                return jsonify({'error': error_message}), 404
            
            ai_analysis = analyze_transcript_with_ai(full_transcript)
            
            if 'error' in ai_analysis:
                return jsonify({'error': ai_analysis['error']}), 500
            
            return jsonify(ai_analysis)
        
        return do_analysis()
    
    except RateLimitExceeded as e:
        return jsonify({'error': str(e)}), 429
    except Exception as e:
        return jsonify({'error': 'An unexpected server error occurred.'}), 500
