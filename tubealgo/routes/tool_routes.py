# tubealgo/routes/tool_routes.py

from flask import render_template, request, flash, Blueprint, jsonify, redirect, url_for
from flask_login import login_required, current_user
# === 1. FlaskForm को यहाँ इम्पोर्ट करें ===
from flask_wtf import FlaskForm
from tubealgo import db
from tubealgo.models import SearchHistory
from tubealgo.services.suggestion_service import get_keyword_suggestions
from tubealgo.services.ai_service import generate_titles_and_tags, generate_description, generate_script_outline
from tubealgo.services.youtube_core import get_youtube_service
from tubealgo.services.video_fetcher import get_trending_videos
from collections import Counter
from tubealgo.decorators import check_limits, RateLimitExceeded
import re
from youtube_transcript_api import YouTubeTranscriptApi
from pytrends.request import TrendReq
from tubealgo.services.cache_manager import get_from_cache, set_to_cache


tool_bp = Blueprint('tool', __name__)

def extract_video_id(url):
    # ... (यह फ़ंक्शन जैसा है वैसा ही रहेगा) ...
    patterns = [
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})',
        r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([a-zA-Z0-9_-]{11})',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/live\/([a-zA-Z0-9_-]{11})',
        r'^[a-zA-Z0-9_-]{11}$'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

@tool_bp.route('/video-analyzer', methods=['GET', 'POST'])
@login_required
def video_analyzer():
    # === यह 'video_analyzer' फ़ंक्शन है जिसे हमने पहले ठीक किया था ===
    form = FlaskForm() 

    if request.method == 'POST':
        video_url = request.form.get('video_url')
        if not video_url:
            flash('Please enter a YouTube video URL or ID.', 'error')
            return render_template('video_analyzer_tool.html', active_page='video_analyzer', form=form)
            
        video_id = extract_video_id(video_url)
        
        if not video_id:
            flash('Invalid YouTube URL or Video ID provided.', 'error')
            return render_template('video_analyzer_tool.html', active_page='video_analyzer', form=form)
            
        return redirect(url_for('analysis.video_analysis', video_id=video_id))
        
    return render_template('video_analyzer_tool.html', active_page='video_analyzer', form=form)

@tool_bp.route('/keyword-research', methods=['GET', 'POST'])
@login_required
def keyword_research():
    # === 2. 'keyword_research' फ़ंक्शन के लिए एक फॉर्म ऑब्जेक्ट बनाएँ ===
    form = FlaskForm()

    if request.method == 'POST':
        try:
            @check_limits(feature='keyword_search')
            def do_search():
                keyword_in = request.form.get('keyword', '').strip()
                if not keyword_in:
                    flash("Please enter a keyword to search.", "error")
                    # === 3. redirect को render_template से बदलें और form पास करें ===
                    return render_template(
                        'keyword_tool.html', 
                        form=form, 
                        keyword=None,
                        recent_searches=db.session.query(SearchHistory.topic).filter_by(user_id=current_user.id).distinct().order_by(SearchHistory.timestamp.desc()).limit(7).all(),
                        trending_videos=get_trending_videos(),
                        active_page='keyword_research'
                    )

                # ... (डेटाबेस और API कॉल्स) ...
                new_search = SearchHistory(user_id=current_user.id, topic=keyword_in)
                db.session.add(new_search)
                db.session.commit()
                suggestions = get_keyword_suggestions(keyword_in)
                top_video_tags = []
                top_ranking_videos = []
                competition_score = {"score": "N/A", "text": "Could not determine.", "color": "text-gray-500"}
                try:
                    youtube, error = get_youtube_service()
                    if error:
                        flash(f"API Error: {error}", "error")
                    else:
                        search_response = youtube.search().list(q=keyword_in, part='id', type='video', maxResults=5, order='relevance').execute()
                        video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]
                        if video_ids:
                            videos_response = youtube.videos().list(part='snippet,statistics,contentDetails', id=','.join(video_ids)).execute()
                            all_tags = []
                            total_views = 0
                            high_view_count_videos = 0
                            for item in videos_response.get('items', []):
                                stats = item.get('statistics', {})
                                view_count = int(stats.get('viewCount', 0))
                                total_views += view_count
                                if view_count > 500000:
                                    high_view_count_videos += 1
                                top_ranking_videos.append({
                                    'id': item.get('id'),
                                    'title': item.get('snippet', {}).get('title'),
                                    'thumbnail': item.get('snippet', {}).get('thumbnails', {}).get('medium', {}).get('url'),
                                    'channel_title': item.get('snippet', {}).get('channelTitle'),
                                    'view_count': view_count,
                                    'published_at': item.get('snippet', {}).get('publishedAt')
                                })
                                tags = item.get('snippet', {}).get('tags', [])
                                if tags:
                                    all_tags.extend(tags)
                            if total_views > 2000000 and high_view_count_videos >= 2:
                                competition_score = {"score": "High", "text": "Very competitive. Dominated by high-view videos.", "color": "text-red-500"}
                            elif total_views > 500000 or high_view_count_videos >= 1:
                                competition_score = {"score": "Medium", "text": "Moderately competitive. Opportunity exists.", "color": "text-yellow-500"}
                            else:
                                competition_score = {"score": "Low", "text": "Less competitive. Good opportunity to rank!", "color": "text-green-500"}
                            if all_tags:
                                tag_counts = Counter(all_tags)
                                top_video_tags = tag_counts.most_common(30)
                except Exception as e:
                    flash(f"Could not fetch complete YouTube data: {e}", "error")

                # === 4. फॉर्म ऑब्जेक्ट को यहाँ भी पास करें ===
                return render_template(
                    'keyword_tool.html', 
                    form=form,
                    keyword=keyword_in, 
                    suggestions=suggestions,
                    top_video_tags=top_video_tags,
                    top_ranking_videos=top_ranking_videos,
                    competition_score=competition_score,
                    active_page='keyword_research'
                )
            return do_search()
        except RateLimitExceeded as e:
            flash(str(e), 'error')
            return redirect(url_for('core.pricing'))
    
    # === 5. GET रिक्वेस्ट के लिए फॉर्म पास करें ===
    recent_searches_query = db.session.query(SearchHistory.topic).filter_by(user_id=current_user.id).distinct().order_by(SearchHistory.timestamp.desc()).limit(7).all()
    recent_searches = [item.topic for item in recent_searches_query]
    trending_videos = get_trending_videos()

    return render_template(
        'keyword_tool.html', 
        form=form,
        keyword=None, 
        recent_searches=recent_searches, 
        trending_videos=trending_videos,
        active_page='keyword_research'
    )

# ... (बाकी के फ़ंक्शंस) ...
@tool_bp.route('/api/keyword-suggestions')
@login_required
def api_keyword_suggestions():
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    return jsonify(get_keyword_suggestions(query))

@tool_bp.route('/ai-generator', methods=['GET', 'POST'])
@login_required
def ai_generator():
    if request.method == 'POST':
        try:
            @check_limits(feature='ai_generation')
            def do_generation():
                if not request.is_json:
                    return jsonify({'error': 'Invalid request format. Must be JSON.'}), 400
                
                data = request.get_json()
                topic_in = data.get('topic', '')

                if not topic_in:
                    return jsonify({'error': 'Topic is required.'}), 400

                new_search = SearchHistory(user_id=current_user.id, topic=topic_in)
                db.session.add(new_search)
                db.session.commit()
                
                results = generate_titles_and_tags(current_user, topic_in)
                if isinstance(results, dict) and 'error' in results:
                    return jsonify({'error': results['error']}), 500
                
                return jsonify(results)
            return do_generation()
        except RateLimitExceeded as e:
            return jsonify({'error': str(e), 'details': str(e)}), 429

    return render_template('ai_generator.html', topic="", results=None, active_page='ai_generator')

@tool_bp.route('/api/generate-description', methods=['POST'])
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

@tool_bp.route('/api/generate-script', methods=['POST'])
@login_required
def api_generate_script():
    try:
        @check_limits(feature='ai_generation')
        def do_api_generation():
            data = request.json
            topic = data.get('topic')
            title = data.get('title')
            language = data.get('language', 'English')
            
            if not topic or not title:
                return jsonify({'error': 'Topic and title are required for context.'}), 400
            
            result = generate_script_outline(title, language)
            return jsonify(result)
        return do_api_generation()
    except RateLimitExceeded as e:
        return jsonify({'error': str(e), 'details': str(e)}), 429

@tool_bp.route('/api/get-transcript/<string:video_id>')
@login_required
def get_transcript(video_id):
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        full_transcript = " ".join([item['text'] for item in transcript_list])
        return jsonify({'success': True, 'transcript': full_transcript})
    except Exception as e:
        error_message = str(e)
        if "Could not retrieve a transcript for the video" in error_message:
            error_message = "Transcripts are disabled for this video."
        return jsonify({'success': False, 'error': error_message}), 404

@tool_bp.route('/api/get-trend/<string:keyword>')
@login_required
def get_google_trend(keyword):
    cache_key = f"google_trend:{keyword}"
    cached_data = get_from_cache(cache_key)
    if cached_data:
        return jsonify(cached_data)

    try:
        pytrends = TrendReq(hl='en-US', tz=330, timeout=(10, 30))
        
        pytrends.build_payload([keyword], cat=0, timeframe='today 12-m', geo='', gprop='youtube')
        
        interest_over_time_df = pytrends.interest_over_time()

        if interest_over_time_df.empty:
            return jsonify({'error': 'Not enough data for this keyword.'}), 404
            
        trend_data = {
            'labels': interest_over_time_df.index.strftime('%b %Y').tolist(),
            'data': interest_over_time_df[keyword].tolist()
        }
        
        set_to_cache(cache_key, trend_data, expire_hours=12)
        
        return jsonify(trend_data)
    except Exception as e:
        return jsonify({'error': f'Could not fetch trend data: {str(e)}'}), 500

