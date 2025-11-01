# tubealgo/services/channel_fetcher.py

import re
import logging
from collections import Counter
from datetime import datetime
import pytz
from .youtube_core import get_youtube_service
from .cache_manager import get_from_cache, set_to_cache
from .video_fetcher import get_latest_videos, get_all_channel_videos # Note the import change
from .discovery_fetcher import get_youtube_categories # Note the import change

def analyze_channel(channel_input):
    youtube, error = get_youtube_service()
    if error: return {'error': error}

    channel_id = None
    
    try:
        patterns = [
            r'(UC[a-zA-Z0-9_-]{22})', 
            r'/@([a-zA-Z0-9_.-]+)', 
            r'/channel/(UC[a-zA-Z0-9_-]{22})'
        ]
        
        found_id = None
        for pattern in patterns:
            match = re.search(pattern, channel_input)
            if match:
                found_id = match.group(1)
                break
        
        if found_id and found_id.startswith('UC'):
            channel_id = found_id
        elif found_id: 
            search_response = youtube.search().list(q=found_id, part='snippet', type='channel', maxResults=1).execute()
            if search_response.get('items'):
                channel_id = search_response['items'][0]['id']['channelId']
        else: 
            search_response = youtube.search().list(q=channel_input, part='snippet', type='channel', maxResults=1).execute()
            if search_response.get('items'):
                channel_id = search_response['items'][0]['id']['channelId']

        if not channel_id:
            return {'error': f"No channel found for '{channel_input}'."}
        
        cache_key = f"channel_analysis_v6:{channel_id}"
        
        cached_data = get_from_cache(cache_key)
        if cached_data:
            return cached_data
        
        final_response = youtube.channels().list(part="snippet,statistics,brandingSettings", id=channel_id).execute()
        if not final_response.get('items'):
            return {'error': f"Could not fetch data for channel ID '{channel_id}'."}
        
        channel = final_response['items'][0]
        stats, snippet, branding = channel.get('statistics', {}), channel.get('snippet', {}), channel.get('brandingSettings', {})
        
        keywords_str = branding.get('channel', {}).get('keywords', '')
        keywords_list = [tag.strip() for tag in re.split(r'[\s,]+', keywords_str) if tag.strip()]

        result = {
            'id': channel.get('id'), 'Title': snippet.get('title', 'N/A'),
            'Description': snippet.get('description', ''), 'Subscribers': int(stats.get('subscriberCount', 0)),
            'Total Views': int(stats.get('viewCount', 0)), 'Video Count': int(stats.get('videoCount', 0)),
            'Thumbnail URL': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
            'publishedAt': snippet.get('publishedAt'),
            'keywords': keywords_list
        }
        set_to_cache(cache_key, result, expire_hours=24)
        return result

    except Exception as e:
        return {'error': 'An unexpected API error occurred.'}

def get_channel_playlists(channel_id, max_results=25):
    cache_key = f"channel_playlists_v1:{channel_id}:{max_results}"
    cached_data = get_from_cache(cache_key)
    if cached_data:
        return cached_data

    youtube, error = get_youtube_service()
    if error: return []

    try:
        request = youtube.playlists().list(part="snippet,contentDetails", channelId=channel_id, maxResults=max_results)
        response = request.execute()
        
        playlists = [
            {'id': item.get('id'), 'title': item.get('snippet', {}).get('title'),
             'description': item.get('snippet', {}).get('description'),
             'thumbnail': item.get('snippet', {}).get('thumbnails', {}).get('medium', {}).get('url'),
             'video_count': item.get('contentDetails', {}).get('itemCount', 0),
             'published_at': item.get('snippet', {}).get('publishedAt')}
            for item in response.get('items', [])
        ]
        
        set_to_cache(cache_key, playlists, expire_hours=24)
        return playlists
    except Exception as e:
        return []

def get_most_used_tags(channel_id, video_limit=50):
    cache_key = f"most_used_tags_v2:{channel_id}:{video_limit}"
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data
    
    video_data = get_latest_videos(channel_id, max_results=video_limit)
    if not video_data or not video_data.get('videos'): return []

    video_ids = [video['id'] for video in video_data['videos'] if video and 'id' in video]
    if not video_ids: return []
    
    youtube, error = get_youtube_service()
    if error: return []

    all_tags = []
    try:
        for i in range(0, len(video_ids), 50):
            batch_ids = video_ids[i:i+50]
            videos_response = youtube.videos().list(part="snippet", id=",".join(batch_ids)).execute()
            for item in videos_response.get('items', []):
                if 'tags' in item['snippet']:
                    all_tags.extend(item['snippet']['tags'])
        
        if not all_tags: return []
        tag_counts = Counter(all_tags)
        most_common_tags = tag_counts.most_common(20)
        set_to_cache(cache_key, most_common_tags, expire_hours=24)
        return most_common_tags
    except Exception as e:
        return []

def get_upload_schedule_analysis(channel_id):
    cache_key = f"upload_schedule_v3_ist:{channel_id}"
    cached_data = get_from_cache(cache_key)
    if cached_data:
        return cached_data

    all_videos = get_all_channel_videos(channel_id)
    if not all_videos or ('error' in all_videos and not isinstance(all_videos, list)):
        return {'by_day': [0]*7, 'by_hour': [0]*24}

    uploads_by_day = [0] * 7
    uploads_by_hour = [0] * 24
    
    ist = pytz.timezone('Asia/Kolkata')

    for video in all_videos:
        try:
            upload_date_utc = datetime.fromisoformat(video['upload_date'].replace('Z', '+00:00'))
            upload_date_ist = upload_date_utc.astimezone(ist)
            
            day_of_week = upload_date_ist.weekday()
            hour_of_day = upload_date_ist.hour
            uploads_by_day[day_of_week] += 1
            uploads_by_hour[hour_of_day] += 1
        except (ValueError, TypeError):
            continue
            
    result = {'by_day': uploads_by_day, 'by_hour': uploads_by_hour}
    set_to_cache(cache_key, result, expire_hours=24)
    return result

def get_channel_main_category(channel_id):
    cache_key = f"channel_category_v3:{channel_id}"
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data
    youtube, error = get_youtube_service()
    if error: return "N/A"
    try:
        search_response = youtube.search().list(part="snippet", channelId=channel_id, order="viewCount", type="video", maxResults=50).execute()
        video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]
        if not video_ids: return "N/A"
        
        videos_response = youtube.videos().list(part="snippet", id=",".join(video_ids)).execute()
        category_ids = [item['snippet']['categoryId'] for item in videos_response.get('items', []) if 'categoryId' in item['snippet']]
        if not category_ids: return "N/A"
        
        most_common_id = Counter(category_ids).most_common(1)[0][0]
        
        all_categories = get_youtube_categories()
        category_name = next((cat['snippet']['title'] for cat in all_categories if cat['id'] == most_common_id), "N/A")
        
        set_to_cache(cache_key, category_name, expire_hours=24)
        return category_name
    except Exception as e:
        return "N/A"