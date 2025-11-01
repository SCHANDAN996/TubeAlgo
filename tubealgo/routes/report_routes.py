# tubealgo/routes/report_routes.py

from flask import Blueprint, render_template, Response
from flask_login import login_required, current_user
from datetime import datetime, timedelta, timezone
from weasyprint import HTML

from ..models import ChannelSnapshot
from ..services.channel_fetcher import analyze_channel
from ..services.youtube_manager import get_user_videos
from .utils import get_credentials, sanitize_filename

report_bp = Blueprint('report', __name__, url_prefix='/report')

@report_bp.route('/monthly')
@login_required
def generate_monthly_report():
    # 1. आवश्यक डेटा इकट्ठा करें
    today = datetime.now(timezone.utc)
    thirty_days_ago = today - timedelta(days=30)
    
    # वर्तमान चैनल आँकड़े
    channel_stats = analyze_channel(current_user.channel.channel_id_youtube)
    if 'error' in channel_stats:
        return "Could not generate report: " + channel_stats['error'], 500

    # 30 दिन पहले के आँकड़े
    past_snapshot = ChannelSnapshot.query.filter(
        ChannelSnapshot.channel_db_id == current_user.channel.id,
        ChannelSnapshot.date <= thirty_days_ago.date()
    ).order_by(ChannelSnapshot.date.desc()).first()

    # ग्रोथ की गणना करें
    growth = {
        "subscribers_gained": 0,
        "views_gained": 0
    }
    if past_snapshot:
        growth["subscribers_gained"] = channel_stats.get('Subscribers', 0) - past_snapshot.subscribers
        growth["views_gained"] = channel_stats.get('Total Views', 0) - past_snapshot.views

    # पिछले 30 दिनों के टॉप वीडियो
    creds = get_credentials()
    all_videos = get_user_videos(current_user, creds)
    
    top_videos = []
    if isinstance(all_videos, list):
        videos_in_period = [
            v for v in all_videos 
            if datetime.fromisoformat(v['published_at'].replace('Z', '+00:00')) >= thirty_days_ago
        ]
        top_videos = sorted(videos_in_period, key=lambda x: x.get('view_count', 0), reverse=True)[:5]

    # 2. HTML टेम्पलेट को डेटा के साथ रेंडर करें
    report_period = f"{thirty_days_ago.strftime('%B %d, %Y')} - {today.strftime('%B %d, %Y')}"
    generation_date = today.strftime('%B %d, %Y')

    html_string = render_template(
        'reports/monthly_summary.html',
        channel_stats=channel_stats,
        report_period=report_period,
        growth=growth,
        top_videos=top_videos,
        generation_date=generation_date
    )

    # 3. HTML से PDF बनाएं
    pdf_file = HTML(string=html_string).write_pdf()

    # 4. PDF को डाउनलोड के रूप में भेजें
    filename = f"Monthly_Report_{sanitize_filename(channel_stats.get('Title', 'Channel'))}_{today.strftime('%Y_%m_%d')}.pdf"
    
    response = Response(pdf_file, mimetype='application/pdf')
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response