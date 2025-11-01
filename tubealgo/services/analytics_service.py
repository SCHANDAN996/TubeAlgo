# tubealgo/services/analytics_service.py

import logging
import time
from functools import wraps # Import wraps for decorator preservation
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import date, timedelta
import numpy as np # Make sure numpy is installed

# Configure logging (ensure this runs only once, maybe better in __init__.py)
# If already configured in __init__.py, you might not need basicConfig here again.
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Use named logger

# --- Retry Decorator ---
def retry_api_call(max_retries=2, delay=3): # <<< Initial delay slightly increased to 3s
    """Decorator to retry API calls on specific errors like timeouts."""
    def decorator(func):
        @wraps(func) # Use wraps to preserve function metadata
        def wrapper(*args, **kwargs):
            retries = 0
            last_exception = None # <<< Store last exception
            while retries <= max_retries:
                try:
                    return func(*args, **kwargs)
                # <<< Catch broader Exception >>>
                except Exception as e:
                    last_exception = e # Store the exception
                    # Check for WSAETIMEDOUT (Windows) or general TimeoutError or socket errors
                    # Added check for ConnectionResetError as well
                    is_timeout = (
                        (isinstance(e, OSError) and getattr(e, 'errno', 0) == 10060) or # WSAETIMEDOUT
                        isinstance(e, TimeoutError) or
                        isinstance(e, ConnectionResetError) or # Connection reset by peer
                        'socket error' in str(e).lower() or
                        'timed out' in str(e).lower() or
                        'connection aborted' in str(e).lower()
                    )

                    # Check for retryable HTTP errors
                    is_retryable_http_error = isinstance(e, HttpError) and hasattr(e, 'resp') and e.resp.status in [500, 503, 429] # Internal Server Error, Service Unavailable, Too Many Requests

                    if (is_timeout or is_retryable_http_error) and retries < max_retries:
                        retries += 1
                        # Exponential backoff with jitter
                        wait_time = (delay * (2 ** (retries - 1))) + np.random.uniform(0, 1)
                        logger.warning(f"API call failed ({type(e).__name__} in {func.__name__}). Retrying in {wait_time:.2f} seconds... (Attempt {retries}/{max_retries})")
                        time.sleep(wait_time)
                        continue # <<< Continue to next retry iteration
                    else:
                        # Non-retryable error or max retries reached
                        logger.error(f"API call ({func.__name__}) failed permanently after {retries} retries: {e}", exc_info=True if not isinstance(e, HttpError) else False) # Log traceback for non-HttpErrors
                        raise e # Re-raise the caught exception
            # This should not be reached if max_retries >= 0, but raise the last known error if it does
            raise last_exception or Exception(f"API call ({func.__name__}) failed after exhausting retries.")
        return wrapper
    return decorator

# --- HELPER FUNCTION TO FIND KEY MOMENTS (DIPS/SPIKES) ---
def find_key_moments(retention_data):
    """
    Analyzes retention data points to identify significant dips and spikes.

    Args:
        retention_data (list): A list of retention values (usually 101 points from 0% to 100%).

    Returns:
        tuple: A tuple containing two lists: (dips, spikes).
               Each item in the lists is a dictionary {'x': index (percentage), 'y': value}.
    """
    dips = []
    spikes = []
    if not retention_data or len(retention_data) < 3:
        return dips, spikes

    # Use numpy for slightly cleaner calculations if available and data is numeric
    try:
        data_np = np.array(retention_data, dtype=float) # Convert Nones or non-numerics to NaN
        if len(data_np) < 3: return dips, spikes

        for i in range(1, len(data_np) - 1):
            prev_val, current_val, next_val = data_np[i-1], data_np[i], data_np[i+1]

            # Skip if current or neighbors are NaN (invalid data)
            if np.isnan(prev_val) or np.isnan(current_val) or np.isnan(next_val):
                continue

            neighborhood_avg = (prev_val + next_val) / 2

            # Dip: current point is significantly lower than its neighbors (e.g., more than 5% relative drop)
            if neighborhood_avg > 0.001 and current_val < neighborhood_avg * 0.95: # Use small threshold for avg > 0
                dips.append({'x': i, 'y': current_val})

            # Spike: current point is significantly higher than its neighbors (e.g., more than 3% relative rise)
            if neighborhood_avg > 0.001 and current_val > neighborhood_avg * 1.03:
                spikes.append({'x': i, 'y': current_val})
            elif neighborhood_avg <= 0.001 and current_val > 0.01: # Handle spike from near-zero baseline (e.g., > 1%)
                 spikes.append({'x': i, 'y': current_val})

    except Exception as e:
        logger.error(f"Error during find_key_moments calculation: {e}")
        # Fallback to original loop if numpy fails or data is complex
        for i in range(1, len(retention_data) - 1):
            prev_val = retention_data[i-1]
            current_val = retention_data[i]
            next_val = retention_data[i+1]
            if not all(isinstance(v, (int, float)) or v is None for v in [prev_val, current_val, next_val]): continue
            if prev_val is None or current_val is None or next_val is None: continue
            neighborhood_avg = (prev_val + next_val) / 2
            if neighborhood_avg > 0 and current_val < neighborhood_avg * 0.95: dips.append({'x': i, 'y': current_val})
            if neighborhood_avg > 0 and current_val > neighborhood_avg * 1.03: spikes.append({'x': i, 'y': current_val})
            elif neighborhood_avg == 0 and current_val > 0.01: spikes.append({'x': i, 'y': current_val})

    return dips, spikes


@retry_api_call()
def get_recent_video_ids(credentials, max_results=20):
    """Fetches the IDs of the user's most recent videos."""
    youtube = build('youtube', 'v3', credentials=credentials)
    channels_response = youtube.channels().list(mine=True, part='contentDetails').execute()

    if not channels_response.get('items'):
        logger.warning("No channels found for the user during get_recent_video_ids.")
        return []

    # Handle potential KeyError if contentDetails or relatedPlaylists are missing
    try:
        uploads_playlist_id = channels_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    except (KeyError, IndexError):
        logger.error("Could not find uploads playlist ID for the user.")
        return []


    playlist_items_response = youtube.playlistItems().list(
        playlistId=uploads_playlist_id,
        part='contentDetails',
        maxResults=max_results # Limit results per page
    ).execute()

    video_ids = [
        item['contentDetails']['videoId']
        for item in playlist_items_response.get('items', [])
        if 'contentDetails' in item and 'videoId' in item['contentDetails'] # Safer access
    ]
    logger.info(f"Fetched {len(video_ids)} recent video IDs.")
    return video_ids


# --- KPI FUNCTIONS (Updated with Retry and simplified error handling) ---
@retry_api_call()
def get_views_for_video(analytics, video_id):
    """Fetches only the view count for a video."""
    start_date_str = (date.today() - timedelta(days=365*5)).strftime('%Y-%m-%d') # Use 5 years
    # Decorator handles retries/exceptions
    response = analytics.reports().query(
        ids='channel==MINE', startDate=start_date_str, endDate=date.today().strftime('%Y-%m-%d'),
        metrics='views', dimensions='video', filters=f'video=={video_id}'
    ).execute()
    # Safer access to rows data
    views = response.get('rows', [[None, 0]])[0][1] if response.get('rows') else 0
    logger.debug(f"Fetched views for {video_id}: {views}")
    return int(views) # Ensure integer


@retry_api_call()
def get_watch_time_for_video(analytics, video_id):
    """Fetches only the watch time for a video, returns hours."""
    start_date_str = (date.today() - timedelta(days=365*5)).strftime('%Y-%m-%d')
    # Decorator handles retries/exceptions
    response = analytics.reports().query(
        ids='channel==MINE', startDate=start_date_str, endDate=date.today().strftime('%Y-%m-%d'),
        metrics='estimatedMinutesWatched', dimensions='video', filters=f'video=={video_id}'
    ).execute()
    minutes = response.get('rows', [[None, 0]])[0][1] if response.get('rows') else 0
    watch_hours = round(minutes / 60, 1)
    logger.debug(f"Fetched watch time for {video_id}: {watch_hours} hours")
    return watch_hours


@retry_api_call()
def get_subscribers_for_video(analytics, video_id):
    """Fetches only the net subscribers gained from a video."""
    start_date_str = (date.today() - timedelta(days=365*5)).strftime('%Y-%m-%d')
    # Decorator handles retries/exceptions
    response = analytics.reports().query(
        ids='channel==MINE', startDate=start_date_str, endDate=date.today().strftime('%Y-%m-%d'),
        metrics='subscribersGained,subscribersLost', dimensions='video', filters=f'video=={video_id}'
    ).execute()
    net_subs = 0
    if response.get('rows'):
        try:
             # Ensure indices are valid
             gained = response['rows'][0][1] or 0
             lost = response['rows'][0][2] or 0
             net_subs = gained - lost
        except (IndexError, TypeError):
             logger.warning(f"Unexpected row format for subscribers for {video_id}: {response.get('rows')}")
             net_subs = 0 # Default to 0 if data is malformed

    logger.debug(f"Fetched net subscribers for {video_id}: {net_subs}")
    return int(net_subs) # Ensure integer


@retry_api_call(max_retries=1) # Fewer retries for CTR as it might be less critical
def get_video_ctr(credentials, video_id, start_date, end_date):
    """Fetches impression click-through rate for a specific video and date range."""
    analytics = build('youtubeAnalytics', 'v2', credentials=credentials)
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')

    try:
        response = analytics.reports().query(
             ids='channel==MINE', startDate=start_date_str, endDate=end_date_str,
            metrics='impressionClickThroughRate', dimensions='video', filters=f'video=={video_id}'
        ).execute()

        if response.get('rows'):
            # Safer access and rounding
            ctr = round(response['rows'][0][1] or 0.0, 2)
            logger.debug(f"Fetched CTR for {video_id}: {ctr}%")
            return ctr, None # Return value, no error
        else:
            logger.warning(f"No CTR data returned for {video_id} between {start_date_str} and {end_date_str}")
            return 0.0, None # Return 0, no error
    except Exception as e:
        # Log the specific error, decorator handles retries/raising
        logger.error(f'Specific error in get_video_ctr for {video_id}: {str(e)}')
        # Return None and an error dictionary as expected by the caller, consistent with original logic
        return None, {'error': f'Could not fetch CTR: {str(e)}'}


@retry_api_call()
def get_audience_retention(credentials, video_id):
    """Fetches audience retention data for a video."""
    analytics = build('youtubeAnalytics', 'v2', credentials=credentials)
    start_date = (date.today() - timedelta(days=28)).strftime('%Y-%m-%d') # Keep 28 days for retention
    end_date = date.today().strftime('%Y-%m-%d')

    response = analytics.reports().query(
        ids='channel==MINE', startDate=start_date, endDate=end_date,
        # Use relative time processed for better accuracy across video lengths
        metrics='relativeRetentionPerformance', dimensions='elapsedVideoTimeRatio',
        filters=f'video=={video_id}'
    ).execute()

    # NOTE: 'relativeRetentionPerformance' returns values like HIGH, AVERAGE, LOW
    # To get the actual percentage curve, we still need 'audienceWatchRatio'.
    # Let's fetch 'audienceWatchRatio' as well. It's better to make two calls if needed
    # than rely on a metric that doesn't give the percentage curve.

    response_ratio = analytics.reports().query(
        ids='channel==MINE', startDate=start_date, endDate=end_date,
        metrics='audienceWatchRatio', dimensions='elapsedVideoTimeRatio',
        filters=f'video=={video_id}',
        maxResults=101 # Explicitly ask for up to 101 points
    ).execute()


    if response_ratio.get('rows'):
        # Ensure data aligns to 101 points (0% to 100%)
        raw_data = {int(row[0]*100): row[1] for row in response_ratio['rows']}
        # Fill missing points with None initially, then interpolate or forward-fill
        retention_data_raw = [raw_data.get(i) for i in range(101)]

        # Simple forward fill for missing data points
        last_valid_value = 0.0
        retention_data_filled = []
        for val in retention_data_raw:
            if val is not None and isinstance(val, (float, int)):
                last_valid_value = val
            retention_data_filled.append(last_valid_value if val is None else val)

        labels = [f"{i}%" for i in range(101)]

        logger.debug(f"Fetched audience retention ratio for {video_id}")
        return {'labels': labels, 'data': retention_data_filled, 'error': None}
    else:
        logger.warning(f"No audience retention ratio data available for video {video_id}")
        return {'labels': [], 'data': [], 'error': 'No retention data available for this period.'}


# This function calls other decorated functions, so it needs robust error handling
def get_average_retention(credentials):
    """Calculates average retention based on recent videos."""
    try:
        # Fetch recent video IDs first (this call is decorated)
        recent_video_ids = get_recent_video_ids(credentials, max_results=15)
        if not recent_video_ids or len(recent_video_ids) < 2:
            logger.warning("Not enough recent videos found to calculate average retention.")
            return {'data': [], 'error': 'Not enough recent videos to calculate an average.'}

        all_retention_curves = []
        successful_fetches = 0
        max_videos_to_process = 10 # Limit API calls further if needed

        for video_id in recent_video_ids[:max_videos_to_process]:
            try:
                # Call the decorated function for individual retention
                retention_result = get_audience_retention(credentials, video_id)

                # Check the result carefully
                if retention_result and not retention_result.get('error'):
                    curve = retention_result.get('data')
                    # Ensure curve has exactly 101 points before adding
                    if isinstance(curve, list) and len(curve) == 101:
                         # Extra check: ensure data is numeric, replace non-numeric with 0
                         numeric_curve = [x if isinstance(x, (int, float)) else 0.0 for x in curve]
                         all_retention_curves.append(numeric_curve)
                         successful_fetches += 1
                    else:
                         logger.warning(f"Skipping retention curve for {video_id} due to unexpected length/type: {len(curve) if isinstance(curve, list) else type(curve)}")
                else:
                    # Log error if get_audience_retention itself returned an error dict
                    error_detail = retention_result.get('error', 'Unknown Error') if isinstance(retention_result, dict) else 'Invalid retention result format'
                    logger.warning(f"Failed to fetch retention for video {video_id} needed for average: {error_detail}")

            except Exception as inner_e:
                # Catch errors raised by the decorated get_audience_retention
                logger.warning(f"Exception fetching retention for video {video_id} during average calculation: {inner_e}")
                continue # Skip this video and try the next

        if not all_retention_curves:
            logger.error("Could not fetch any valid retention curves for recent videos.")
            return {'data': [], 'error': 'Could not fetch valid retention for recent videos.'}
        if successful_fetches < 2:
             logger.warning(f"Only fetched {successful_fetches} valid retention curves. Average might not be representative.")
             # Proceeding anyway, but logged a warning

        # Calculate average only if we have curves
        try:
             avg_retention_curve = np.mean(all_retention_curves, axis=0).tolist()
             logger.info(f"Calculated average retention based on {len(all_retention_curves)} videos.")
             return {'data': avg_retention_curve, 'error': None}
        except Exception as e:
             logger.error(f"Error calculating numpy mean for average retention: {e}")
             return {'data': [], 'error': 'Error calculating average retention.'}


    except Exception as e:
         # Catch errors from get_recent_video_ids or other unexpected issues
         logger.error(f"Error in get_average_retention function: {e}", exc_info=True)
         return {'data': [], 'error': f'Error during average calculation: {str(e)}'}


@retry_api_call()
def get_traffic_sources(credentials, video_id):
    """Fetches top traffic sources for a video."""
    analytics = build('youtubeAnalytics', 'v2', credentials=credentials)
    start_date = (date.today() - timedelta(days=28)).strftime('%Y-%m-%d')
    end_date = date.today().strftime('%Y-%m-%d')

    response = analytics.reports().query(
        ids='channel==MINE', startDate=start_date, endDate=end_date,
        metrics='views', dimensions='insightTrafficSourceType', filters=f'video=={video_id}',
        sort='-views', maxResults=10 # Fetch top 10 sources
    ).execute()

    if response.get('rows'):
        source_map = {
             'SUBSCRIBER': 'Notifications & Subs Feed', 'YT_SEARCH': 'YouTube Search',
            'RELATED_VIDEO': 'Suggested Videos', 'END_SCREEN': 'End Screens',
            'PLAYLIST': 'Playlists', 'EXTERNAL_URL': 'External (Websites/Apps)',
            'NO_LINK_OTHER': 'Direct or Unknown', 'BROWSE_FEATURES': 'Browse Features (Home, etc.)',
            'CHANNEL_PAGE': 'Channel Pages', 'YT_OTHER_PAGE': 'Other YouTube Features',
            'VIDEO_REMIXES': 'Shorts Feed', 'NO_LINK_EMBEDDED': 'Embedded Player',
            'ADVERTISING': 'Advertising', 'HASHTAG_PAGE': 'Hashtag Pages',
            'SOUND_PAGE': 'Sound Pages', 'PLAYLIST_PAGE': 'Playlist Page' # Added Playlist Page
            # Add more mappings as needed based on YouTube Analytics documentation
        }
        # Limit to top N sources for clarity in chart, e.g., top 7 + 'Other'
        top_n = 7
        rows = response['rows']
        labels = []
        views_data = []
        other_views = 0

        for i, row in enumerate(rows):
            try:
                source_name = source_map.get(row[0], row[0].replace('_', ' ').title())
                view_count = int(row[1]) # Ensure integer
                if i < top_n:
                    labels.append(source_name)
                    views_data.append(view_count)
                else:
                    other_views += view_count
            except (IndexError, TypeError, ValueError):
                 logger.warning(f"Skipping malformed traffic source row for {video_id}: {row}")
                 continue # Skip malformed row

        # Aggregate remaining sources into 'Other'
        if other_views > 0:
            labels.append('Other Sources')
            views_data.append(other_views)

        if not labels: # Handle case where all rows were malformed or no rows
             logger.warning(f"No valid traffic source data processed for video {video_id}")
             return {'labels': [], 'data': [], 'error': 'No valid traffic source data.'}


        logger.debug(f"Fetched and processed traffic sources for {video_id}")
        return {'labels': labels, 'data': views_data, 'error': None}
    else:
        logger.warning(f"No traffic source data available from API for video {video_id}")
        return {'labels': [], 'data': [], 'error': 'No traffic source data available.'}