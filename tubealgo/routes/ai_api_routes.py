# tubealgo/routes/ai_api_routes.py

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from ..services.ai_service import generate_titles_and_tags, generate_description, generate_script_outline
from ..decorators import check_limits, RateLimitExceeded

ai_api_bp = Blueprint('ai_api', __name__, url_prefix='/manage/api')

@ai_api_bp.route('/generate-titles', methods=['POST'])
@login_required
def api_generate_titles():
    try:
        @check_limits(feature='ai_generation')
        def do_api_generation():
            data = request.json
            topic = data.get('topic')
            if not topic:
                return jsonify({'error': 'bad_request', 'message': 'Topic is required.'}), 400
            results = generate_titles_and_tags(current_user, topic)
            return jsonify(results)
        return do_api_generation()
    except RateLimitExceeded as e:
        return jsonify({'error': str(e), 'details': str(e)}), 429

@ai_api_bp.route('/generate-tags', methods=['POST'])
@login_required
def api_generate_tags():
    try:
        @check_limits(feature='ai_generation')
        def do_api_generation():
            data = request.json
            topic = data.get('topic')
            if not topic:
                return jsonify({'error': 'bad_request', 'message': 'Topic is required.'}), 400
            
            results = generate_titles_and_tags(current_user, topic, exclude_tags=[])

            if 'tags' in results and current_user.channel and current_user.channel.channel_title:
                channel_name_tag = current_user.channel.channel_title
                if isinstance(results.get('tags'), dict) and 'main_keywords' in results['tags']:
                    all_tags_lower = [tag.lower() for cat_tags in results['tags'].values() for tag in cat_tags]
                    if channel_name_tag.lower() not in all_tags_lower:
                        results['tags']['main_keywords'].insert(0, channel_name_tag)
            return jsonify(results)
        return do_api_generation()
    except RateLimitExceeded as e:
        return jsonify({'error': str(e), 'details': str(e)}), 429

@ai_api_bp.route('/generate-description', methods=['POST'])
@login_required
def api_generate_description():
    try:
        @check_limits(feature='ai_generation')
        def do_api_generation():
            data = request.json
            topic = data.get('topic')
            title = data.get('title')
            language = data.get('language', 'English')
            
            if not topic or not title:
                return jsonify({'error': 'Topic and title are required.'}), 400
                
            result = generate_description(current_user, topic, title, language)
            return jsonify(result)
        return do_api_generation()
    except RateLimitExceeded as e:
        return jsonify({'error': str(e), 'details': str(e)}), 429

# --- नया रूट यहाँ जोड़ा गया है ---
@ai_api_bp.route('/generate-script', methods=['POST'])
@login_required
def api_generate_script():
    try:
        @check_limits(feature='ai_generation')
        def do_api_generation():
            data = request.json
            topic = data.get('topic')
            language = data.get('language', 'English')
            if not topic:
                return jsonify({'error': 'Topic is required.'}), 400
            
            result = generate_script_outline(topic, language)
            return jsonify(result)
        return do_api_generation()
    except RateLimitExceeded as e:
        return jsonify({'error': str(e), 'details': str(e)}), 429