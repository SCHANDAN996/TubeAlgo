# tubealgo/routes/api_routes.py

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
# === बदलाव यहाँ है: VideoSnapshot और datetime को इम्पोर्ट किया गया ===
from tubealgo.models import Competitor, ChannelSnapshot, VideoSnapshot
from tubealgo.services.cache_manager import get_from_cache, set_to_cache
from tubealgo.services.channel_fetcher import (
    analyze_channel, get_channel_main_category, get_channel_playlists, 
    get_most_used_tags
)
from tubealgo.services.video_fetcher import (
    get_latest_videos, get_most_viewed_videos, get_video_details,
    get_all_channel_videos
)
from tubealgo.services.discovery_fetcher import search_for_channels
import json
from datetime import date, timedelta, datetime, timezone

api_bp = Blueprint('api', __name__, url_prefix='/api')

def get_full_competitor_package(competitor_id, force_refresh=False):
    """
    Fetches ALL data for a competitor, including growth stats and trending status.
    """
    cache_key = f"competitor_package_v6:{competitor_id}" # वर्शन बदला गया
    if not force_refresh:
        cached_data = get_from_cache(cache_key)
        if cached_data:
            return cached_data

    comp = Competitor.query.get_or_404(competitor_id)

    details = analyze_channel(comp.channel_id_youtube)
    if 'error' in details:
        return {'error': details['error']}

    growth_data = { '1d': None, '7d': None }
    
    latest_videos_all = get_all_channel_videos(comp.channel_id_youtube)
    if isinstance(latest_videos_all, dict) and 'error' in latest_videos_all:
         return {'error': latest_videos_all['error']}

    most_viewed_data_api = get_most_viewed_videos(comp.channel_id_youtube, max_results=50)
    most_viewed_videos_all = most_viewed_data_api.get('videos', [])

    all_videos_dict = {}
    for video in (latest_videos_all + most_viewed_videos_all):
        if video and 'id' in video:
            all_videos_dict[video['id']] = video
    
    all_videos_unique = list(all_videos_dict.values())

    # === बदलाव यहाँ से शुरू है: ट्रेंडिंग स्थिति की गणना ===
    for video in all_videos_unique:
        video['trending_status'] = None
        try:
            # वीडियो के लिए नवीनतम दो स्नैपशॉट प्राप्त करें
            snapshots = VideoSnapshot.query.filter_by(video_id=video['id']).order_by(VideoSnapshot.timestamp.desc()).limit(2).all()
            
            if len(snapshots) == 2:
                latest_snapshot = snapshots[0]
                previous_snapshot = snapshots[1]

                views_gained = latest_snapshot.view_count - previous_snapshot.view_count
                time_diff_seconds = (latest_snapshot.timestamp - previous_snapshot.timestamp).total_seconds()

                if time_diff_seconds > 60: # कम से कम एक मिनट का अंतर हो
                    vph = (views_gained / time_diff_seconds) * 3600
                    
                    upload_date = datetime.fromisoformat(video['upload_date'].replace('Z', '+00:00'))
                    days_since_upload = (datetime.now(timezone.utc) - upload_date).days

                    # ट्रेंडिंग के लिए नियम
                    if vph > 1000 and days_since_upload <= 3:
                        video['trending_status'] = '🔥 Trending'
                    elif vph > 500 and days_since_upload <= 7:
                        video['trending_status'] = '🚀 Fast Growing'
        except Exception:
            # कोई त्रुटि होने पर चुपचाप जारी रखें
            continue
    # === बदलाव यहाँ खत्म है ===

    recent_videos_data = {
        'videos': sorted(all_videos_unique, key=lambda x: x.get('upload_date', ''), reverse=True),
        'nextPageToken': None
    }
    
    most_viewed_videos_data = {
        'videos': sorted(all_videos_unique, key=lambda x: x.get('view_count', 0), reverse=True),
        'nextPageToken': None
    }

    playlists = get_channel_playlists(comp.channel_id_youtube)
    top_tags = get_most_used_tags(comp.channel_id_youtube, video_limit=50)
    category = get_channel_main_category(comp.channel_id_youtube)

    final_data = {
        'details': details,
        'growth': growth_data,
        'recent_videos_data': recent_videos_data,
        'most_viewed_videos_data': most_viewed_videos_data,
        'playlists': playlists,
        'top_tags': top_tags,
        'category': category
    }
    
    set_to_cache(cache_key, final_data, expire_hours=4) 
    
    return final_data


@api_bp.route('/competitor/<int:competitor_id>/data')
@login_required
def get_competitor_data(competitor_id):
    comp = Competitor.query.filter_by(id=competitor_id, user_id=current_user.id).first_or_404()
    data_package = get_full_competitor_package(comp.id)
    return jsonify(data_package)


@api_bp.route('/competitor/<int:competitor_id>/refresh', methods=['POST'])
@login_required
def refresh_competitor_data(competitor_id):
    comp = Competitor.query.filter_by(id=competitor_id, user_id=current_user.id).first_or_404()
    fresh_data_package = get_full_competitor_package(comp.id, force_refresh=True)
    return jsonify(fresh_data_package)


@api_bp.route('/search-channels')
@login_required
def api_search_channels():
    query = request.args.get('q', '')
    if len(query) < 2: return jsonify([])
    return jsonify(search_for_channels(query))
    

@api_bp.route('/video-details/<string:video_id>')
@login_required
def api_video_details(video_id):
    details = get_video_details(video_id)
    if 'error' in details: return jsonify({'error': details['error']}), 404
    return jsonify(details)


@api_bp.route('/channel/<string:channel_id>/videos')
@login_required
def get_channel_videos_paginated(channel_id):
    page_token = request.args.get('page_token', None)
    sort_by = request.args.get('sort_by', 'date')

    if sort_by == 'viewCount':
        data = get_most_viewed_videos(channel_id, max_results=20, page_token=page_token)
    else:
        data = get_latest_videos(channel_id, max_results=20, page_token=page_token)

    return jsonify(data)