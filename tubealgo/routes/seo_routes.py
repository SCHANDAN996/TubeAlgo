# tubealgo/routes/seo_routes.py
"""
SEO Score Tool Routes
Video SEO analysis ke liye endpoints
"""

from flask import Blueprint, render_template, request, jsonify, current_app, Response
from flask_login import login_required, current_user
from tubealgo.models.youtube_models import Video, YouTubeChannel
from tubealgo.services.seo_analyzer import SEOScoreAnalyzer, get_video_seo_score
from tubealgo.services.youtube_fetcher import get_full_video_details
from tubealgo.services.fetcher_utils import parse_iso_duration
from ..routes.utils import sanitize_filename
from tubealgo import db
import logging
from datetime import datetime
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False

# --- नया इम्पोर्ट ---
import requests
import json
# --- बदलाव खत्म ---


logger = logging.getLogger(__name__)

# === बदलाव: API के लिए ब्लूप्रिंट (प्रीफिक्स के साथ) ===
seo_bp = Blueprint('seo', __name__, url_prefix='/api/seo')

# === बदलाव: UI पेज के लिए ब्लूप्रिंट (बिना प्रीफिक्स के) ===
seo_ui_bp = Blueprint('seo_ui', __name__)


# --- UI Route (अब 'seo_ui_bp' का उपयोग कर रहा है) --
@seo_ui_bp.route('/tools/seo-analyzer')
@login_required
def seo_analyzer_page():
    """SEO Score Tool ka main page"""
    user_videos = []
    if current_user.channel:
        user_videos = Video.query.filter_by(
            channel_id=current_user.channel.id
        ).order_by(
            Video.last_analyzed.desc().nullslast(),
            Video.published_at.desc()
        ).limit(6).all()
        
    return render_template('seo_analyzer.html', videos=user_videos)


# --- API Routes (अब 'seo_bp' का उपयोग कर रहे हैं) ---

@seo_bp.route('/analyze-video', methods=['POST'])
@login_required
def analyze_video():
    """Single video ka SEO analyze karo"""
    data = request.json
    video_id = data.get('video_id')
    refresh = data.get('refresh', False)
    
    if not video_id:
        return jsonify({'success': False, 'error': 'Video ID is required'}), 400
    
    try:
        # 1. Check database first
        video = Video.query.filter_by(video_id=video_id).first()
        
        # 2. If refresh=True or not in DB or not analyzed, fetch from YouTube
        if refresh or not video or not video.last_analyzed:
            gemini_key = current_app.config.get('GEMINI_API_KEY')
            if not gemini_key:
                logger.error("GEMINI_API_KEY is not configured.")
                return jsonify({'success': False, 'error': 'AI configuration error on server.'}), 500

            # Fetch fresh data
            video_details = get_full_video_details(video_id)
            if not video_details:
                return jsonify({'success': False, 'error': 'Could not fetch video details from YouTube.'}), 404

            # Prepare data for analyzer
            video_data = {
                'title': video_details.get('title', ''),
                'description': video_details.get('description', ''),
                'tags': video_details.get('tags', []),
                'duration': parse_iso_duration(video_details.get('duration', 'PT0M0S')),
                'thumbnail': video_details['thumbnails'].get('high', {}).get('url', ''),
                'view_count': int(video_details['statistics'].get('viewCount', 0)),
                'like_count': int(video_details['statistics'].get('likeCount', 0)),
                'comment_count': int(video_details['statistics'].get('commentCount', 0)),
                'published_at': video_details.get('publishedAt'),
                'has_captions': video_details.get('has_captions', False)
            }
            
            # Run analyzer
            analyzer = SEOScoreAnalyzer(gemini_key)
            seo_result = analyzer.calculate_video_seo_score(video_data)
            
            if not seo_result.get('success'):
                return jsonify({'success': False, 'error': seo_result.get('error', 'Analysis failed')}), 500

            # Save/Update in DB
            if not video:
                channel_db = YouTubeChannel.query.filter_by(user_id=current_user.id).first()
                
                video = Video(
                    video_id=video_id,
                    user_id=current_user.id, # Link to the user who analyzed it
                    channel_id=channel_db.id if channel_db and video_details.get('channelId') == channel_db.channel_id_youtube else None
                )
                db.session.add(video)

            # Update video fields
            video.title = video_data['title']
            video.description = video_data['description']
            video.tags = video_data['tags']
            video.thumbnail_url = video_data['thumbnail']
            video.published_at = datetime.fromisoformat(video_data['published_at'].replace('Z', '+00:00'))
            video.duration = video_data['duration']
            video.view_count = video_data['view_count']
            video.like_count = video_data['like_count']
            video.comment_count = video_data['comment_count']
            video.has_captions = video_data['has_captions']
            
            # Update SEO fields
            video.seo_score = seo_result.get('score')
            video.seo_grade = seo_result.get('grade')
            video.last_analyzed = datetime.utcnow()
            
            db.session.commit()

        else:
            # 3. If in DB and analyzed, use cached score
            gemini_key = current_app.config.get('GEMINI_API_KEY')
            video_data = {
                'title': video.title or '',
                'description': video.description or '',
                'tags': video.tags or [],
                'duration': video.duration or 0,
                'thumbnail': video.thumbnail_url or '',
                'view_count': video.view_count or 0,
                'like_count': video.like_count or 0,
                'comment_count': video.comment_count or 0,
                'published_at': video.published_at.isoformat() if video.published_at else None,
                'has_captions': video.has_captions or False
            }
            analyzer = SEOScoreAnalyzer(gemini_key)
            seo_result = analyzer.calculate_video_seo_score(video_data)

        # Prepare response
        return jsonify({
            'success': True,
            'video': {
                'id': video.video_id,
                'title': video.title,
                'thumbnail': video.thumbnail_url,
                'url': f"https://www.youtube.com/watch?v={video.video_id}"
            },
            'seo_analysis': seo_result
        })

    except Exception as e:
        logger.error(f"Error in /analyze-video: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@seo_bp.route('/channel-overview')
@login_required
def get_channel_overview():
    """User ke channel ka SEO overview calculate karo"""
    if not current_user.channel:
        return jsonify({'success': False, 'error': 'No channel connected'}), 404
        
    try:
        videos = Video.query.filter_by(channel_id=current_user.channel.id).filter(Video.seo_score.isnot(None)).all()
        
        if not videos:
            return jsonify({'success': True, 'overview': {
                'total_videos_analyzed': 0,
                'average_score': 0,
                'highest_score': 0,
                'lowest_score': 0,
                'grade_distribution': {},
                'top_videos': [],
                'videos_needing_improvement': []
            }})

        total_score = sum(v.seo_score for v in videos)
        total_videos = len(videos)
        average_score = round(total_score / total_videos, 1)
        
        grade_dist = {}
        for v in videos:
            grade = v.seo_grade or 'N/A'
            grade_dist[grade] = grade_dist.get(grade, 0) + 1
            
        sorted_videos = sorted(videos, key=lambda v: v.seo_score, reverse=True)
        
        top_videos = [{
            'id': v.video_id, 'title': v.title, 'thumbnail': v.thumbnail_url,
            'score': v.seo_score, 'grade': v.seo_grade
        } for v in sorted_videos[:3]]
        
        needing_improvement = sorted([v for v in videos if v.seo_score < 60], key=lambda v: v.seo_score)
        
        videos_needing_improvement = [{
            'id': v.video_id, 'title': v.title, 'thumbnail': v.thumbnail_url,
            'score': v.seo_score, 'grade': v.seo_grade
        } for v in needing_improvement[:5]]
        
        overview = {
            'total_videos_analyzed': total_videos,
            'average_score': average_score,
            'highest_score': round(sorted_videos[0].seo_score, 1),
            'lowest_score': round(sorted_videos[-1].seo_score, 1),
            'grade_distribution': grade_dist,
            'top_videos': top_videos,
            'videos_needing_improvement': videos_needing_improvement
        }
        
        return jsonify({'success': True, 'overview': overview})
        
    except Exception as e:
        logger.error(f"Error in /channel-overview: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@seo_bp.route('/export-report/<string:video_id>')
@login_required
def export_seo_report(video_id):
    """SEO report ko PDF me export karo"""
    
    if not WEASYPRINT_AVAILABLE:
        logger.warning("WeasyPrint not installed. PDF export is disabled.")
        return "PDF Export functionality is not enabled on this server.", 501

    try:
        gemini_key = current_app.config.get('GEMINI_API_KEY')
        if not gemini_key:
             logger.error("GEMINI_API_KEY is not configured.")
             return jsonify({'success': False, 'error': 'AI configuration error on server.'}), 500

        seo_result = get_video_seo_score(video_id, gemini_key)
        if not seo_result.get('success'):
            return jsonify({'success': False, 'error': f'Report generation failed: {seo_result.get("error", "Could not analyze video")}'}), 500

        video = Video.query.filter_by(video_id=video_id).first()
        if not video:
            return jsonify({'success': False, 'error': 'Video data not found for report'}), 404

        # Ensure 'reports/seo_report_pdf.html' template exists
        html_string = render_template(
            'reports/seo_report_pdf.html',
            video=video,
            analysis=seo_result
        )

        pdf_file = HTML(string=html_string).write_pdf()

        filename = f"SEO_Report_{sanitize_filename(video.title)}_{video_id}.pdf"
        response = Response(pdf_file, mimetype='application/pdf')
        # Sanitize filename for ASCII-only headers
        ascii_filename = sanitize_filename(video.title).encode('ascii', 'ignore').decode('ascii') + f"_{video_id}.pdf"
        response.headers['Content-Disposition'] = f'attachment; filename="{ascii_filename}"'
        return response

    except Exception as e:
        logger.error(f"Report export failed for video {video_id}: {e}", exc_info=True)
        return "Failed to generate PDF report.", 500

# --- === नया Google/YouTube Autocomplete स्क्रैपिंग रूट === ---
@seo_bp.route('/autocomplete', methods=['POST'])
@login_required
def get_autocomplete_suggestions():
    """
    Google/YouTube search bar se suggestions scrape karo.
    Yeh Google Trends ka ek behtareen alternative hai.
    """
    data = request.json
    query = data.get('query')
    source = data.get('source', 'youtube') # 'google' or 'youtube'

    if not query:
        return jsonify({'success': False, 'error': 'Query is required'}), 400

    try:
        if source == 'youtube':
            # YouTube suggestions URL
            url = f"http://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q={query}"
        else:
            # Google suggestions URL
            url = f"http://suggestqueries.google.com/complete/search?client=firefox&q={query}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status() # Agar error aaye toh exception raise karo

        # Response ek JSON list hai: [query, [suggestion1, suggestion2, ...]]
        results = json.loads(response.text)
        
        if len(results) > 1:
            suggestions = results[1]
            return jsonify({'success': True, 'suggestions': suggestions})
        else:
            return jsonify({'success': True, 'suggestions': []})

    except requests.exceptions.RequestException as e:
        logger.error(f"Autocomplete scrape failed: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to fetch suggestions: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Error in /autocomplete: {str(e)}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500