# tubealgo/services/transcript_fetcher.py
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled, 
    NoTranscriptFound, 
    VideoUnavailable
)
import re
import time
import requests
from typing import Optional, List, Dict, Any
from xml.etree.ElementTree import ParseError

logger = logging.getLogger(__name__)

def extract_video_id(url_or_id: str) -> Optional[str]:
    """YouTube video URL se video ID extract karta hai."""
    url_or_id = url_or_id.strip()

    if re.fullmatch(r"^[a-zA-Z0-9_-]{11}$", url_or_id):
        return url_or_id

    match = re.search(
        r"(?:v=|\/|embed\/|shorts\/|live\/)([a-zA-Z0-9_-]{11})(?:\?|&|$)", 
        url_or_id
    )
    if match:
        return match.group(1)

    match = re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", url_or_id)
    if match:
        return match.group(1)

    return None


def try_manual_transcript_fetch(video_id: str, lang_code: str = 'hi') -> Optional[List[Dict[str, Any]]]:
    """
    Manual method se transcript fetch karta hai using YouTube's timedtext API.
    """
    try:
        base_url = "https://www.youtube.com/api/timedtext"
        params = {
            'v': video_id,
            'lang': lang_code,
            'fmt': 'json3'
        }
        
        logger.info(f"Trying manual fetch for {video_id} with lang={lang_code}")
        response = requests.get(base_url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'events' in data:
                segments = []
                for event in data['events']:
                    if 'segs' in event:
                        text = ''.join([seg.get('utf8', '') for seg in event['segs']])
                        if text.strip():
                            segments.append({
                                'text': text.strip(),
                                'start': event.get('tStartMs', 0) / 1000,
                                'duration': event.get('dDurationMs', 0) / 1000
                            })
                
                if segments:
                    logger.info(f"✓ Manual fetch successful: {len(segments)} segments")
                    return segments
        
        return None
        
    except Exception as e:
        logger.warning(f"Manual fetch failed: {e}")
        return None


def get_transcript_from_url(
    video_url_or_id: str, 
    languages: Optional[List[str]] = None,
    max_retries: int = 2,
    retry_delay: float = 1.5,
    try_translation: bool = True,
    try_manual_fetch: bool = True
) -> Dict[str, Any]:
    """
    YouTube video ke liye transcript fetch karta hai with multiple fallback strategies.
    """
    if languages is None:
        languages = ['hi', 'en-IN', 'en']
    
    video_id = extract_video_id(video_url_or_id)
    if not video_id:
        logger.error(f"Invalid video URL or ID: {video_url_or_id}")
        return {
            'success': False, 
            'error': 'Invalid YouTube URL or Video ID. Please check the link and try again.'
        }

    logger.info(f"Attempting to fetch transcript for video: {video_id}")

    # Strategy 1: Try youtube_transcript_api
    for attempt in range(max_retries + 1):
        try:
            transcript_list_obj = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Check if ANY transcripts exist
            available_transcripts = list(transcript_list_obj)
            if not available_transcripts:
                logger.warning(f"No transcripts available for {video_id}")
                return {
                    'success': False,
                    'error': 'No transcripts available. The video may be too new or transcripts may be disabled.'
                }
            
            # Try to find transcript in preferred languages
            try:
                transcript = transcript_list_obj.find_transcript(languages)
                logger.info(f"Found transcript in '{transcript.language}' for {video_id}")
                
            except NoTranscriptFound:
                # Strategy 2: Try translation
                if try_translation and attempt == 0:
                    logger.info(f"Preferred languages not found, trying translation...")
                    try:
                        transcript = available_transcripts[0]
                        for target_lang in ['hi', 'en']:
                            try:
                                if transcript.is_translatable:
                                    transcript = transcript.translate(target_lang)
                                    logger.info(f"Translated transcript to '{target_lang}'")
                                    break
                            except Exception as trans_error:
                                logger.warning(f"Translation to {target_lang} failed: {trans_error}")
                                continue
                    except Exception as e:
                        logger.error(f"Translation strategy failed: {e}")
                        raise NoTranscriptFound(video_id, languages, None)
                else:
                    raise
            
            # Try to fetch the actual transcript data
            try:
                transcript_data = transcript.fetch()
            except ParseError as pe:
                logger.warning(f"ParseError for {video_id} (attempt {attempt + 1}): {pe}")
                
                if attempt < max_retries:
                    logger.info(f"Retrying... ({attempt + 1}/{max_retries + 1})")
                    time.sleep(retry_delay)
                    continue
                else:
                    transcript_data = None
            
            # If we have data, process it
            if transcript_data:
                if not transcript_data:
                    logger.warning(f"Empty transcript data for {video_id}")
                    return {
                        'success': False,
                        'error': 'Transcript is empty. The video may not have any spoken content.'
                    }
                
                # Build full transcript text
                full_transcript = " ".join([segment['text'] for segment in transcript_data])
                full_transcript = re.sub(r'\s+', ' ', full_transcript).strip()
                
                if not full_transcript:
                    logger.warning(f"Transcript empty after processing for {video_id}")
                    return {
                        'success': False,
                        'error': 'Transcript is empty after processing.'
                    }

                logger.info(
                    f"✓ Successfully fetched transcript: "
                    f"{len(transcript_data)} segments, {len(full_transcript)} chars"
                )
                
                return {
                    'success': True, 
                    'transcript': full_transcript, 
                    'video_id': video_id, 
                    'language': transcript.language,
                    'language_code': transcript.language_code,
                    'is_generated': transcript.is_generated,
                    'segment_count': len(transcript_data)
                }
            
            # If no data after retries, try manual fetch
            if attempt >= max_retries:
                break
            
        except TranscriptsDisabled:
            logger.warning(f"Transcripts disabled for {video_id}")
            return {
                'success': False, 
                'error': 'Transcripts are disabled for this video by the creator.'
            }
            
        except NoTranscriptFound:
            available_info = []
            try:
                for t in available_transcripts:
                    available_info.append(
                        f"{t.language} ({'auto' if t.is_generated else 'manual'})"
                    )
            except:
                pass
            
            langs_list = ", ".join(available_info) if available_info else "None"
            error_msg = (
                f"Could not find transcript in requested languages ({', '.join(languages)}). "
                f"Available: {langs_list}"
            )
            
            logger.warning(error_msg)
            return {'success': False, 'error': error_msg}
            
        except VideoUnavailable:
            logger.warning(f"Video {video_id} is unavailable")
            return {
                'success': False, 
                'error': 'This video is unavailable, private, or has been removed.'
            }
            
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            
            if attempt < max_retries:
                time.sleep(retry_delay)
                continue
            break
    
    # Strategy 3: Manual fetch as last resort
    if try_manual_fetch:
        logger.info(f"All API methods failed, trying manual fetch...")
        
        for lang in ['hi', 'en', 'en-IN']:
            manual_data = try_manual_transcript_fetch(video_id, lang)
            if manual_data:
                full_transcript = " ".join([seg['text'] for seg in manual_data])
                full_transcript = re.sub(r'\s+', ' ', full_transcript).strip()
                
                if full_transcript:
                    logger.info(f"✓ Manual fetch successful with lang={lang}")
                    return {
                        'success': True,
                        'transcript': full_transcript,
                        'video_id': video_id,
                        'language': lang,
                        'segment_count': len(manual_data),
                        'method': 'manual'
                    }
    
    # All strategies failed
    logger.error(f"All strategies failed for {video_id}")
    return {
        'success': False,
        'error': (
            'Unable to fetch transcript after multiple attempts. '
            'The video may be too new, still processing, or experiencing temporary issues. '
            'Please try a different video or wait a few minutes.'
        )
    }


def check_transcript_availability(video_url_or_id: str) -> Dict[str, Any]:
    """Video ke liye transcript availability check karta hai."""
    video_id = extract_video_id(video_url_or_id)
    if not video_id:
        return {'available': False, 'error': 'Invalid video ID'}
    
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcripts_info = []
        
        for transcript in transcript_list:
            transcripts_info.append({
                'language': transcript.language,
                'language_code': transcript.language_code,
                'is_generated': transcript.is_generated,
                'is_translatable': transcript.is_translatable
            })
        
        return {
            'available': True,
            'video_id': video_id,
            'count': len(transcripts_info),
            'transcripts': transcripts_info
        }
        
    except Exception as e:
        return {
            'available': False,
            'video_id': video_id,
            'error': str(e)
        }