# tubealgo/telegram_bot_handler.py

import requests
import traceback
from .models import is_admin_telegram_user, User, SystemLog, db, log_system_event
from .services.notification_service import send_telegram_message

last_update_id = 0

def answer_callback_query(callback_query_id):
    """बटन क्लिक के बाद लोडिंग आइकॉन को हटाने के लिए टेलीग्राम को जवाब देता है।"""
    from .models import get_config_value
    TELEGRAM_TOKEN = get_config_value('TELEGRAM_BOT_TOKEN')
    if not TELEGRAM_TOKEN: return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
    payload = {'callback_query_id': callback_query_id}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        log_system_event(
            message="Error answering Telegram callback query",
            log_type='ERROR',
            details={'error': str(e), 'traceback': traceback.format_exc()}
        )

def handle_stats(chat_id):
    """/stats कमांड को हैंडल करता है।"""
    if not is_admin_telegram_user(chat_id):
        send_telegram_message(chat_id, "❌ You are not authorized to use this command.")
        return
    try:
        total_users = User.query.count()
        subscribed_users = User.query.filter(User.subscription_plan != 'free').count()
        message = (
            f"📊 *TubeAlgo System Stats*\n\n"
            f"👥 *Total Users:* {total_users}\n"
            f"💎 *Subscribed Users:* {subscribed_users}"
        )
        send_telegram_message(chat_id, message)
    except Exception as e:
        send_telegram_message(chat_id, f"An error occurred while fetching stats: {e}")

def handle_users(chat_id):
    """/users कमांड को हैंडल करता है।"""
    if not is_admin_telegram_user(chat_id):
        send_telegram_message(chat_id, "❌ You are not authorized to use this command.")
        return
    try:
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        if not recent_users:
            send_telegram_message(chat_id, "No users found yet.")
            return
        message = "📜 *Most Recent Users:*\n\n"
        for i, user in enumerate(recent_users, 1):
            join_date = user.created_at.strftime('%d %b, %Y')
            message += (
                f"*{i}. {user.email}*\n"
                f"   Plan: `{user.subscription_plan.capitalize()}` | Joined: _{join_date}_\n\n"
            )
        send_telegram_message(chat_id, message)
    except Exception as e:
        send_telegram_message(chat_id, f"An error occurred while fetching users: {e}")

def handle_get_logs(chat_id):
    """/get_logs कमांड को हैंडल करता है।"""
    if not is_admin_telegram_user(chat_id):
        send_telegram_message(chat_id, "❌ You are not authorized to use this command.")
        return
    try:
        logs = SystemLog.query.order_by(SystemLog.timestamp.desc()).limit(5).all()
        if not logs:
            send_telegram_message(chat_id, "✅ No system logs found. Everything looks good!")
            return
        message = "📋 *Last 5 System Logs:*\n\n"
        for log in logs:
            log_time = log.timestamp.strftime('%Y-%m-%d %H:%M')
            icon = "🚨" if log.log_type in ['ERROR', 'QUOTA_EXCEEDED'] else "ℹ️"
            message += (
                f"{icon} *{log.log_type}* at _{log_time} UTC_\n"
                f"`{log.message}`\n\n"
            )
        send_telegram_message(chat_id, message)
    except Exception as e:
        send_telegram_message(chat_id, f"An error occurred while fetching logs: {e}")

def handle_find_user(chat_id, text):
    """/find_user <email> कमांड को हैंडल करता है।"""
    if not is_admin_telegram_user(chat_id):
        send_telegram_message(chat_id, "❌ You are not authorized to use this command.")
        return
    try:
        parts = text.split()
        if len(parts) < 2:
            send_telegram_message(chat_id, "Please provide an email to search. \nUsage: `/find_user user@example.com`")
            return
        email_to_find = parts[1]
        user = User.query.filter_by(email=email_to_find).first()
        if not user:
            send_telegram_message(chat_id, f"User with email `{email_to_find}` not found.")
            return
        join_date = user.created_at.strftime('%d %b, %Y')
        status_icon = "✅" if user.status == 'active' else " suspend"
        message = (
            f"👤 *User Details*\n\n"
            f"*Email:* `{user.email}`\n"
            f"*Plan:* `{user.subscription_plan.capitalize()}`\n"
            f"*Status:* {status_icon} `{user.status.capitalize()}`\n"
            f"*Joined:* _{join_date}_\n"
            f"*User ID:* `{user.id}`\n"
        )
        if user.telegram_chat_id:
            message += f"*Telegram Connected:* ✅ (`{user.telegram_chat_id}`)\n"
        else:
            message += "*Telegram Connected:* ❌\n"
        send_telegram_message(chat_id, message)
    except Exception as e:
        send_telegram_message(chat_id, f"An error occurred while finding user: {e}")

def handle_suspend_user(chat_id, text):
    """/suspend_user <email> कमांड को हैंडल करता है।"""
    if not is_admin_telegram_user(chat_id):
        send_telegram_message(chat_id, "❌ You are not authorized to use this command.")
        return
    try:
        parts = text.split()
        if len(parts) < 2:
            send_telegram_message(chat_id, "Please provide an email. \nUsage: `/suspend_user user@example.com`")
            return
        email = parts[1]
        user = User.query.filter_by(email=email).first()
        if not user:
            send_telegram_message(chat_id, f"User `{email}` not found.")
            return
        if user.status == 'active':
            user.status = 'suspended'
            db.session.commit()
            send_telegram_message(chat_id, f"✅ User `{email}` has been suspended.")
        else:
            user.status = 'active'
            db.session.commit()
            send_telegram_message(chat_id, f"✅ User `{email}` has been reactivated.")
    except Exception as e:
        db.session.rollback()
        send_telegram_message(chat_id, f"Error updating user status: {e}")

def handle_upgrade_plan(chat_id, text):
    """/upgrade_plan <email> <plan> कमांड को हैंडल करता है।"""
    if not is_admin_telegram_user(chat_id):
        send_telegram_message(chat_id, "❌ You are not authorized to use this command.")
        return
    try:
        parts = text.split()
        valid_plans = ['free', 'creator', 'pro']
        if len(parts) < 3:
            send_telegram_message(chat_id, f"Invalid format. \nUsage: `/upgrade_plan <email> <plan>`\nValid plans: `{', '.join(valid_plans)}`")
            return
        email = parts[1]
        plan = parts[2].lower()
        if plan not in valid_plans:
            send_telegram_message(chat_id, f"Invalid plan name. Valid plans are: `{', '.join(valid_plans)}`")
            return
        user = User.query.filter_by(email=email).first()
        if not user:
            send_telegram_message(chat_id, f"User `{email}` not found.")
            return
        user.subscription_plan = plan
        db.session.commit()
        send_telegram_message(chat_id, f"✅ User `{email}`'s plan has been successfully upgraded to *{plan.capitalize()}*.")
    except Exception as e:
        db.session.rollback()
        send_telegram_message(chat_id, f"Error upgrading plan: {e}")

def handle_start_or_help(chat_id):
    """/start और /help कमांड को हैंडल करता है। अब यह टेक्स्ट की जगह बटन भेजेगा।"""
    message = (
        "🤖 *Welcome to the TubeAlgo Bot!*\n\n"
        "This bot sends you notifications about your competitors."
    )
    
    if not is_admin_telegram_user(chat_id):
        send_telegram_message(chat_id, message)
        return

    admin_message = message + "\n\n👑 *Admin Menu:*"
    
    keyboard = [
        [
            {'text': '📊 Stats', 'callback_data': 'stats'},
            {'text': '👥 Recent Users', 'callback_data': 'users'}
        ],
        [
            {'text': '📋 Get Logs', 'callback_data': 'get_logs'}
        ]
    ]
    reply_markup = {'inline_keyboard': keyboard}
    
    send_telegram_message(chat_id, admin_message, reply_markup=reply_markup)

def process_updates(app):
    """टेलीग्राम से नए मैसेज और बटन क्लिक को प्रोसेस करता है।"""
    global last_update_id
    from .models import get_config_value

    with app.app_context():
        TELEGRAM_TOKEN = get_config_value('TELEGRAM_BOT_TOKEN')
        if not TELEGRAM_TOKEN:
            return

        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params = {'offset': last_update_id + 1, 'timeout': 5}
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            updates = response.json().get('result', [])

            for update in updates:
                last_update_id = update['update_id']
                
                if 'callback_query' in update:
                    callback_id = update['callback_query']['id']
                    chat_id = update['callback_query']['message']['chat']['id']
                    data = update['callback_query']['data']
                    
                    answer_callback_query(callback_id)

                    if data == 'stats':
                        handle_stats(chat_id)
                    elif data == 'users':
                        handle_users(chat_id)
                    elif data == 'get_logs':
                        handle_get_logs(chat_id)
                    continue

                if 'message' in update and 'text' in update['message']:
                    chat_id = update['message']['chat']['id']
                    text = update['message']['text']

                    if text.startswith('/stats'):
                        handle_stats(chat_id)
                    elif text.startswith('/users'):
                        handle_users(chat_id)
                    elif text.startswith('/get_logs'):
                        handle_get_logs(chat_id)
                    elif text.startswith('/find_user'):
                        handle_find_user(chat_id, text)
                    elif text.startswith('/suspend_user'):
                        handle_suspend_user(chat_id, text)
                    elif text.startswith('/upgrade_plan'):
                        handle_upgrade_plan(chat_id, text)
                    elif text.startswith('/start') or text.startswith('/help'):
                        handle_start_or_help(chat_id)

        except requests.exceptions.RequestException as e:
            log_system_event(
                message="Could not connect to Telegram API",
                log_type='ERROR',
                details={'error': str(e)}
            )
        except Exception as e:
            log_system_event(
                message="Error processing Telegram updates",
                log_type='ERROR',
                details={'error': str(e), 'traceback': traceback.format_exc()}
            )