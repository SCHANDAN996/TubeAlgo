# tubealgo/services/youtube_fetcher.py

import logging
import re
import json
from collections import Counter
from datetime import datetime
import pytz
from .youtube_core import get_youtube_service
from .cache_manager import get_from_cache, set_to_cache
from googleapiclient.errors import HttpError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
    except Exception as e:
        logging.error(f"Error getting uploads playlist ID for {channel_id}: {e}")
        return None

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
    
    for _ in range(10): 
        data = get_latest_videos(channel_id, max_results=50, page_token=next_page_token)
        
        if 'error' in data or not data.get('videos'):
            break

        all_videos.extend(data['videos'])
        next_page_token = data.get('nextPageToken')
        
        if not next_page_token:
            break
            
    set_to_cache(cache_key, all_videos, expire_hours=12)
    return all_videos

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
        logging.error(f"Error fetching playlists for channel {channel_id}: {e}")
        return []

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
        logging.error(f"Error in get_most_viewed_videos for {channel_id}: {e}")
        return {'videos': [], 'nextPageToken': None, 'error': str(e)}

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
        logging.error(f"ERROR in analyze_channel: {e}")
        return {'error': 'An unexpected API error occurred.'}

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
        logging.error(f"Error in get_most_used_tags for channel_id {channel_id}: {e}")
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

def get_youtube_categories(region_code="IN"):
    cache_key = f"youtube_categories_v2:{region_code}"
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data
    youtube, error = get_youtube_service()
    if error: return []
    try:
        response = youtube.videoCategories().list(part="snippet", regionCode=region_code).execute()
        items = response.get("items", [])
        set_to_cache(cache_key, items, expire_hours=168)
        return items
    except Exception as e:
        logging.error(f"Error getting YouTube categories: {e}")
        return []

def get_top_channels_by_category(category_id, region_code="IN"):
    cache_key = f"top_channels_v2:{category_id}:{region_code}"
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data
    youtube, error = get_youtube_service()
    if error: return []
    try:
        video_search = youtube.search().list(part="snippet", type="video", videoCategoryId=category_id, regionCode=region_code, order="viewCount", maxResults=20).execute()
        channel_ids = list(set([item['snippet']['channelId'] for item in video_search.get('items', [])]))
        if not channel_ids: return []
        channel_details = youtube.channels().list(part="snippet,statistics", id=",".join(channel_ids)).execute()
        channels = [
            {'title': item['snippet']['title'], 'channel_id': item['id'],
             'thumbnail': item['snippet']['thumbnails']['default']['url'],
             'subscribers': int(item.get('statistics', {}).get('subscriberCount', 0))}
            for item in channel_details.get("items", [])
        ]
        sorted_channels = sorted(channels, key=lambda x: x['subscribers'], reverse=True)[:10]
        set_to_cache(cache_key, sorted_channels, expire_hours=24)
        return sorted_channels
    except Exception as e:
        logging.error(f"Error getting top channels by category: {e}")
        return []

def find_similar_channels(channel_id):
    cache_key = f"similar_channels_v2:{channel_id}"
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data
    youtube, error = get_youtube_service()
    if error: return []
    try:
        most_viewed_data = get_most_viewed_videos(channel_id, max_results=5)
        most_viewed = most_viewed_data.get('videos', [])
        if not most_viewed: return []
        
        video_ids = [v['id'] for v in most_viewed]
        video_details_list = [get_video_details(vid) for vid in video_ids]
        source_tags = set()
        for detail in video_details_list:
            if detail and 'tags' in detail:
                source_tags.update(detail['tags'])
        if not source_tags: return []
        search_query = " ".join(list(source_tags)[:5])
        search_response = youtube.search().list(part="snippet", q=search_query, type="channel", maxResults=10).execute()
        similar_channels = [
            {'title': item['snippet']['title'], 'channel_id': item['snippet']['channelId'],
             'thumbnail': item['snippet']['thumbnails']['default']['url']}
            for item in search_response.get("items", []) if item['snippet']['channelId'] != channel_id
        ]
        set_to_cache(cache_key, similar_channels, expire_hours=24)
        return similar_channels
    except Exception as e:
        logging.error(f"Error finding similar channels: {e}")
        return []
        
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
        logging.error(f"Error in get_full_video_details for video_id {video_id}: {e}")
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
        if 'quotaExceeded' in str(e): return {'error': 'YouTube API daily limit reached. Please try again tomorrow.'}
        return {'error': f'An unexpected API error occurred: {e}'}
    except Exception as e:
        logging.error(f"Error in get_video_details for video_id {video_id}: {e}")
        return {'error': f'An unexpected error occurred: {e}'}

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
        logging.error(f"Could not determine category for channel {channel_id}: {e}")
        return "N/A"

def search_for_channels(query):
    cache_key = f"search_channels_v2:{query}"
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data
    youtube, error = get_youtube_service()
    if error: return []
    try:
        response = youtube.search().list(part="snippet", q=query, type="channel", maxResults=5).execute()
        channels = [{'title': item['snippet']['title'], 'channel_id': item['snippet']['channelId'], 'thumbnail': item['snippet']['thumbnails']['default']['url']} for item in response.get('items', [])]
        set_to_cache(cache_key, channels, expire_hours=1)
        return channels
    except Exception as e:
        logging.error(f"Error in search_for_channels for query '{query}': {e}")
        return []

def search_videos(query, max_results=3):
    cache_key = f"video_search_v2:{query}:{max_results}"
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data
    youtube, error = get_youtube_service()
    if error: return {'videos': []}
    try:
        response = youtube.search().list(part="snippet", q=query, maxResults=max_results, order="relevance", type="video").execute()
        videos = [{'id': item['id']['videoId']} for item in response.get('items', [])]
        result = {'videos': videos}
        set_to_cache(cache_key, result, expire_hours=24)
        return result
    except Exception as e:
        logging.error(f"Error in search_videos for query '{query}': {e}")
        return {'videos': []}