# tubealgo/routes/video_analytics_routes.py

import logging
import json
from flask import Blueprint, render_template, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
# <<< FIX 1: Import Class with an Alias >>>
from youtube_transcript_api import YouTubeTranscriptApi as YTTApi, TranscriptsDisabled, NoTranscriptFound
import concurrent.futures
import threading
from ..services.ai_service import generate_retention_insights
from .utils import get_credentials, parse_duration
from ..services.analytics_service import (
    get_audience_retention, get_traffic_sources, get_average_retention,
    get_views_for_video, get_watch_time_for_video, get_subscribers_for_video,
    find_key_moments
)
from ..services.youtube_manager import get_single_video
from flask_sse import sse
import time

video_analytics_bp = Blueprint('video_analytics', __name__)
logger = logging.getLogger(__name__)

# --- _handle_api_error helper (Remains same) ---
def _handle_api_error(e, context="API call"):
    # ... (code as before) ...
    error_msg = str(e); status_code = 500; user_friendly_message = f"API Error: {error_msg}"
    if "timeout" in error_msg.lower() or "WSAETIMEDOUT" in error_msg: status_code = 504; user_friendly_message = "Error loading data. (Timeout)" # Simplified timeout check
    elif isinstance(e, HttpError): status_code = e.resp.status if hasattr(e, 'resp') else 500; # ... (rest of HttpError handling) ...
    elif "Working outside of application context" in error_msg: user_friendly_message = "Internal Server Error (App Context)"; status_code = 500
    should_log_traceback = not isinstance(e, HttpError) or status_code >= 500; logger.error(f"Caught exception in {context}: {error_msg}", exc_info=should_log_traceback)
    return {'error': user_friendly_message}

# --- video_dashboard route (Remains same) ---
@video_analytics_bp.route('/manage/analytics/<string:video_id>')
@login_required
def video_dashboard(video_id):
    # ... (code as before) ...
    creds = get_credentials() # ... error handling ...
    video_details = None
    try:
        logger.info(f"Fetching initial video details for {video_id}...")
        video_details = get_single_video(creds, video_id) # ... error handling ...
        if isinstance(video_details, dict) and 'error' in video_details: logger.error(f"Error fetching initial details for {video_id}: {video_details['error']}"); flash(f"Could not retrieve initial video details: {video_details['error']}", 'error'); return redirect(url_for('manager.manage_videos'))
        elif not isinstance(video_details, dict): raise TypeError(f"Expected dict, got {type(video_details)}")
        logger.info(f"Successfully fetched initial details for {video_id}.")
    except Exception as e: logger.error(f"Exception fetching initial details for {video_id}: {e}", exc_info=True); flash(f"Failed to load video details: {str(e)}", 'error'); return redirect(url_for('manager.manage_videos'))
    return render_template('video_analytics.html', video=video_details)


# --- Consolidated API Endpoint ---
@video_analytics_bp.route('/api/analytics/<string:video_id>/stream-data')
@login_required
def stream_all_video_data(video_id):
    creds = get_credentials(); # ... error handling ...
    if not creds: return jsonify({'error': 'Authentication failed.'}), 401
    app = current_app._get_current_object()
    channel = f"video-{video_id}-{current_user.id}-{int(time.time())}"
    logger.info(f"SSE: Stream initiated for channel {channel}")

    # --- Helper to run tasks ---
    def run_and_publish(task_func, event_type):
        with app.app_context():
            result = None
            try:
                result = task_func()
                # <<< FIX Traffic Logging >>>
                if event_type == 'traffic':
                    logger.debug(f"SSE: Raw result for traffic task: {result}") # Log raw traffic result

                if isinstance(result, dict) and result.get('error'):
                    if "No data available" not in result.get('error', ''): logger.warning(f"SSE: Task {task_func.__name__} for {channel} returned error: {result['error']}")
                    sse.publish({"error": result['error']}, type=event_type, channel=channel)
                else: # Success case
                    data_to_publish = result
                    if event_type in ['views', 'watchTime', 'subscribers']: data_to_publish = {'data': result}
                    # <<< FIX Traffic Publish - Ensure 'data' key exists for frontend >>>
                    elif event_type == 'traffic':
                        # Service returns {'labels': [], 'data': [], 'error': 'No data available.'} OR {'labels': [...], 'data': [...], 'error': None}
                        # Wrap it inside a 'data' key for frontend consistency if no top-level error raised
                        data_to_publish = {'data': result, 'error': result.get('error')} # Pass potential 'No data' error inside 'error'
                    # retention and insights return dicts like {'retention': {...}} or {'insights': {...}}
                    sse.publish(data_to_publish, type=event_type, channel=channel)
                    logger.debug(f"SSE: Published '{event_type}' OK for {channel}. Data: {json.dumps(data_to_publish)}") # Log published data
            except Exception as e: # Handle raised exceptions
                error_dict = _handle_api_error(e, f"SSE Task {task_func.__name__} for {video_id}")
                sse.publish(error_dict, type=event_type, channel=channel)

    # --- Specific Task Definitions ---
    def task_views(): analytics_client = build('youtubeAnalytics', 'v2', credentials=creds); return get_views_for_video(analytics_client, video_id)
    def task_watch_time(): analytics_client = build('youtubeAnalytics', 'v2', credentials=creds); return get_watch_time_for_video(analytics_client, video_id)
    def task_subscribers(): analytics_client = build('youtubeAnalytics', 'v2', credentials=creds); return get_subscribers_for_video(analytics_client, video_id)
    def task_retention():
        # ... (retention logic remains the same) ...
        video_details = get_single_video(creds, video_id); # Raises on fail
        duration_iso = video_details.get('contentDetails', {}).get('duration'); total_seconds, _ = parse_duration(duration_iso)
        if total_seconds == 0: return {'error': 'Could not determine video duration.'}
        video_data = get_audience_retention(creds, video_id); # Raises or error dict
        average_data = get_average_retention(creds); # Dict with error or data
        combined = {"video_duration_seconds": total_seconds, "video_retention": video_data, "average_retention": average_data};
        if isinstance(video_data, dict) and video_data.get('error'): combined['error'] = video_data.get('error')
        elif isinstance(average_data, dict) and average_data.get('error'): logger.warning(f"Average retention failed for {video_id}: {average_data.get('error')}")
        return combined

    def task_traffic(): return get_traffic_sources(creds, video_id) # Raises or error dict

    def task_ai_insights():
        # ... (dependency fetching remains the same) ...
        retention_curve_ai, dips_ai, spikes_ai, total_seconds_ai = [], [], [], 0
        try: # Fetch dependencies
             retention_result_ai = get_audience_retention(creds, video_id); # Raises or error dict
             if isinstance(retention_result_ai, dict) and retention_result_ai.get('error'): raise Exception(retention_result_ai['error'])
             retention_curve_ai = retention_result_ai.get('data', []); #... error check ...
             dips_ai, spikes_ai = find_key_moments(retention_curve_ai)
             video_details_ai = get_single_video(creds, video_id); # Raises or error dict
             if 'error' in video_details_ai: raise Exception(video_details_ai['error'])
             duration_iso_ai = video_details_ai.get('contentDetails', {}).get('duration'); total_seconds_ai, _ = parse_duration(duration_iso_ai)
             if total_seconds_ai == 0: raise Exception("Could not determine duration for AI")
        except Exception as e_dep: logger.warning(f"AI Insights: Skipping dep fetch error for {video_id}: {e_dep}"); return {'insights_error': f'Could not get data for AI: {str(e_dep)[:50]}...'}

        transcript_ai = ""
        try: # Fetch Transcript
            # <<< FIX 2: Use the imported Alias YTTApi >>>
            logger.debug(f"AI Insights: Attempting transcript fetch for {video_id} using YTTApi.get_transcript")
            transcript_list = YTTApi.get_transcript(video_id, languages=['en', 'hi'])
            transcript_ai = " ".join(item['text'].replace('\n', ' ').strip() for item in transcript_list)

            if not transcript_ai.strip(): logger.warning(f"AI Insights: Transcript for {video_id} is empty.")
            else: logger.debug(f"AI Insights: Transcript fetched successfully for {video_id} via get_transcript")

        except TranscriptsDisabled: logger.warning(f"AI Insights: Transcripts disabled for {video_id}.")
        except NoTranscriptFound: logger.warning(f"AI Insights: No transcript found for {video_id}.")
        # No need to catch AttributeError now if import is correct
        except Exception as e_tr: logger.error(f"AI Insights: Unexpected error fetching transcript for {video_id}: {e_tr}", exc_info=False)

        # Generate Insights
        logger.debug(f"AI Insights: Generating insights for {video_id}...")
        insights_result = generate_retention_insights(retention_curve_ai, dips_ai, spikes_ai, total_seconds_ai, transcript_ai); # ... error handling ...
        if isinstance(insights_result, dict) and insights_result.get('error'): #... handle AI error ...
             logger.error(f"AI insight generation failed for {video_id}: {insights_result.get('error')}"); ai_error_msg = insights_result.get('error', 'AI analysis failed'); err_detail = 'AI analysis failed.'; #... check quota/limit ...
             if 'quota' in ai_error_msg.lower() or 'limit' in ai_error_msg.lower() or 'key' in ai_error_msg.lower(): err_detail = 'AI analysis failed (Configuration or Limit Issue).'
             return {'insights_error': err_detail}
        elif not isinstance(insights_result, dict): logger.error(f"AI returned non-dict data for {video_id}"); return {'insights_error': 'AI returned invalid data.'}
        else: logger.debug(f"AI Insights: Generated OK for {video_id}"); return {'insights': insights_result}

    # --- Function to run tasks in background (Remains same) ---
    def run_tasks_and_publish_wrapper():
        # ... (code as before) ...
        tasks_map = { 'views': task_views, 'watchTime': task_watch_time, 'subscribers': task_subscribers, 'retention': task_retention, 'traffic': task_traffic, 'retentionInsights': task_ai_insights }
        TIMEOUT_SECONDS = 90; logger.info(f"SSE Wrapper: Starting tasks for {channel}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks_map), thread_name_prefix='SSEWorker') as inner_executor:
            futures = {inner_executor.submit(run_and_publish, func, event_name): event_name for event_name, func in tasks_map.items()}
            try:
                done, not_done = concurrent.futures.wait(futures, timeout=TIMEOUT_SECONDS); logger.info(f"SSE Wrapper: {len(done)} tasks completed, {len(not_done)} tasks incomplete/timed out for {channel}.")
                if not_done: logger.warning(f"SSE Wrapper: Timed out tasks for {channel}: {[futures[f] for f in not_done]}")
                for future in done:
                    if future.exception(): logger.error(f"SSE: Task {futures[future]} completed with exception: {future.exception()}")
            except Exception as e: logger.error(f"SSE Wrapper: Error during inner execution for {channel}: {e}", exc_info=True)
        with app.app_context(): # Signal completion
             try: sse.publish({"message": "Data stream finished."}, type="complete", channel=channel); logger.info(f"SSE Wrapper: Completion signal sent for {channel}")
             except Exception as e_pub: logger.error(f"SSE Wrapper: Failed to send completion signal for {channel}: {e_pub}")

    # --- Start background thread (Remains same) ---
    thread = threading.Thread(target=run_tasks_and_publish_wrapper, daemon=True)
    thread.start()
    logger.info(f"SSE: Initial request acknowledged for channel {channel}")
    return jsonify({"status": "initiated", "channel": channel}), 202

# --- Old individual routes are removed ---