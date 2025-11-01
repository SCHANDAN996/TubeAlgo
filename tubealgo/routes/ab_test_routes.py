# tubealgo/routes/ab_test_routes.py

import os
import uuid
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from .. import db
from ..models import ThumbnailTest
from ..services.youtube_manager import get_user_videos, set_video_thumbnail
from ..routes.utils import get_credentials
from ..jobs import start_thumbnail_test

ab_test_bp = Blueprint('ab_test', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@ab_test_bp.route('/ab-test')
@login_required
def dashboard():
    creds = get_credentials(current_user)
    if not creds:
        flash('Please connect your Google account with YouTube permissions to use this feature.', 'warning')
        return redirect(url_for('auth_google.connect_youtube'))

    # यूज़र ऑब्जेक्ट को पास करें ताकि कैशिंग काम कर सके
    videos = get_user_videos(current_user, creds)
    
    if isinstance(videos, dict) and 'error' in videos:
        flash(f"Could not fetch your videos: {videos['error']}", "error")
        videos = []

    # शॉर्ट्स को वीडियो सूची से फ़िल्टर करें
    long_form_videos = [v for v in videos if not v.get('is_short')]

    tests = ThumbnailTest.query.filter_by(user_id=current_user.id).order_by(ThumbnailTest.created_at.desc()).all()

    video_title_map = {video['id']: video['title'] for video in videos}

    for test in tests:
        test.video_title = video_title_map.get(test.video_id, test.video_id)

    return render_template('ab_test_dashboard.html', videos=long_form_videos, tests=tests)

@ab_test_bp.route('/ab-test/start', methods=['POST'])
@login_required
def start_test():
    video_id = request.form.get('video_id')
    thumbnail_a = request.files.get('thumbnail_a')
    thumbnail_b = request.files.get('thumbnail_b')

    if not all([video_id, thumbnail_a, thumbnail_b]):
        flash('Please select a video and upload both thumbnails.', 'error')
        return redirect(url_for('ab_test.dashboard'))

    if not (allowed_file(thumbnail_a.filename) and allowed_file(thumbnail_b.filename)):
        flash('Invalid file type. Please upload JPG or PNG images.', 'error')
        return redirect(url_for('ab_test.dashboard'))

    # यूज़र-विशिष्ट और टेस्ट-विशिष्ट फ़ोल्डर बनाएं
    relative_folder = os.path.join('uploads', 'ab_tests', str(current_user.id), str(uuid.uuid4()))
    upload_folder = os.path.join(current_app.static_folder, relative_folder)
    os.makedirs(upload_folder, exist_ok=True)

    filename_a = f"thumb_a_{secure_filename(thumbnail_a.filename)}"
    filename_b = f"thumb_b_{secure_filename(thumbnail_b.filename)}"
    
    # URL संगतता के लिए फॉरवर्ड स्लैश का उपयोग करें
    relative_path_a = os.path.join(relative_folder, filename_a).replace("\\", "/")
    relative_path_b = os.path.join(relative_folder, filename_b).replace("\\", "/")

    # बैकएंड संचालन के लिए पूरा पाथ
    full_path_a = os.path.join(upload_folder, filename_a)
    full_path_b = os.path.join(upload_folder, filename_b)

    thumbnail_a.save(full_path_a)
    thumbnail_b.save(full_path_b)

    new_test = ThumbnailTest(
        user_id=current_user.id,
        video_id=video_id,
        thumbnail_a_path=relative_path_a,
        thumbnail_b_path=relative_path_b,
        status='pending'
    )
    db.session.add(new_test)
    db.session.commit()

    # Celery टास्क को केवल टेस्ट ID पास करें
    start_thumbnail_test.delay(new_test.id)

    flash(f"A/B Test for video {video_id} has been started! The first thumbnail is being applied now.", 'success')
    return redirect(url_for('ab_test.dashboard'))

@ab_test_bp.route('/ab-test/delete/<int:test_id>', methods=['POST'])
@login_required
def delete_test(test_id):
    test = ThumbnailTest.query.filter_by(id=test_id, user_id=current_user.id).first_or_404()

    try:
        # फ़ाइल हटाने के लिए पूरा पाथ प्राप्त करें
        full_path_a = os.path.join(current_app.static_folder, test.thumbnail_a_path)
        full_path_b = os.path.join(current_app.static_folder, test.thumbnail_b_path)
        folder_path = os.path.dirname(full_path_a)

        db.session.delete(test)
        db.session.commit()
        
        # DB में बदलाव के बाद फ़ाइलें हटाएँ
        if os.path.exists(full_path_a):
            os.remove(full_path_a)
        if os.path.exists(full_path_b):
            os.remove(full_path_b)
        
        try:
            if os.path.exists(folder_path) and not os.listdir(folder_path):
                os.rmdir(folder_path)
        except OSError:
            pass 

        flash("Test deleted successfully. The active thumbnail on YouTube was not changed.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred while deleting the test files: {e}", "error")

    return redirect(url_for('ab_test.dashboard'))