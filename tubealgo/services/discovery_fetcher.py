# tubealgo/services/discovery_fetcher.py

import logging
from collections import Counter
from .youtube_core import get_youtube_service
from .cache_manager import get_from_cache, set_to_cache
from .video_fetcher import get_most_viewed_videos, get_video_details # Note the import change

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
        return []

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
        return {'videos': []}