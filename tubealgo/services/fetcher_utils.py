# tubealgo/services/fetcher_utils.py

import re
from .cache_manager import get_from_cache, set_to_cache
from .youtube_core import get_youtube_service

def parse_iso_duration(duration_str):
    if not duration_str:
        return 0
    
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match:
        return 0
    
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds

def _create_video_objects(video_items):
    videos = []
    for item in video_items:
        snippet, stats, content = item.get('snippet', {}), item.get('statistics', {}), item.get('contentDetails', {})
        view_count = int(stats.get('viewCount', 0))
        like_count = int(stats.get('likeCount', 0))
        comment_count = int(stats.get('commentCount', 0))
        duration_seconds = parse_iso_duration(content.get('duration'))
        
        videos.append({
            'id': item.get('id'),
            'title': snippet.get('title'),
            'thumbnail': snippet.get('thumbnails', {}).get('medium', {}).get('url'),
            'view_count': view_count,
            'like_count': like_count,
            'comment_count': comment_count,
            'upload_date': snippet.get('publishedAt'),
            'duration_seconds': duration_seconds,
            'is_short': 0 < duration_seconds <= 61,
        })
    return videos

def _get_uploads_playlist_id(channel_id):
    """Helper to get the special 'uploads' playlist ID for a channel."""
    cache_key = f"uploads_playlist_id:{channel_id}"
    cached_id = get_from_cache(cache_key)
    if cached_id:
        return cached_id

    youtube, error = get_youtube_service()
    if error:
        return None

    try:
        response = youtube.channels().list(part="contentDetails", id=channel_id).execute()
        if not response.get('items'):
            return None
        playlist_id = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        set_to_cache(cache_key, playlist_id, expire_hours=168)
        return playlist_id
    except Exception:
        return None