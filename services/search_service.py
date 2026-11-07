import os
import requests
from dotenv import load_dotenv

# Load the .env file
load_dotenv()
db_url = os.environ.get("DATABASE_URL")

def generate_ai_response(prompt, system_prompt="You are an expert academic project advisor for degree students (UG/PG)."):
    print("\n🔥🔥🔥 AI SERVICE: STARTING REQUEST 🔥🔥🔥")
    
    # --- LOAD KEYS SECURELY FROM .env ---
    GROQ_API_KEY_1 = os.environ.get("GROQ_API_KEY_1", "")
    GROQ_API_KEY_2 = os.environ.get("GROQ_API_KEY_2", "")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]
    }

    # ==========================================
    # 1. Try Groq Primary Key
    # ==========================================
    print("⏳ Contacting Groq (Primary Key)...")
    url_groq = "https://api.groq.com/openai/v1/chat/completions"
    headers["Authorization"] = f"Bearer {GROQ_API_KEY_1}"
    
    try:
        response = requests.post(url_groq, headers=headers, json=payload, timeout=15)
        print(f"Groq Primary Status Code: {response.status_code}")
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content'], "groq_primary"
        else:
            print(f"❌ GROQ PRIMARY FAILED: {response.text}")
    except Exception as e:
        print(f"❌ GROQ PRIMARY CRASH: {e}")

    # ==========================================
    # 2. Try Groq Fallback Key
    # ==========================================
    if GROQ_API_KEY_2:
        print("⏳ Primary failed. Trying Groq Fallback Key...")
        headers["Authorization"] = f"Bearer {GROQ_API_KEY_2}"
        
        try:
            response = requests.post(url_groq, headers=headers, json=payload, timeout=15)
            print(f"Groq Fallback Status Code: {response.status_code}")
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'], "groq_fallback"
            else:
                print(f"❌ GROQ FALLBACK FAILED: {response.text}")
        except Exception as e:
            print(f"❌ GROQ FALLBACK CRASH: {e}")

    # ==========================================
    # 3. Try Gemini (Last Resort)
    # ==========================================
    print("⏳ Both Groq keys failed. Falling back to Gemini...")
    url_gemini = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    gemini_headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    gemini_payload = {"contents": [{"parts": [{"text": f"{system_prompt}\n\nUser: {prompt}"}]}]}
    
    try:
        response = requests.post(url_gemini, headers=gemini_headers, json=gemini_payload, timeout=15)
        print(f"Gemini Status Code: {response.status_code}")
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text'], "gemini"
        else:
            print(f"❌ GEMINI ERROR: {response.text}")
    except Exception as e:
        print(f"❌ GEMINI CRASH: {e}")

    return "All AI APIs failed. Check the terminal for rate limits.", "error"