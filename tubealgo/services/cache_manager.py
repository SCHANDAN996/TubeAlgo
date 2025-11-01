# Filepath: tubealgo/services/cache_manager.py
from tubealgo import db
from tubealgo.models import ApiCache
from datetime import datetime, timedelta
import json

def get_from_cache(key):
    """
    Checks for a valid cache entry and returns it if found.
    """
    now = datetime.utcnow()
    cache_entry = ApiCache.query.filter(ApiCache.cache_key == key, ApiCache.expires_at > now).first()
    
    if cache_entry:
        print(f"CACHE HIT for key: {key}")
        return cache_entry.cache_value
    
    print(f"CACHE MISS for key: {key}")
    return None

def set_to_cache(key, value, expire_hours=4):
    """
    Saves a value to the cache with an expiration time.
    """
    now = datetime.utcnow()
    expires_at = now + timedelta(hours=expire_hours)
    
    # Check if an entry already exists and update it, or create a new one
    cache_entry = ApiCache.query.filter_by(cache_key=key).first()
    
    if cache_entry:
        cache_entry.cache_value = value
        cache_entry.expires_at = expires_at
    else:
        cache_entry = ApiCache(
            cache_key=key,
            cache_value=value,
            expires_at=expires_at
        )
        db.session.add(cache_entry)
        
    db.session.commit()
    print(f"CACHE SET for key: {key}")

