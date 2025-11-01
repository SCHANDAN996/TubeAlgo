# Filepath: tubealgo/services/notification_service.py
import requests
import json # json को इम्पोर्ट करें

def send_telegram_message(chat_id, message, reply_markup=None):
    # इम्पोर्ट को फंक्शन के अंदर ले जाया गया है
    from tubealgo.models import get_config_value 
    
    TELEGRAM_TOKEN = get_config_value('TELEGRAM_BOT_TOKEN')
    if not TELEGRAM_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is not set.")
        return None

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    # === यहाँ बदलाव किया गया है ===
    # अगर बटन भेजे गए हैं, तो उन्हें पेलोड में जोड़ें
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    # === यहाँ तक ===

    try:
        response = requests.post(url, data=payload)
        return response.json()
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return None

def send_telegram_photo_with_caption(chat_id, photo_url, caption):
    # इम्पोर्ट को इस फंक्शन के अंदर भी ले जाया गया है
    from tubealgo.models import get_config_value
    
    TELEGRAM_TOKEN = get_config_value('TELEGRAM_BOT_TOKEN')
    if not TELEGRAM_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is not set.")
        return None
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    payload = {
        'chat_id': chat_id,
        'photo': photo_url,
        'caption': caption,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, data=payload)
        return response.json()
    except Exception as e:
        print(f"Error sending Telegram photo: {e}")
        # Fallback to text message if photo fails
        return send_telegram_message(chat_id, caption)