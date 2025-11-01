# tubealgo/routes/utils.py

import re
from datetime import datetime
from tubealgo.services.video_fetcher import get_full_video_details
from tubealgo.services.channel_fetcher import get_most_used_tags as fetcher_get_most_used_tags
from flask_login import current_user
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from tubealgo import db
from tubealgo.models import get_config_value

# Define all possible scopes that the credentials might need
ALL_SCOPES = [
    'https://www.googleapis.com/auth/userinfo.email', 
    'https://www.googleapis.com/auth/userinfo.profile', 
    'openid',
    'https://www.googleapis.com/auth/youtube', 
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/yt-analytics.readonly'
]

# --- यहाँ बदलाव किया गया है ---
def get_credentials(user=None):
    """
    Gets valid Google credentials for a given user or the current user.
    Handles token refresh automatically using the database.
    """
    # यदि कोई यूज़र पास नहीं किया गया है, तो current_user का उपयोग करें
    target_user = user or current_user

    if not target_user or not target_user.is_authenticated or not target_user.google_refresh_token:
        return None

    creds = Credentials.from_authorized_user_info({
        "token": target_user.google_access_token,
        "refresh_token": target_user.google_refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": get_config_value("GOOGLE_CLIENT_ID"),
        "client_secret": get_config_value("GOOGLE_CLIENT_SECRET"),
        "scopes": ALL_SCOPES 
    })

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            target_user.google_access_token = creds.token
            target_user.google_token_expiry = creds.expiry
            db.session.commit()
        except Exception as e:
            # अगर टोकन रिफ्रेश फेल होता है, तो लॉग करें और None लौटाएं
            from tubealgo.models import log_system_event
            log_system_event(
                message=f"Google token refresh failed for user {target_user.id}",
                log_type='ERROR',
                details={'error': str(e)}
            )
            return None
    
    return creds

def parse_duration(duration_str):
    if not duration_str: return 0, "N/A"
    regex = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
    parts = regex.match(duration_str)
    if not parts: return 0, "N/A"
    parts = parts.groups()
    hours = int(parts[0]) if parts[0] else 0
    minutes = int(parts[1]) if parts[1] else 0
    seconds = int(parts[2]) if parts[2] else 0
    total_seconds = hours * 3600 + minutes * 60 + seconds
    if hours > 0:
        return total_seconds, f"{hours:02}:{minutes:02}:{seconds:02}"
    else:
        return total_seconds, f"{minutes:02}:{seconds:02}"

def get_video_info_dict(video_id):
    data = get_full_video_details(video_id)
    if 'error' in data: return data
    stats, snippet, content = data.get('statistics', {}), data.get('snippet', {}), data.get('contentDetails', {})
    description = snippet.get('description', '')
    upload_date = datetime.fromisoformat(snippet['publishedAt'].replace('Z', ''))
    days_since_upload = (datetime.utcnow() - upload_date).days
    view_count = int(stats.get('viewCount', 0))
    _, duration_formatted = parse_duration(content.get('duration'))
    
    hashtags = re.findall(r"#(\w+)", description)
    return {
        'id': data.get('id'), 'title': snippet.get('title'), 'channel_title': snippet.get('channelTitle', ''),
        'channel_id': snippet.get('channelId', ''), 'description': description, 'tags': snippet.get('tags', []), 
        'hashtags': hashtags, 'thumbnail_url': snippet.get('thumbnails', {}).get('maxres', snippet.get('thumbnails', {}).get('high', {})).get('url'),
        'upload_date_str': upload_date.strftime('%B %d, %Y'), 'duration_str': duration_formatted,
        'views': view_count, 'likes': int(stats.get('likeCount', 0)), 'comments': int(stats.get('commentCount', 0)),
        'days_since_upload': days_since_upload
    }

def sanitize_filename(name):
    if not name: return "Untitled"
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    name = emoji_pattern.sub(r'', name)
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:100] if name else "Untitled"

def get_most_used_tags(channel_id, video_limit=50):
    return fetcher_get_most_used_tags(channel_id, video_limit)