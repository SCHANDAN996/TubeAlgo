import google.generativeai as genai
import os
from dotenv import load_dotenv

# .env फ़ाइल से API key लोड करने के लिए
load_dotenv()

# अपनी Gemini API key यहाँ प्राप्त करें
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not GEMINI_API_KEY:
    print("त्रुटि: कृपया अपनी .env फ़ाइल में GEMINI_API_KEY सेट करें।")
else:
    try:
        genai.configure(api_key=GEMINI_API_KEY)

        print("आपकी API Key के लिए उपलब्ध मॉडल्स की सूची:")
        
        # === बदलाव यहाँ है: हार्डकोडेड की प्रिंट को हटा दिया गया है ===

        found_model = False
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(m.name)
                found_model = True

        if not found_model:
            print("\nइस API Key के लिए कोई भी संगत (compatible) मॉडल नहीं मिला।")
            print("कृपया सुनिश्चित करें कि आपने Vertex AI API को सही प्रोजेक्ट में इनेबल किया है।")

    except Exception as e:
        print(f"\nएक त्रुटि हुई: {e}")
        print("\nकृपया सुनिश्चित करें कि आपकी API Key सही है और आपने Vertex AI API को इनेबल कर लिया है।")