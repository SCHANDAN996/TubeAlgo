# tubealgo/services/ai_service.py

import os
import openai
import json
import traceback
from datetime import datetime
import google.generativeai as genai
# --- सुनिश्चित करें कि यह इम्पोर्ट यहाँ है, हालाँकि सीधे इस्तेमाल नहीं किया गया ---
# --- इसे कॉल करने वाली सर्विस (जैसे transcript_fetcher) को इसकी आवश्यकता होगी ---
from youtube_transcript_api import YouTubeTranscriptApi 
# --- ---
from .cache_manager import get_from_cache, set_to_cache
# --- video_fetcher शायद यहाँ आवश्यक नहीं है, इसे हटा सकते हैं यदि यह केवल get_ai_video_suggestions में इस्तेमाल होता है ---
# from .video_fetcher import get_latest_videos
# --- ---
from tubealgo.models import get_config_value, get_setting, APIKeyStatus, log_system_event
from tubealgo import db
import re # <-- रेगेक्स (regex) के लिए यह इम्पोर्ट ज़रूरी है

# Global variables for managing AI clients
gemini_keys = []
openai_client = None

def _mask_gemini_key(key):
    """Masks a Gemini API key for logging."""
    if isinstance(key, str) and len(key) > 8:
        return f"gemini_{key[:4]}...{key[-4:]}"
    return "invalid_gemini_key"

def initialize_ai_clients():
    """Initializes all AI clients once when the application starts."""
    global gemini_keys, openai_client
    
    gemini_keys_str = get_config_value('GEMINI_API_KEY', '')
    if gemini_keys_str:
        try:
            # First try loading as JSON list
            loaded_keys = json.loads(gemini_keys_str)
            if isinstance(loaded_keys, list):
                gemini_keys = [key.strip() for key in loaded_keys if key.strip()]
        except json.JSONDecodeError:
            # Fallback to comma-separated string if JSON fails
            gemini_keys = [key.strip() for key in gemini_keys_str.split(',') if key.strip()]
    
    if gemini_keys:
        print(f"INFO: Loaded {len(gemini_keys)} Gemini API keys from config.")

    openai_key = get_config_value('OPENAI_API_KEY')
    if openai_key:
        print("INFO: Initializing OpenAI Client.")
        openai_client = openai.OpenAI(api_key=openai_key)

def get_next_gemini_client():
    """
    Finds a valid, active Gemini key, configures the service, and returns it.
    Marks keys as 'exhausted' upon failure.
    """
    if not gemini_keys:
        return None

    all_key_identifiers = [_mask_gemini_key(key) for key in gemini_keys]
    
    exhausted_keys_query = APIKeyStatus.query.filter(
        APIKeyStatus.key_identifier.in_(all_key_identifiers),
        APIKeyStatus.status == 'exhausted'
    ).all()
    exhausted_identifiers = {k.key_identifier for k in exhausted_keys_query}

    active_keys_to_try = [key for key in gemini_keys if _mask_gemini_key(key) not in exhausted_identifiers]

    if not active_keys_to_try:
        log_system_event(
            message="All Gemini API keys are marked as exhausted.",
            log_type='ERROR',
            details={'keys_checked': all_key_identifiers}
        )
        return None

    for key in active_keys_to_try:
        try:
            genai.configure(api_key=key)
            selected_model_name = get_config_value('SELECTED_AI_MODEL', 'gemini-1.5-flash-latest')
            # --- जेनरेशन कॉन्फ़िगरेशन यहाँ जोड़ा गया ---
            generation_config = {
                "temperature": 0.7,
                "top_p": 1,
                "top_k": 1,
                "max_output_tokens": 8192, # या आपकी ज़रूरत के अनुसार
            }
            # --- सुरक्षा सेटिंग्स यहाँ जोड़ी गई ---
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            ]
            model = genai.GenerativeModel(
                selected_model_name,
                generation_config=generation_config, # <-- यहाँ पास करें
                safety_settings=safety_settings      # <-- यहाँ पास करें
            )
            
            # Test the key with a minimal call (वैकल्पिक, लेकिन अच्छा अभ्यास)
            # model.generate_content("test", generation_config={'max_output_tokens': 1})

            print(f"INFO: Successfully configured Gemini with key {_mask_gemini_key(key)}")
            return model # मॉडल ऑब्जेक्ट वापस भेजें
        except Exception as e:
            error_message = str(e).lower()
            key_identifier = _mask_gemini_key(key)
            
            if 'api_key_invalid' in error_message or 'permission_denied' in error_message or 'quota' in error_message or 'resource_exhausted' in error_message:
                log_system_event(
                    message=f"Gemini API Key {key_identifier} failed and will be marked as exhausted.",
                    log_type='QUOTA_EXCEEDED',
                    details={'reason': error_message}
                )
                
                key_status = APIKeyStatus.query.filter_by(key_identifier=key_identifier).first()
                if not key_status:
                    key_status = APIKeyStatus(key_identifier=key_identifier)
                    db.session.add(key_status)
                
                key_status.status = 'exhausted'
                key_status.last_failure_at = datetime.utcnow()
                db.session.commit()
            else:
                log_system_event(
                    message=f"An unexpected error occurred with Gemini key {key_identifier}",
                    log_type='ERROR',
                    details={'error': str(e), 'traceback': traceback.format_exc()}
                )
            
            continue # Try the next key
            
    return None


def generate_ai_response(system_prompt, user_prompt, is_json=False):
    """
    Generates a response from the AI, using the robust key management system.
    """
    gemini_model = get_next_gemini_client() # अब यह मॉडल ऑब्जेक्ट लौटाता है

    if gemini_model:
        try:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            if is_json:
                full_prompt += "\n\nIMPORTANT: Respond ONLY with a valid JSON object."
            
            response = gemini_model.generate_content(full_prompt) # मॉडल ऑब्जेक्ट का उपयोग करें
            
            if is_json:
                cleaned_text = response.text.strip().replace("```json", "").replace("```", "").strip()
                try:
                    # कभी-कभी AI अभी भी टेक्स्ट जोड़ देता है, JSON को निकालने का प्रयास करें
                    json_match = re.search(r'\{.*\}', cleaned_text, re.DOTALL)
                    if json_match:
                        cleaned_text = json_match.group(0)
                    return json.loads(cleaned_text)
                except json.JSONDecodeError as json_e:
                     log_system_event(
                         message="Gemini JSON parsing failed.",
                         log_type='ERROR',
                         details={'error': str(json_e), 'raw_response': cleaned_text[:500]} # लॉग में कच्चा रिस्पॉन्स देखें
                     )
                     # OpenAI फॉलबैक पर जाने दें
            else:
                return response.text
        
        except Exception as e:
            log_system_event(
                message="Gemini generation failed even with a selected client.",
                log_type='ERROR',
                details={'error': str(e), 'traceback': traceback.format_exc()}
            )
            # OpenAI फॉलबैक पर जाने दें

    # Fallback to OpenAI if configured and Gemini failed
    if openai_client:
        try:
            print("INFO: Gemini failed or not available, falling back to OpenAI.")
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            response_format = {"type": "json_object"} if is_json else {"type": "text"}
            
            # सुनिश्चित करें कि आपके पास नवीनतम openai लाइब्रेरी है
            # पुराने संस्करणों में response_format अलग हो सकता है
            response = openai_client.chat.completions.create(
                model="gpt-4o", # या जो भी मॉडल आप उपयोग करना चाहते हैं
                messages=messages,
                response_format=response_format
            )
            content = response.choices[0].message.content
            return json.loads(content) if is_json else content
        except Exception as e:
            log_system_event(
                message="OpenAI fallback generation also failed.",
                log_type='ERROR',
                details={'error': str(e), 'traceback': traceback.format_exc()}
            )

    # If both failed
    final_error_message = 'No AI provider is configured or all API keys failed. Please check your keys.'
    log_system_event(final_error_message, 'CRITICAL') # इसे गंभीर रूप से लॉग करें
    return {'error': final_error_message} if is_json else f"Error: {final_error_message}"


def generate_idea_set(topic, language='English', description=None, video_type='any'):
    default_system_prompt = (
        "You are a world-class YouTube content strategist and scriptwriter. Your task is to generate a set of 3 creative, distinct, and engaging video ideas based on a user's topic. Each idea must come with a full script outline."
    )
    system_prompt = get_setting('prompt_generate_ideas', default_system_prompt)

    video_type_instruction = ""
    if video_type == 'short':
        video_type_instruction = "The user wants ideas for a **Short Video** (under 60 seconds, vertical format). The title should be very catchy and the script outline must be extremely concise, fast-paced, with a strong hook and a quick payoff."
    elif video_type == 'long':
        video_type_instruction = "The user wants ideas for a **Long Video** (standard 8-15 minute format). The script outline should be detailed, with multiple sections, talking points, and clear visual cues."
    
    if language.lower() == 'hindi':
        lang_instruction = "IMPORTANT: The entire output (all titles and script outlines) must be in pure Hindi (Devanagari script)."
    elif language.lower() == 'mix':
        lang_instruction = "IMPORTANT: The entire output must be in a mix of Hindi (Devanagari script) and English. Use technical terms in English and explanations in Hindi."
    elif language.lower() == 'hinglish':
        lang_instruction = "IMPORTANT: The entire output must be in Hinglish (a mix of Hindi and English, written in the Latin script, like 'Fan bending ka issue kaise solve karein')."
    else: 
        lang_instruction = "IMPORTANT: The entire output must be in English."
    
    description_context = ""
    if description and description.strip():
        description_context = f"The user has provided these additional details about their idea: '{description}'. Use these details to make the ideas more specific and relevant."
    
    user_prompt = (
        f"My video topic is: '{topic}'.\n"
        f"{description_context}\n"
        f"{video_type_instruction}\n\n"
        f"{lang_instruction}\n\n"
        "Please generate an array of exactly 3 unique video ideas. Each idea in the array should be a JSON object with two keys:\n"
        "1.  `title`: A catchy, viral-potential YouTube title for the video. Include 1-2 relevant emojis in the title.\n"
        "2.  `outline`: A complete, well-structured script outline in Markdown format. The outline MUST start directly with the 'Intro Hook' and MUST NOT repeat the title from the `title` key. Use emojis strategically (e.g., 훅 Intro, 💡 Main Points, 🎬 Visual, 🗣️ Host, ✅ Call to Action, 👋 Outro) to make the outline visually appealing and easy to scan. Use Markdown headings (like `### Main Talking Points`) for sections.\n\n"
        "The script outline must include these sections: 'Intro Hook', 'Main Talking Points' with visual cues, a 'Call to Action', and an 'Outro'.\n\n"
        "Return your response as a single, valid JSON object with a single top-level key: `ideas`. The value of `ideas` should be the array of the 3 idea objects."
    )
    
    return generate_ai_response(system_prompt, user_prompt, is_json=True)

# --- NEW FUNCTION FOR RETENTION INSIGHTS ---
# (यह फ़ंक्शन जैसा था वैसा ही रहता है)
def generate_retention_insights(retention_data, dips, spikes, video_duration, transcript):
    """
    Analyzes retention data and transcript to generate actionable insights.
    """
    system_prompt = (
        "You are a world-class YouTube video editor and content strategist. Your task is to analyze a video's audience retention data and its transcript to provide concise, actionable feedback. The user wants to know WHY viewers are dropping off or rewatching certain parts."
    )

    intro_retention_point = min(30, len(retention_data) - 1) if retention_data else 0
    intro_retention = retention_data[intro_retention_point] * 100 if retention_data and intro_retention_point < len(retention_data) else 0
    
    key_moments_summary = f"- Intro Performance: Retained {intro_retention:.0f}% of viewers around the 30% mark.\n"
    
    if dips:
        key_moments_summary += "- Significant Dips (Viewers Leaving):\n"
        for dip in dips[:3]:
            percentage = dip.get('x', 0) # Use .get() for safety
            time_in_seconds = (percentage / 100) * video_duration if video_duration else 0
            minutes = int(time_in_seconds // 60)
            seconds = int(time_in_seconds % 60)
            key_moments_summary += f"  - At {minutes}:{seconds:02d} ({percentage}% into the video)\n"
    
    if spikes:
        key_moments_summary += "- Key Spikes (Most Re-watched Parts):\n"
        for spike in spikes[:2]:
            percentage = spike.get('x', 0) # Use .get() for safety
            time_in_seconds = (percentage / 100) * video_duration if video_duration else 0
            minutes = int(time_in_seconds // 60)
            seconds = int(time_in_seconds % 60)
            key_moments_summary += f"  - At {minutes}:{seconds:02d} ({percentage}% into the video)\n"

    user_prompt = (
        "Analyze the following YouTube video data.\n\n"
        f"KEY MOMENTS FROM RETENTION GRAPH:\n{key_moments_summary}\n\n"
        f"FULL VIDEO TRANSCRIPT (Excerpt):\n---\n{transcript[:8000]}\n---\n\n" # Limit transcript length
        "Based on ALL the data above, provide a JSON object with a key 'insights' which is an array of 2-3 concise objects. Each object must have 'type' ('good', 'bad', or 'info'), 'icon' (a relevant Font Awesome icon class like 'fa-solid fa-thumbs-up', 'fa-solid fa-arrow-trend-down', 'fa-solid fa-repeat'), and 'text' (a short, actionable insight explaining the WHY behind a key moment by referencing the transcript content around that time. Be specific!). Focus only on the most impactful moments identified above."
    )

    return generate_ai_response(system_prompt, user_prompt, is_json=True)

# (यह फ़ंक्शन जैसा था वैसा ही रहता है)
def get_ai_video_suggestions(user, user_videos=None):
    # --- video_fetcher को यहाँ इम्पोर्ट करें यदि आवश्यक हो ---
    from tubealgo.services.video_fetcher import get_latest_videos
    # --- ---
    from tubealgo.models import Competitor # मॉडल्स को अंदर इम्पोर्ट करना अच्छा नहीं है, लेकिन आपके कोड में था
    if not user.competitors.first():
        return {'error': 'Please add at least one competitor to generate AI suggestions.'}
    cache_key = f"ai_suggestions_v2:{user.id}"
    cached_data = get_from_cache(cache_key)
    if cached_data: return cached_data
    try:
        competitors = user.competitors.order_by(Competitor.position).limit(5).all()
        # --- यहाँ से video_fetcher इम्पोर्ट हटा दिया गया है ---
        all_videos_data = [get_latest_videos(c.channel_id_youtube, 5) for c in competitors]
        all_videos = [v for data in all_videos_data for v in data.get('videos', [])]
        if not all_videos: return {'error': 'Could not fetch competitor videos.'}
        successful_videos = sorted(all_videos, key=lambda x: x.get('view_count', 0), reverse=True)[:5]
        if not successful_videos: return {'error': 'Not enough data to analyze.'}
        prompt_context = "Here is a list of successful videos from competitors:\n\n"
        for i, video in enumerate(successful_videos, 1):
            prompt_context += (f"- Title: {video.get('title')}\n- Views: {video.get('view_count', 0):,}\n") # सुरक्षित एक्सेस के लिए .get() का उपयोग करें
        system_prompt = "You are an expert YouTube growth strategist."
        user_prompt = (f"{prompt_context}\n\nAnalyze these videos. Generate exactly 3 unique and compelling video ideas for my channel. For each idea, provide a catchy 'title' and a one-sentence 'description'. Return the output as a JSON object with a key 'suggestions' which is an array of objects.")
        response_data = generate_ai_response(system_prompt, user_prompt, is_json=True)
        if isinstance(response_data, dict) and 'error' in response_data: return response_data # एरर को ठीक से हैंडल करें
        final_suggestions = response_data.get("suggestions", []) if isinstance(response_data, dict) else [] # सुरक्षित एक्सेस
        set_to_cache(cache_key, final_suggestions, expire_hours=24)
        return final_suggestions
    except Exception as e:
        log_system_event("Failed to generate AI video suggestions", "ERROR", {'user_id': user.id, 'error': str(e), 'traceback': traceback.format_exc()})
        return {'error': f'Could not generate AI suggestions.'}

# (यह फ़ंक्शन जैसा था वैसा ही रहता है)
def generate_titles_and_tags(user, topic, exclude_tags=None):
    default_system_prompt = "You are a world-class YouTube viral title expert and SEO strategist. Your task is to generate a ranked list of title suggestions and categorized tags based on a user's topic."
    system_prompt = get_setting('prompt_titles_and_tags', default_system_prompt)

    user_prompt = (
        f"Analyze the user's video topic: '{topic}'.\n\n"
        "PART 1: TITLE GENERATION\n"
        "Generate an array of 10 unique title objects. You MUST rank them from best to worst based on their potential for virality, CTR, and SEO.\n"
        "Each title object must have three keys:\n"
        "1. 'title': A catchy, compelling video title. MUST include 1-2 relevant emojis.\n"
        "2. 'score': An integer score from 80 to 100, representing its overall effectiveness. The best title should have the highest score.\n"
        "3. 'strengths': An array of 2-3 short, powerful strings explaining why the title is good. Use professional terms from this list ONLY: 'High CTR', 'SEO Friendly', 'Sparks Curiosity', 'Emotional Hook', 'Urgency', 'Viral Potential', 'Strong Hook', 'Clear Benefit'.\n\n"
        
        "PART 2: TAG GENERATION\n"
        "Generate a JSON object for SEO tags with three keys:\n"
        "1. 'main_keywords': An array of 2-3 most critical, high-volume tags for the main topic.\n"
        "2. 'secondary_keywords': An array of 7-10 related LSI (Latent Semantic Indexing) tags that provide context.\n"
        "3. 'broad_tags': An array of 3-5 general category tags.\n\n"
        "FINAL OUTPUT:\n"
        "Return a single, valid JSON object with two top-level keys: 'titles' (containing the array of title objects) and 'tags' (containing the tag object with its categories)."
    )
    
    return generate_ai_response(system_prompt, user_prompt, is_json=True)

# (यह फ़ंक्शन जैसा था वैसा ही रहता है, लेकिन यूजर ऑब्जेक्ट पास किया गया है)
def generate_description(user, topic, title, language='English'):
    defaults_context = "Use the following user-provided details to personalize the description. If a detail is not provided, DO NOT mention it.\n"
    has_defaults = False
    if hasattr(user, 'default_channel_name') and user.default_channel_name: # सुरक्षित एक्सेस
        defaults_context += f"- Channel Name: {user.default_channel_name}\n"
        has_defaults = True
    if hasattr(user, 'default_social_handles') and user.default_social_handles: # सुरक्षित एक्सेस
        defaults_context += f"- Social Media Links:\n{user.default_social_handles}\n"
        has_defaults = True
    if hasattr(user, 'default_contact_info') and user.default_contact_info: # सुरक्षित एक्सेस
        defaults_context += f"- Contact Info: {user.default_contact_info}\n"
        has_defaults = True

    if not has_defaults:
        defaults_context = "" 

    default_system_prompt = "You are a world-class YouTube SEO expert. Your task is to write a highly-optimized YouTube description following a professional structure."
    system_prompt = get_setting('prompt_description', default_system_prompt)

    user_prompt = (
        f"My video title is: '{title}'\nThe main topic is: '{topic}'\nThe requested language for the output is: {language}\n\n{defaults_context}\n"
        "Generate a new, unique, and well-structured YouTube description (at least 200 words). The description MUST follow this professional format:\n\n"
        "1. **Compelling Hook (First 2-3 lines):** Start with a strong hook that grabs the viewer's attention, uses keywords from the title, and makes them want to watch.\n\n"
        "2. **Detailed Summary:** Write a detailed paragraph summarizing the video's content. Naturally include important keywords from the topic. Use emojis to break up text and make it easy to read.\n\n"
        "3. **Timestamps:** Provide a template with 3-5 logical chapter timestamps based on the topic. Use the format '(00:00) Chapter Title'. The user will edit the exact times later.\n\n"
        "4. **Call to Action (CTA):** Include a clear call to subscribe to the channel and a placeholder encouraging viewers to watch another relevant video (e.g., '📺 Watch Next: [Link to Your Other Video]').\n\n"
        "5. **User's Links:** (If provided in the context) Add a section for the user's social media and contact info under a clear heading like '🔗 Connect with Me' or 'Follow Us'.\n\n"
        "6. **Relevant Hashtags:** End with a list of 3-5 relevant #hashtags on new lines. The hashtags should be single words and relevant to the video topic.\n\n"
        "Return the entire, perfectly formatted description as a single string."
    )
    
    description_text = generate_ai_response(system_prompt, user_prompt, is_json=False)
    # एरर हैंडलिंग जोड़ें
    if isinstance(description_text, dict) and 'error' in description_text:
        return description_text
    return {'description': description_text}

# (यह फ़ंक्शन जैसा था वैसा ही रहता है)
def generate_script_outline(video_title, language='English'):
    """This function is a wrapper for generate_idea_set for backward compatibility."""
    idea_set = generate_idea_set(topic=video_title, language=language)
    if isinstance(idea_set, dict) and 'ideas' in idea_set and len(idea_set['ideas']) > 0: # सुरक्षित एक्सेस
        return {'outline': idea_set['ideas'][0]['outline']}
    elif isinstance(idea_set, dict) and 'error' in idea_set: # सुरक्षित एक्सेस
        return {'error': idea_set['error']}
    return {'error': 'Could not generate a script outline.'}

# (यह फ़ंक्शन जैसा था वैसा ही रहता है)
def generate_motivational_suggestion(video_title):
    system_prompt = "You are a YouTube growth strategist. Your goal is to provide creative, motivational video ideas in Hindi, formatted for a Telegram message."
    user_prompt = (f"My competitor had success with a video titled: '{video_title}'.\n\nBased on this topic, do the following in a friendly, motivational tone:\n1. Generate 2 alternative, more engaging, video titles for me in Hindi.\n2. Provide one short, actionable 'Pro Tip' in English with Hindi translation for making the video better.\nFormat the output as a single string for a Telegram message, using Markdown (*bold*). Start with a motivational sentence.")
    return generate_ai_response(system_prompt, user_prompt, is_json=False)

# (यह फ़ंक्शन जैसा था वैसा ही रहता है)
def generate_playlist_suggestions(user, user_playlists_titles, competitor_video_titles, limit=3):
    if not competitor_video_titles:
        return {'error': 'Not enough competitor data to generate suggestions.'}
    channel_name = user.channel.channel_title if hasattr(user, 'channel') and user.channel else "my channel" # सुरक्षित एक्सेस
    system_prompt = f"You are a YouTube expert specializing in content strategy. Your client's channel name is '{channel_name}'."
    user_prompt = (f"My existing playlists:\n- {'\n- '.join(user_playlists_titles)}\n\nPopular video titles from my competitors:\n- {'\n- '.join(competitor_video_titles[:20])}\n\nSuggest exactly {limit} new playlist ideas that I don't already have.\nFor each idea, provide a catchy, SEO-friendly 'title' and a detailed 'description' (100-150 words).\n\nReturn the output as a single, valid JSON object with a key 'suggestions', which is an array of objects. Each object must have 'title' and 'description' keys.")
    return generate_ai_response(system_prompt, user_prompt, is_json=True)

# (यह फ़ंक्शन जैसा था वैसा ही रहता है)
def generate_idea_from_competitor(title):
    """
    Takes a competitor's video title and generates a new, unique idea from it.
    """
    system_prompt = "You are a creative YouTube content strategist. Your task is to take a competitor's successful video title and generate a new, unique, and more engaging video title on the same topic for my channel. The new title should be a fresh take, not a direct copy or simple rephrase. Add 1-2 relevant emojis."
    
    user_prompt = (f"A competitor had success with this video title: '{title}'.\n\n"
                   "Generate one new, unique, and engaging title for my own video on this topic.\n\n"
                   "Return your response as a single, valid JSON object with one key: `new_title`.")

    return generate_ai_response(system_prompt, user_prompt, is_json=True)

# --- Transcript Analysis Functions ---
# (_split_text फ़ंक्शन जैसा था वैसा ही रहता है)
def _split_text(text, max_length=4000, overlap=200):
    """Splits long text into overlapping chunks."""
    if len(text) <= max_length:
        yield text
        return
    
    start = 0
    while start < len(text):
        end = start + max_length
        # Find a natural break point (like a period or newline) near the end
        break_point = text.rfind('.', start + max_length - overlap, end)
        if break_point == -1:
             break_point = text.rfind('\n', start + max_length - overlap, end)
        if break_point == -1 or break_point < start + overlap: # If no good break found or it's too early
            break_point = end # Just cut at max_length

        yield text[start:break_point]
        
        # Move start to the beginning of the overlap for the next chunk
        # Find the start of the sentence *after* the overlap point
        next_start = text.find('.', start + max_length - overlap)
        if next_start == -1:
             next_start = text.find('\n', start + max_length - overlap)
        
        # If no sentence break found, or if it results in a very small next chunk,
        # just use the standard overlap.
        if next_start == -1 or (len(text) - (next_start + 1)) < overlap:
             start = start + max_length - overlap
        else:
            start = next_start + 1 # Start after the period/newline

        # Avoid infinite loop if overlap logic fails
        if start <= (start + max_length - overlap):
            start = start + max_length - overlap # Fallback to ensure progress


# (यह फ़ंक्शन जैसा था वैसा ही रहता है)
def analyze_transcript_with_ai(transcript):
    """
    Analyzes a video transcript using chunking for long videos.
    """
    
    # Direct analysis for short transcripts
    if len(transcript) < 4500:
        print("INFO: Transcript is short. Performing direct analysis.")
        system_prompt = "You are an expert YouTube content strategist. Your task is to analyze a video transcript and provide actionable insights in a structured format."
        user_prompt = (
            f"Please analyze the following YouTube video transcript:\n\n---\n{transcript}\n---\n\n"
            "Based on the transcript, provide the following in a structured JSON format:\n"
            "1. `summary`: A concise, one-paragraph summary of the main topics discussed in the video.\n"
            "2. `keywords`: An array of the top 5-7 most important keywords or key phrases mentioned.\n"
            "3. `content_gaps`: An array of 3 distinct, actionable video ideas that could be created as a follow-up. These ideas should cover topics that the original video mentioned briefly but did not cover in detail, or are logical next steps for a viewer interested in this topic. Each idea should be a string.\n\n"
            "Return a single, valid JSON object with only the keys `summary`, `keywords`, and `content_gaps`."
        )
        return generate_ai_response(system_prompt, user_prompt, is_json=True)

    # Chunking process for long transcripts
    print(f"INFO: Transcript is long ({len(transcript)} chars). Starting chunking process.")
    chunks = list(_split_text(transcript))
    summaries = []

    # Step 1: Summarize each chunk
    summary_system_prompt = "You are a text summarization expert. Summarize the following text, focusing on the key points and topics. Be concise."
    for i, chunk in enumerate(chunks):
        print(f"Summarizing chunk {i+1}/{len(chunks)}...")
        summary_user_prompt = f"Please summarize this piece of a video transcript:\n\n{chunk}"
        chunk_summary = generate_ai_response(summary_system_prompt, summary_user_prompt, is_json=False)
        if isinstance(chunk_summary, str) and 'error' not in chunk_summary.lower(): # एरर की जाँच करें
            summaries.append(chunk_summary)
        else:
             log_system_event("Transcript chunk summarization failed.", "ERROR", {'chunk_index': i, 'error': chunk_summary})
             return {'error': 'Failed to summarize a part of the transcript.'} # यहाँ एरर लौटाएँ
    
    combined_summary = "\n\n".join(summaries)
    print("INFO: All chunks summarized. Performing final analysis on combined summary.")

    # Step 2: Final analysis on the combined summary
    final_system_prompt = "You are an expert YouTube content strategist. You will be given a detailed summary compiled from different parts of a long video transcript. Your task is to analyze this summary and provide actionable insights."
    final_user_prompt = (
        f"Here is a comprehensive summary of a long video:\n\n---\n{combined_summary}\n---\n\n"
        "Based on this complete summary, provide the following in a structured JSON format:\n"
        "1. `summary`: A final, polished, one-paragraph summary of the entire video's content.\n"
        "2. `keywords`: An array of the top 5-7 most important keywords or key phrases from the entire video.\n"
        "3. `content_gaps`: An array of 3 distinct, actionable video ideas based on the *entire* video's context. These ideas should identify topics that were likely only touched upon briefly or suggest valuable follow-up content.\n\n"
        "Return a single, valid JSON object with only the keys `summary`, `keywords`, and `content_gaps`."
    )
    
    return generate_ai_response(final_system_prompt, final_user_prompt, is_json=True)

# (यह फ़ंक्शन जैसा था वैसा ही रहता है)
def generate_comment_reply(comment_text):
    """
    Generates engaging reply suggestions for a given YouTube comment.
    """
    system_prompt = (
        "You are a helpful and friendly YouTube channel manager. Your goal is to generate positive and engaging replies to user comments. "
        "The replies should be concise, encourage further conversation, and maintain a positive community tone. "
        "Provide a few different styles of replies: a simple thank you, a reply with a question, and a slightly more detailed one if possible."
    )
    
    user_prompt = (
        f"A viewer left this comment: \"{comment_text}\"\n\n"
        "Please generate an array of 3 distinct, potential replies in JSON format under the key 'suggestions'. "
        "Each reply in the array must be a string.\n"
        "Example format: {\"suggestions\": [\"Thanks so much! 😊\", \"Glad you enjoyed it! What was your favorite part?\", \"That's a great point, thanks for sharing your thoughts!\"]}"
    )
    
    return generate_ai_response(system_prompt, user_prompt, is_json=True)

# --- === === === === === === === === === === === ---
# --- === नए ट्रांसक्रिप्ट प्रोसेसिंग फ़ंक्शंस === ---
# --- === === === === === === === === === === === ---

def format_transcript_for_voiceover(raw_transcript: str) -> str:
    """
    Cleans a raw transcript and formats it for a voice-over artist.
    Fixes punctuation, grammar, and removes filler words.
    """
    system_prompt = """
    You are a professional video script editor. Your task is to take a raw, unformatted YouTube transcript and turn it into a clean, easy-to-read voice-over script.

    RULES:
    1.  Correct any spelling mistakes and grammatical errors.
    2.  Add proper punctuation (commas, periods, etc.) to create natural-sounding sentences.
    3.  Remove filler words (like "um," "ah," "you know," "like") and repeated stutters.
    4.  Combine short, choppy sentences into longer, more coherent paragraphs.
    5.  Do NOT change the core meaning or the speaker's original words, just clean them up.
    6.  The final output should be a single block of text, formatted into paragraphs, ready for recording.
    """
    
    # छोटे ट्रांसक्रिप्ट के लिए सीधे कॉल करें, लंबे के लिए चंक करें
    if len(raw_transcript) < 8000: # सीमा थोड़ी बढ़ा दी गई है
        user_prompt = f"""
        RAW TRANSCRIPT:
        "{raw_transcript}" 

        Cleaned Voice-Over Script:
        """
        response = generate_ai_response(system_prompt, user_prompt, is_json=False)
        return response if isinstance(response, str) else f"AI Error: {response.get('error', 'Unknown error')}"
    else:
        # लंबे ट्रांसक्रिप्ट के लिए चंकिंग (सरल संस्करण)
        print(f"INFO: Formatting long transcript ({len(raw_transcript)} chars) for voiceover using chunking.")
        chunks = list(_split_text(raw_transcript, max_length=7500, overlap=300)) # चंक साइज़ समायोजित करें
        processed_chunks = []
        for i, chunk in enumerate(chunks):
            print(f"Processing voiceover chunk {i+1}/{len(chunks)}...")
            chunk_user_prompt = f"""
            RAW TRANSCRIPT CHUNK:
            "{chunk}" 

            Cleaned Voice-Over Script Chunk (Maintain context from potential previous/next chunk):
            """
            processed_chunk = generate_ai_response(system_prompt, chunk_user_prompt, is_json=False)
            if isinstance(processed_chunk, str) and 'error' not in processed_chunk.lower():
                processed_chunks.append(processed_chunk)
            else:
                log_system_event("Voiceover chunk processing failed.", "ERROR", {'chunk_index': i, 'error': processed_chunk})
                return f"AI Error: Failed to process part of the transcript for voiceover. Error: {processed_chunk.get('error', 'Unknown error') if isinstance(processed_chunk, dict) else processed_chunk}"
        
        # चंक्स को समझदारी से जोड़ें (उदाहरण के लिए, पैराग्राफ ब्रेक्स पर)
        full_voiceover = "\n\n".join(processed_chunks) 
        print("INFO: Voiceover chunks processed and combined.")
        return full_voiceover


def convert_transcript_to_script(raw_transcript: str) -> str:
    """
    Converts a raw transcript into a full "Script-to-Screen" document
    with visual cues and voice-over text.
    """
    system_prompt = """
    You are an expert YouTube video director and scriptwriter. Your job is to convert a raw voice-over transcript into a full-fledged video script.
    
    You must analyze the transcript and, for each logical section, create two parts:
    1.  **VISUALS (क्या दिखाना है):** Describe the visuals that should be on screen. Be specific (e.g., "B-roll of coffee beans," "Host speaking to camera," "Text overlay: '3 Simple Tips'").
    2.  **VOICE-OVER (क्या बोलना है):** The corresponding part of the cleaned-up transcript.

    Format the output STRICTLY using Markdown:

    ---
    **VISUALS:** [Visual description here]
    **VOICE-OVER:** [Voice-over text here]
    ---
    **VISUALS:** [Next visual description]
    **VOICE-OVER:** [Next part of the voice-over]
    ---
    
    (Continue this pattern for the entire script)
    """

    # छोटे ट्रांसक्रिप्ट के लिए सीधे कॉल करें, लंबे के लिए चंक करें
    if len(raw_transcript) < 8000:
        user_prompt = f"""
        RAW TRANSCRIPT:
        "{raw_transcript}"

        Full Video Script:
        """
        response = generate_ai_response(system_prompt, user_prompt, is_json=False)
        return response if isinstance(response, str) else f"AI Error: {response.get('error', 'Unknown error')}"
    else:
         # लंबे ट्रांसक्रिप्ट के लिए चंकिंग (सरल संस्करण)
        print(f"INFO: Converting long transcript ({len(raw_transcript)} chars) to script using chunking.")
        chunks = list(_split_text(raw_transcript, max_length=7500, overlap=300)) # चंक साइज़ समायोजित करें
        script_chunks = []
        for i, chunk in enumerate(chunks):
            print(f"Processing script chunk {i+1}/{len(chunks)}...")
            chunk_user_prompt = f"""
            RAW TRANSCRIPT CHUNK:
            "{chunk}"

            Full Video Script Chunk (Maintain context and formatting. End cleanly if possible, ready to merge with next chunk):
            """
            processed_chunk = generate_ai_response(system_prompt, chunk_user_prompt, is_json=False)
            if isinstance(processed_chunk, str) and 'error' not in processed_chunk.lower():
                script_chunks.append(processed_chunk.strip()) # अतिरिक्त स्पेस हटा दें
            else:
                log_system_event("Script conversion chunk processing failed.", "ERROR", {'chunk_index': i, 'error': processed_chunk})
                return f"AI Error: Failed to process part of the transcript for script conversion. Error: {processed_chunk.get('error', 'Unknown error') if isinstance(processed_chunk, dict) else processed_chunk}"

        # चंक्स को जोड़ें, डुप्लिकेट सेपरेटर से बचें
        full_script = ""
        for chunk in script_chunks:
            if full_script and not full_script.endswith("\n---") and chunk.startswith("---"):
                 full_script += "\n" + chunk # सुनिश्चित करें कि सेपरेटर डुप्लिकेट न हो
            elif full_script and not full_script.endswith("\n---\n") and not chunk.startswith("---"):
                 full_script += "\n\n---\n\n" + chunk # यदि आवश्यक हो तो सेपरेटर डालें
            elif not full_script:
                 full_script = chunk # पहला चंक
            else:
                 full_script += "\n" + chunk # सामान्य जोड़
                 
        print("INFO: Script chunks processed and combined.")
        return full_script


def get_ai_processed_transcript(raw_transcript):
    """Fetches all AI versions of a transcript."""
    # यहाँ एरर हैंडलिंग जोड़ना महत्वपूर्ण है
    try:
        voiceover_script = format_transcript_for_voiceover(raw_transcript)
        # यदि पहला कॉल विफल होता है, तो दूसरा न चलाएं और एरर लौटाएं
        if isinstance(voiceover_script, str) and "AI Error:" in voiceover_script:
             return {
                 'voiceover': voiceover_script,
                 'script': voiceover_script # एरर दोनों में दिखाएं
             }

        full_script = convert_transcript_to_script(raw_transcript)
        if isinstance(full_script, str) and "AI Error:" in full_script:
             return {
                 'voiceover': voiceover_script, # वॉयसओवर सफल हो सकता है
                 'script': full_script # स्क्रिप्ट में एरर दिखाएं
             }

        return {
            'voiceover': voiceover_script,
            'script': full_script
        }
    except Exception as e:
        log_system_event("Critical error during AI transcript processing", "CRITICAL", {'error': str(e), 'traceback': traceback.format_exc()})
        error_msg = f"AI Error: A critical error occurred during processing: {str(e)}"
        return {
            'voiceover': error_msg,
            'script': error_msg
        }