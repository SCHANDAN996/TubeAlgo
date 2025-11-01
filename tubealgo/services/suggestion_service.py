# tubealgo/services/suggestion_service.py
import requests
import json

def get_keyword_suggestions(keyword):
    try:
        url = f"http://google.com/complete/search?client=chrome&q={keyword}"
        response = requests.get(url)
        response.raise_for_status()
        suggestions_list = json.loads(response.text)[1]
        formatted_suggestions = [{"keyword": suggestion, "volume": "(coming soon)"} for suggestion in suggestions_list]
        if not formatted_suggestions:
            return {"suggestions": [{"keyword": "No suggestions found.", "volume": ""}]}
        return {"suggestions": formatted_suggestions}
    except Exception as e:
        return {'error': f'An unexpected error occurred: {e}'}

# === बदलाव यहाँ से शुरू है: नया फंक्शन जोड़ा गया ===
def analyze_best_time_to_post(aggregated_schedule):
    """
    Analyzes aggregated upload data to find the best day and time to post.
    """
    if not aggregated_schedule or sum(aggregated_schedule.get('by_day', [])) == 0:
        return {
            "message": "आपके प्रतियोगियों के पर्याप्त डेटा का विश्लेषण करने के बाद सुझाव यहां दिखाई देंगे।",
            "day": None,
            "time_range": None
        }

    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    # सबसे अच्छा दिन खोजें
    uploads_by_day = aggregated_schedule.get('by_day', [0]*7)
    best_day_index = uploads_by_day.index(max(uploads_by_day))
    best_day = days_of_week[best_day_index]

    # सबसे अच्छा घंटा खोजें
    uploads_by_hour = aggregated_schedule.get('by_hour', [0]*24)
    best_hour_24 = uploads_by_hour.index(max(uploads_by_hour))

    # घंटे को AM/PM प्रारूप में बदलें
    if best_hour_24 == 0:
        time_str = "12 AM"
    elif best_hour_24 < 12:
        time_str = f"{best_hour_24} AM"
    elif best_hour_24 == 12:
        time_str = "12 PM"
    else:
        time_str = f"{best_hour_24 - 12} PM"

    return {
        "message": f"आपके प्रतियोगियों की गतिविधि के आधार पर, पोस्ट करने का सबसे अच्छा समय लगभग है:",
        "day": best_day,
        "time_range": time_str
    }
# === बदलाव यहाँ खत्म है ===