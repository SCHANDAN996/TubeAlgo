# tubealgo/services/video_fetcher.py

import json
import logging
from googleapiclient.errors import HttpError
from .youtube_core import get_youtube_service
from .cache_manager import get_from_cache, set_to_cache
from .fetcher_utils import _create_video_objects, _get_uploads_playlist_id

def get_latest_videos(channel_id, max_results=20, page_token=None):
    uploads_playlist_id = _get_uploads_playlist_id(channel_id)
    if not uploads_playlist_id: return {'videos': [], 'nextPageToken': None}

    cache_key = f"playlist_videos_v7:{uploads_playlist_id}:{max_results}:{page_token or 'first'}"
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data

    youtube, error = get_youtube_service()
    if error: return {'videos': [], 'nextPageToken': None, 'error': error}

    try:
        playlist_items_request = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=max_results,
            pageToken=page_token
        )
        playlist_response = playlist_items_request.execute()
        next_page_token = playlist_response.get('nextPageToken')

        video_ids = [item['contentDetails']['videoId'] for item in playlist_response.get('items', []) if 'videoId' in item.get('contentDetails', {})]
        if not video_ids: return {'videos': [], 'nextPageToken': None}
            
        video_details_response = youtube.videos().list(part="snippet,statistics,contentDetails", id=",".join(video_ids)).execute()
        
        videos = _create_video_objects(video_details_response.get('items', []))
        
        result = {'videos': videos, 'nextPageToken': next_page_token}
        set_to_cache(cache_key, result, expire_hours=4)
        return result
    
    except HttpError as e:
        try:
            error_details = json.loads(e.content.decode())
            if e.resp.status == 404 and error_details.get("error", {}).get("errors", [{}])[0].get("reason") == "playlistNotFound":
                return {'videos': [], 'nextPageToken': None}
            else:
                return {'videos': [], 'nextPageToken': None, 'error': str(e)}
        except (json.JSONDecodeError, IndexError, KeyError):
            return {'videos': [], 'nextPageToken': None, 'error': str(e)}
    
    except Exception as e:
        return {'videos': [], 'nextPageToken': None, 'error': str(e)}

def get_all_channel_videos(channel_id):
    cache_key = f"all_videos_v2:{channel_id}"
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data

    all_videos = []
    next_page_token = None
    
    for _ in range(10): # Limit to 500 videos (10 pages * 50 results) to prevent excessive API usage
        data = get_latest_videos(channel_id, max_results=50, page_token=next_page_token)
        
        if 'error' in data or not data.get('videos'):
            break

        all_videos.extend(data['videos'])
        next_page_token = data.get('nextPageToken')
        
        if not next_page_token:
            break
            
    set_to_cache(cache_key, all_videos, expire_hours=12)
    return all_videos

def get_most_viewed_videos(channel_id, max_results=20, page_token=None):
    cache_key = f"most_viewed_v6:{channel_id}:{max_results}:{page_token or 'first'}"
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data
    
    youtube, error = get_youtube_service()
    if error: return {'videos': [], 'nextPageToken': None, 'error': error}

    try:
        search_request = youtube.search().list(part="snippet", channelId=channel_id, maxResults=max_results, order="viewCount", type="video", pageToken=page_token)
        search_response = search_request.execute()
        next_page_token = search_response.get('nextPageToken')

        video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]
        if not video_ids: return {'videos': [], 'nextPageToken': None}

        video_details_response = youtube.videos().list(part="snippet,statistics,contentDetails", id=",".join(video_ids)).execute()
        
        videos = _create_video_objects(video_details_response.get('items', []))

        result = {'videos': videos, 'nextPageToken': next_page_token}
        set_to_cache(cache_key, result, expire_hours=24)
        return result
    except Exception as e:
        return {'videos': [], 'nextPageToken': None, 'error': str(e)}

def get_full_video_details(video_id):
    cache_key = f"full_video_details_v3:{video_id}"
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data
    youtube, error = get_youtube_service()
    if error: return {'error': str(error)}
    try:
        video_response = youtube.videos().list(part="snippet,statistics,contentDetails", id=video_id).execute()
        if not video_response.get('items'): return {'error': 'Video not found.'}
        video_data = video_response['items'][0]
        comments = []
        try:
            comment_response = youtube.commentThreads().list(part="snippet", videoId=video_id, maxResults=50, order="relevance").execute()
            comments = [item["snippet"]["topLevelComment"]["snippet"]["textDisplay"] for item in comment_response.get("items", [])]
        except HttpError as e:
            logging.warning(f"Could not fetch comments for video {video_id}: {e.reason}")
            comments = []
        except Exception:
            comments = []
        
        video_data['comments_retrieved'] = comments
        set_to_cache(cache_key, video_data, expire_hours=24)
        return video_data
    except Exception as e:
        return {'error': f'An unexpected error occurred: {e}'}

def get_video_details(video_id):
    cache_key = f"video_details_v3:{video_id}"
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data
    youtube, error = get_youtube_service()
    if error: return {'error': str(error)}
    try:
        response = youtube.videos().list(part="snippet,statistics", id=video_id).execute()
        if not response.get('items'): return {'error': 'Video not found.'}
        video_data = response['items'][0]
        snippet, stats = video_data.get('snippet', {}), video_data.get('statistics', {})
        details = {
            'title': snippet.get('title'), 'description': snippet.get('description'),
            'tags': snippet.get('tags', []), 'view_count': int(stats.get('viewCount', 0)),
            'like_count': int(stats.get('likeCount', 0)), 'comment_count': int(stats.get('commentCount', 0))
        }
        set_to_cache(cache_key, details, expire_hours=24)
        return details
    except HttpError as e:
        if 'quotaExceeded' in str(e): return {'error': 'YouTube API daily limit reached.'}
        return {'error': f'An unexpected API error occurred: {e}'}
    except Exception as e:
        return {'error': f'An unexpected error occurred: {e}'}

def get_trending_videos(region_code="IN", max_results=5):
    """Fetches the most popular/trending videos for a given region."""
    cache_key = f"trending_videos:{region_code}:{max_results}"
    cached_data = get_from_cache(cache_key)
    if cached_data:
        return cached_data

    youtube, error = get_youtube_service()
    if error:
        return {'error': error}

    try:
        request = youtube.videos().list(
            part="snippet,statistics",
            chart="mostPopular",
            regionCode=region_code,
            maxResults=max_results
        )
        response = request.execute()
        
        videos = []
        for item in response.get('items', []):
            videos.append({
                'id': item.get('id'),
                'title': item.get('snippet', {}).get('title'),
                'thumbnail': item.get('snippet', {}).get('thumbnails', {}).get('medium', {}).get('url'),
                'channel_title': item.get('snippet', {}).get('channelTitle')
            })

        set_to_cache(cache_key, videos, expire_hours=6) # 6 घंटे के लिए कैश करें
        return videos
    except Exception as e:
        return {'error': str(e)}