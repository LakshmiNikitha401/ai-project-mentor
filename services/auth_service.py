import os
import random
import string
import requests
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()
db_url = os.environ.get("DATABASE_URL")

# --- NEW GMAIL API CREDENTIALS ---
GMAIL_CLIENT_ID = os.environ.get('GMAIL_CLIENT_ID')
GMAIL_CLIENT_SECRET = os.environ.get('GMAIL_CLIENT_SECRET')
GMAIL_REFRESH_TOKEN = os.environ.get('GMAIL_REFRESH_TOKEN')
GMAIL_SENDER = os.environ.get('GMAIL_SENDER')

def get_db():
    return psycopg2.connect(db_url)

# --- NEW HELPER FUNCTION FOR GOOGLE API ---
def send_email_via_gmail_api(to_email, subject, html_body):
    try:
        if not all([GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN, GMAIL_SENDER]):
            print("❌ Missing Gmail API environment variables.")
            return False

        # 1. Trade refresh token for a fresh access token
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            'client_id': GMAIL_CLIENT_ID,
            'client_secret': GMAIL_CLIENT_SECRET,
            'refresh_token': GMAIL_REFRESH_TOKEN,
            'grant_type': 'refresh_token'
        }
        token_res = requests.post(token_url, data=token_data, timeout=10)
        access_token = token_res.json().get('access_token')

        if not access_token:
            print(f"❌ Auth failed: {token_res.text}")
            return False

        # 2. Build the email
        msg = MIMEMultipart()
        msg['To'] = to_email
        msg['From'] = f"AI Project Mentor <{GMAIL_SENDER}>"
        msg['Subject'] = subject
        msg.attach(MIMEText(html_body, 'html'))

        # 3. Encode and send
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        send_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        send_res = requests.post(send_url, headers=headers, json={'raw': raw_message}, timeout=10)
        
        if send_res.status_code == 200:
            return True
        else:
            print(f"❌ Gmail API Error: {send_res.text}")
            return False

    except Exception as e:
        print(f"❌ Email sending failed: {e}")
        return False


# --- UPDATED EMAIL FUNCTIONS ---
def send_otp_email(to_email, otp):
    subject = "Your Verification Code - AI Project Mentor"
    body = f"<h2>Welcome!</h2><p>Your verification code is:</p><h1>{otp}</h1>"
    return send_email_via_gmail_api(to_email, subject, body)

def send_project_started_email(to_email, user_name, project_title, duration_weeks):
    subject = f"🚀 Project Started: {project_title}"
    body = f"""
    <h2>Hi {user_name},</h2>
    <p>You have successfully started <strong>{project_title}</strong>!</p>
    <p>Your timeline is set for <strong>{duration_weeks} weeks</strong>. We have generated your roadmap and timeline reminders.</p>
    <p>Log in to your workspace to view your first task and get started.</p>
    <br>
    <p>Best of luck,<br>AI Project Mentor</p>
    """
    return send_email_via_gmail_api(to_email, subject, body)

def send_urgent_reminder_email(to_email, user_name, reminder_title, due_date):
    subject = f"⚠️ Urgent Reminder: {reminder_title}"
    body = f"""
    <h2>Hi {user_name},</h2>
    <p>This is a gentle nudge to keep you on track.</p>
    <p>Your milestone <strong>{reminder_title}</strong> is due on <strong>{due_date}</strong>.</p>
    <p>Hurry up and complete this phase so you don't fall behind on your roadmap!</p>
    <br>
    <p>You can do it,<br>AI Project Mentor</p>
    """
    return send_email_via_gmail_api(to_email, subject, body)


# --- REST OF YOUR DATABASE LOGIC (UNCHANGED) ---

def check_email_exists(email):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM user_credentials WHERE email = %s", (email,))
    exists = cursor.fetchone() is not None
    cursor.close()
    conn.close()
    return exists

def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

def create_user_after_otp(email, password, full_name, degree_level, department, skills):
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        hashed = generate_password_hash(password)
        
        cursor.execute(
            """INSERT INTO user_credentials 
               (user_id, email, password_hash, full_name, is_verified, degree_level, department, skills_list) 
               VALUES (gen_random_uuid(), %s, %s, %s, true, %s, %s, %s)""",
            (email, hashed, full_name, degree_level, department, skills)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def login_user(email, password):
    try:
        conn = get_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM user_credentials WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user:
            return {"success": False, "error": "Invalid email or password"}
        if not user["is_verified"]:
            return {"success": False, "error": "Please verify your email first."}
        
        if check_password_hash(user["password_hash"], password):
            return {
                "success": True,
                "access_token": "local_session",
                "user": {
                    "id": str(user["user_id"]), 
                    "email": user["email"], 
                    "full_name": user["full_name"],
                    "degree": user.get("degree_level"),
                    "skills": user.get("skills_list")
                }
            }
        else:
            return {"success": False, "error": "Invalid email or password"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_user_profile(user_id):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM user_credentials WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user

def update_user_profile(user_id, full_name, degree_level, department, skills_list):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE user_credentials 
            SET full_name = %s, degree_level = %s, department = %s, skills_list = %s
            WHERE user_id = %s
        """, (full_name, degree_level, department, skills_list, user_id))
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()
