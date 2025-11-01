# tubealgo/services/youtube_manager.py

import os
import logging
import re
import mimetypes
from datetime import timedelta, datetime
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
import json
import pytz

from ..services.cache_manager import get_from_cache, set_to_cache
from ..services.fetcher_utils import _get_uploads_playlist_id
from ..services.video_fetcher import get_latest_videos as get_videos_by_channel_id
from ..models import log_system_event

logging.basicConfig(level=logging.INFO)

def _handle_quota_error(e, user_id):
    """A helper function to specifically log project-level quota errors."""
    error_str = str(e).lower()
    if "quotaexceeded" in error_str or "quota" in error_str:
        log_system_event(
            message="Overall project quota exhausted by a user credential call.",
            log_type='PROJECT_QUOTA_EXCEEDED',
            details={'user_id': user_id, 'error': str(e)}
        )
        return {'error': 'YouTube API project quota exceeded.'}
    return {'error': str(e)}

def _get_user_id_from_creds(credentials):
    """Helper to find a user ID from a credentials object to log errors correctly."""
    from ..models import User
    user = User.query.filter_by(google_access_token=credentials.token).first()
    return user.id if user else 'unknown'

def _parse_duration(duration_str):
    if not duration_str: return 0
    duration_regex = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
    parts = duration_regex.match(duration_str)
    if not parts: return 0
    parts = parts.groups()
    time_params = {name: int(value) for name, value in zip(["hours", "minutes", "seconds"], parts) if value}
    return timedelta(**time_params).total_seconds()

def get_user_videos(user, credentials):
    cache_key = f"user_videos_list_v2:{user.id}"
    cached_videos = get_from_cache(cache_key)
    if cached_videos:
        return cached_videos

    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        if not user.channel or not user.channel.channel_id_youtube: 
            return []
            
        uploads_playlist_id = _get_uploads_playlist_id(user.channel.channel_id_youtube)
        if not uploads_playlist_id: 
            return []

        playlist_items_request = youtube.playlistItems().list(part="contentDetails", playlistId=uploads_playlist_id, maxResults=50)
        playlist_response = playlist_items_request.execute()
        
        video_ids = [item['contentDetails']['videoId'] for item in playlist_response.get('items', []) if 'videoId' in item.get('contentDetails', {})]
        if not video_ids: 
            return []

        details_request = youtube.videos().list(part="snippet,statistics,contentDetails,status", id=",".join(video_ids))
        details_response = details_request.execute()
        
        videos = []
        for item in details_response.get('items', []):
            duration_seconds = _parse_duration(item.get('contentDetails', {}).get('duration'))
            videos.append({
                'id': item.get('id'), 'title': item.get('snippet', {}).get('title'),
                'thumbnail': item.get('snippet', {}).get('thumbnails', {}).get('medium', {}).get('url'),
                'published_at': item.get('snippet', {}).get('publishedAt'),
                'view_count': int(item.get('statistics', {}).get('viewCount', 0)),
                'like_count': int(item.get('statistics', {}).get('likeCount', 0)),
                'comment_count': int(item.get('statistics', {}).get('commentCount', 0)),
                'is_short': 0 < duration_seconds <= 61,
                'privacy_status': item.get('status', {}).get('privacyStatus')
            })
        videos.sort(key=lambda x: x.get('published_at', ''), reverse=True)
        set_to_cache(cache_key, videos, expire_hours=1)
        return videos
    except HttpError as e:
        logging.error(f"Could not fetch user videos for user {user.id}: {e}")
        return _handle_quota_error(e, user.id)
    except Exception as e:
        logging.error(f"Could not fetch user videos for user {user.id}: {e}")
        return {'error': str(e)}

def get_user_playlists(credentials):
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        playlists_request = youtube.playlists().list(
            part="snippet,contentDetails,status",
            mine=True,
            maxResults=50
        )
        playlists_response = playlists_request.execute()
        playlists = []
        for item in playlists_response.get('items', []):
            playlists.append({
                'id': item.get('id'), 'title': item.get('snippet', {}).get('title'),
                'description': item.get('snippet', {}).get('description'),
                'thumbnail': item.get('snippet', {}).get('thumbnails', {}).get('medium', {}).get('url'),
                'published_at': item.get('snippet', {}).get('publishedAt'),
                'video_count': item.get('contentDetails', {}).get('itemCount', 0),
                'privacy_status': item.get('status', {}).get('privacyStatus')
            })
        return playlists
    except HttpError as e:
        user_id = _get_user_id_from_creds(credentials)
        logging.error(f"Could not fetch user playlists for user {user_id}: {e}")
        return _handle_quota_error(e, user_id)
    except Exception as e:
        logging.error(f"Could not fetch user playlists: {e}")
        return {'error': str(e)}

def get_competitors_playlists(user):
    from ..models import Competitor
    competitors = user.competitors.all()
    if not competitors:
        return []

    all_video_titles = []
    for comp in competitors:
        try:
            video_data = get_videos_by_channel_id(comp.channel_id_youtube, max_results=10)
            if 'error' in video_data:
                logging.error(f"Could not fetch videos for competitor {comp.channel_title}: {video_data['error']}")
                return {'error': f"Could not fetch videos for competitor {comp.channel_title}. YouTube API quota may be exceeded."}
            videos = video_data.get('videos', [])
            for video in videos:
                if 'title' in video:
                    all_video_titles.append(video['title'])
        except Exception as e:
            logging.error(f"An unexpected error occurred while fetching data for competitor {comp.channel_id_youtube}: {e}")
            continue
    return list(set(all_video_titles))

def get_single_video(credentials, video_id):
    user_id = _get_user_id_from_creds(credentials)
    cache_key = f"single_video_details:{video_id}"
    cached_data = get_from_cache(cache_key)
    if cached_data:
        return cached_data
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        request = youtube.videos().list(part="snippet,status,contentDetails", id=video_id)
        response = request.execute()
        if not response.get('items'):
            return {'error': 'Video not found or you do not have permission to view it.'}
        video_data = response['items'][0]
        set_to_cache(cache_key, video_data, expire_hours=1)
        return video_data
    except HttpError as e:
        logging.error(f"Could not fetch single video {video_id}: {e}")
        return _handle_quota_error(e, user_id)
    except Exception as e:
        logging.error(f"Could not fetch single video {video_id}: {e}")
        return {'error': str(e)}

def get_single_playlist(credentials, playlist_id):
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        request = youtube.playlists().list(part="snippet,status", id=playlist_id)
        response = request.execute()
        if not response.get('items'):
            return {'error': 'Playlist not found or you do not have permission to view it.'}
        return response['items'][0]
    except HttpError as e:
        user_id = _get_user_id_from_creds(credentials)
        logging.error(f"Could not fetch single playlist {playlist_id}: {e}")
        return _handle_quota_error(e, user_id)
    except Exception as e:
        logging.error(f"Could not fetch single playlist {playlist_id}: {e}")
        return {'error': str(e)}

def create_playlist(credentials, title, description, privacy_status):
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        body = {
            "snippet": { "title": title, "description": description },
            "status": { "privacyStatus": privacy_status }
        }
        request = youtube.playlists().insert(part="snippet,status", body=body)
        response = request.execute()
        return response
    except HttpError as e:
        user_id = _get_user_id_from_creds(credentials)
        logging.error(f"Could not create playlist: {e}")
        return _handle_quota_error(e, user_id)
    except Exception as e:
        logging.error(f"Could not create playlist: {e}")
        return {'error': str(e)}

def update_playlist(credentials, playlist_id, title, description, privacy_status):
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        playlist_response = youtube.playlists().list(part='snippet,status', id=playlist_id).execute()
        if not playlist_response.get('items'):
            return {'error': 'Playlist not found.'}
        playlist = playlist_response['items'][0]
        playlist['snippet']['title'] = title
        playlist['snippet']['description'] = description
        playlist['status']['privacyStatus'] = privacy_status
        request = youtube.playlists().update(part="snippet,status", body=playlist)
        response = request.execute()
        return response
    except HttpError as e:
        user_id = _get_user_id_from_creds(credentials)
        logging.error(f"Could not update playlist {playlist_id}: {e}")
        return _handle_quota_error(e, user_id)
    except Exception as e:
        logging.error(f"Could not update playlist {playlist_id}: {e}")
        return {'error': str(e)}

def update_video_details(credentials, video_id, title, description, tags, privacy_status, publish_at=None):
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        video_response = youtube.videos().list(part='snippet,status', id=video_id).execute()
        if not video_response.get('items'): return {'error': 'Video not found.'}
        video = video_response['items'][0]
        video['snippet']['title'] = title
        video['snippet']['description'] = description
        video['snippet']['tags'] = tags
        video['status']['privacyStatus'] = privacy_status
        if publish_at:
            video['status']['publishAt'] = publish_at.isoformat(timespec='seconds') + "Z"
        else:
            video['status'].pop('publishAt', None)
        request = youtube.videos().update(part="snippet,status", body=video)
        response = request.execute()
        return response
    except HttpError as e:
        user_id = _get_user_id_from_creds(credentials)
        logging.error(f"Could not update video {video_id}: {e}")
        return _handle_quota_error(e, user_id)
    except Exception as e:
        logging.error(f"Could not update video {video_id}: {e}")
        return {'error': str(e)}

def upload_video(credentials, video_filepath, metadata):
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        body = {
            "snippet": {
                "title": metadata.get('title'), "description": metadata.get('description'),
                "tags": metadata.get('tags', []), "categoryId": metadata.get('category_id', '22')
            },
            "status": { "privacyStatus": metadata.get('privacy_status', 'private') }
        }
        if metadata.get('publish_at'):
            body['status']['publishAt'] = metadata['publish_at'].isoformat(timespec='seconds') + "Z"
        media_body = MediaFileUpload(video_filepath, chunksize=-1, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media_body)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logging.info(f"Uploaded {int(status.progress() * 100)}%.")
        return response
    except HttpError as e:
        user_id = _get_user_id_from_creds(credentials)
        logging.error(f"Could not upload video from path {video_filepath}: {e}")
        return _handle_quota_error(e, user_id)
    except Exception as e:
        logging.error(f"Could not upload video from path {video_filepath}: {e}")
        return {'error': str(e)}

def set_video_thumbnail(credentials, video_id, image_filepath):
    try:
        youtube = build('youtube', 'v3', credentials=credentials)
        mimetype, _ = mimetypes.guess_type(image_filepath)
        with open(image_filepath, 'rb') as file_handle:
            media_body = MediaIoBaseUpload(file_handle, mimetype=mimetype, resumable=True)
            request = youtube.thumbnails().set(videoId=video_id, media_body=media_body)
            response = request.execute()
        return response
    except HttpError as e:
        user_id = _get_user_id_from_creds(credentials)
        logging.error(f"Could not set thumbnail for video {video_id}: {e}")
        return _handle_quota_error(e, user_id)
    except Exception as e:
        logging.error(f"Could not set thumbnail for video {video_id}: {e}")
        return {'error': str(e)}