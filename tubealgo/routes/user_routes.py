# tubealgo/routes/user_routes.py

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from tubealgo import db
import pytz

user_bp = Blueprint('user', __name__)

@user_bp.route('/api/user/set-timezone', methods=['POST'])
@login_required
def set_user_timezone():
    data = request.json
    timezone = data.get('timezone')

    if not timezone or timezone not in pytz.all_timezones:
        return jsonify({'success': False, 'error': 'Invalid timezone provided.'}), 400

    # Only update if the timezone is not already set
    if not current_user.timezone:
        current_user.timezone = timezone
        db.session.commit()
        return jsonify({'success': True, 'message': f'Timezone set to {timezone}.'})

    return jsonify({'success': True, 'message': 'Timezone was already set.'})