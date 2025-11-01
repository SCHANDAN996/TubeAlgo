# tubealgo/services/youtube_core.py

import itertools
import logging
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tubealgo.models import get_config_value, APIKeyStatus
from tubealgo import db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_youtube_service():
    """
    Creates and returns a YouTube Data API service object.
    Cycles through available API keys and automatically resets keys older than 24 hours.
    """
    API_KEYS_STRING = get_config_value('YOUTUBE_API_KEYS', '')
    API_KEYS = [key.strip() for key in API_KEYS_STRING.split(',') if key.strip()]
    
    if not API_KEYS: 
        return None, "Server API Key not configured."

    # *** NEW FIX: Self-healing logic for exhausted keys ***
    try:
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        keys_to_reset = APIKeyStatus.query.filter(
            APIKeyStatus.status == 'exhausted',
            APIKeyStatus.last_failure_at < twenty_four_hours_ago
        ).all()
        
        if keys_to_reset:
            for key_status in keys_to_reset:
                logging.info(f"Resetting API key status to 'active' for {key_status.key_identifier} as it expired more than 24 hours ago.")
                key_status.status = 'active'
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"Failed to auto-reset API key statuses: {e}")
    # *** END OF NEW FIX ***

    key_cycler = itertools.cycle(API_KEYS)
    
    for _ in range(len(API_KEYS)):
        api_key = next(key_cycler)
        key_identifier = f"{api_key[:8]}...{api_key[-4:]}"

        # Check if the key is marked as exhausted in the database
        key_status = APIKeyStatus.query.filter_by(key_identifier=key_identifier).first()
        if key_status and key_status.status == 'exhausted':
            logging.warning(f"Skipping API Key {key_identifier} as it is marked exhausted for the day.")
            continue

        try:
            service = build('youtube', 'v3', developerKey=api_key)
            # A lightweight call to check if the key is valid and has quota
            service.i18nLanguages().list(part='snippet').execute()
            logging.info(f"Using API Key starting with: {api_key[:5]}")
            return service, None
        except HttpError as e:
            error_content_str = str(e)
            if 'quotaExceeded' in error_content_str:
                logging.warning(f"API Key {key_identifier} quota exceeded. Cycling to next key.")
                
                try:
                    if not key_status:
                        key_status = APIKeyStatus(key_identifier=key_identifier)
                        db.session.add(key_status)
                    
                    key_status.status = 'exhausted'
                    key_status.last_failure_at = datetime.utcnow()
                    db.session.commit()
                except Exception as db_error:
                    db.session.rollback()
                    logging.error(f"Failed to update API key status in DB: {db_error}")
                    
                continue # Try the next key
            else:
                # For other HTTP errors, we just return the error
                return None, f"API Key Error: {error_content_str}"
                
    return None, "All available API Keys have exhausted their quota for the day."