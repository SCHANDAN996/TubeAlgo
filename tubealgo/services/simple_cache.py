# tubealgo/services/simple_cache.py
"""
Simple In-Memory Cache
Redis replacement for free tier deployment

Features:
- Thread-safe operations
- TTL (Time To Live) support
- Automatic cleanup of expired entries
- Memory-efficient
"""

from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


class SimpleCache:
    """
    In-memory cache with TTL support
    Thread-safe implementation
    """
    
    def __init__(self):
        self._cache = {}
        self._lock = Lock()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                
                # Check if expired
                if expiry and datetime.now() > expiry:
                    del self._cache[key]
                    logger.debug(f"CACHE EXPIRED for key: {key}")
                    self._misses += 1
                    return None
                
                logger.debug(f"CACHE HIT for key: {key}")
                self._hits += 1
                return value
            
            logger.debug(f"CACHE MISS for key: {key}")
            self._misses += 1
            return None
    
    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """
        Set value in cache with TTL
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default: 1 hour)
                 Set to None for no expiration
        """
        with self._lock:
            expiry = datetime.now() + timedelta(seconds=ttl) if ttl else None
            self._cache[key] = (value, expiry)
            logger.debug(f"CACHE SET for key: {key} (TTL: {ttl}s)")
    
    def delete(self, key: str) -> bool:
        """
        Delete key from cache
        
        Args:
            key: Cache key
            
        Returns:
            True if key was deleted, False if not found
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"CACHE DELETE for key: {key}")
                return True
            return False
    
    def exists(self, key: str) -> bool:
        """
        Check if key exists and is not expired
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists and valid, False otherwise
        """
        return self.get(key) is not None
    
    def clear(self) -> None:
        """Clear all cache entries"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"CACHE CLEARED - {count} entries removed")
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired entries
        
        Returns:
            Number of entries removed
        """
        with self._lock:
            now = datetime.now()
            expired_keys = [
                key for key, (_, expiry) in self._cache.items()
                if expiry and now > expiry
            ]
            
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                logger.info(f"CACHE CLEANUP: Removed {len(expired_keys)} expired entries")
            
            return len(expired_keys)
    
    def get_stats(self) -> dict:
        """
        Get cache statistics
        
        Returns:
            Dictionary with cache stats
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'total_entries': len(self._cache),
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': round(hit_rate, 2),
                'total_requests': total_requests
            }
    
    def get_keys(self, pattern: str = None) -> list:
        """
        Get all keys matching pattern
        
        Args:
            pattern: Optional pattern to match (simple string matching)
            
        Returns:
            List of matching keys
        """
        with self._lock:
            if pattern:
                return [key for key in self._cache.keys() if pattern in key]
            return list(self._cache.keys())
    
    def set_many(self, mapping: dict, ttl: int = 3600) -> None:
        """
        Set multiple key-value pairs
        
        Args:
            mapping: Dictionary of key-value pairs
            ttl: Time to live in seconds
        """
        with self._lock:
            expiry = datetime.now() + timedelta(seconds=ttl) if ttl else None
            for key, value in mapping.items():
                self._cache[key] = (value, expiry)
            logger.debug(f"CACHE SET_MANY: {len(mapping)} entries")
    
    def get_many(self, keys: list) -> dict:
        """
        Get multiple values at once
        
        Args:
            keys: List of keys to retrieve
            
        Returns:
            Dictionary with found key-value pairs
        """
        result = {}
        for key in keys:
            value = self.get(key)
            if value is not None:
                result[key] = value
        return result
    
    def increment(self, key: str, amount: int = 1) -> int:
        """
        Increment integer value
        
        Args:
            key: Cache key
            amount: Amount to increment (default: 1)
            
        Returns:
            New value after increment
        """
        with self._lock:
            current = self.get(key) or 0
            new_value = int(current) + amount
            self.set(key, new_value)
            return new_value
    
    def decrement(self, key: str, amount: int = 1) -> int:
        """
        Decrement integer value
        
        Args:
            key: Cache key
            amount: Amount to decrement (default: 1)
            
        Returns:
            New value after decrement
        """
        return self.increment(key, -amount)


# Global cache instance
cache = SimpleCache()


# Periodic cleanup task
def cleanup_cache_periodically():
    """
    Cleanup expired cache entries
    Call this periodically (e.g., every hour)
    """
    try:
        removed = cache.cleanup_expired()
        if removed > 0:
            logger.info(f"Periodic cache cleanup: Removed {removed} expired entries")
        return removed
    except Exception as e:
        logger.error(f"Cache cleanup error: {str(e)}")
        return 0


# Cache decorator
def cached(ttl: int = 3600, key_prefix: str = ''):
    """
    Decorator to cache function results
    
    Usage:
        @cached(ttl=600, key_prefix='user_data')
        def get_user_data(user_id):
            return expensive_operation(user_id)
    
    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache key
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Generate cache key
            import hashlib
            import json
            
            key_parts = [key_prefix, func.__name__]
            if args:
                key_parts.append(str(args))
            if kwargs:
                key_parts.append(json.dumps(kwargs, sort_keys=True))
            
            cache_key = hashlib.md5('_'.join(key_parts).encode()).hexdigest()
            
            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache result
            cache.set(cache_key, result, ttl)
            
            return result
        
        wrapper.__name__ = func.__name__
        return wrapper
    
    return decorator
