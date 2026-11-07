import os
import random
import string
import smtplib
import json
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

# Gmail API imports
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()
db_url = os.environ.get("DATABASE_URL")
mail_email = os.environ.get("MAIL_EMAIL")
mail_password = os.environ.get("MAIL_PASSWORD")
gmail_creds_json = os.environ.get("GMAIL_CREDENTIALS_JSON")

def get_db():
    return psycopg2.connect(db_url)

# ==========================================
# EMAIL HELPER (Handles Local vs Render)
# ==========================================
def _send_email(to_email, subject, body_html):
    # Check if we are running on Render (Render sets the RENDER env variable)
    is_production = os.environ.get("RENDER") is not None
    
    if is_production and gmail_creds_json:
        # --- PRODUCTION: Use Gmail API ---
        try:
            creds_info = json.loads(gmail_creds_json)
            creds = Credentials.from_authorized_user_info(creds_info)
            service = build('gmail', 'v1', credentials=creds)
            
            message = MIMEText(body_html, 'html')
            message['to'] = to_email
            message['from'] = mail_email
            message['subject'] = subject
            
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            service.users().messages().send(userId='me', body={'raw': raw}).execute()
            print(f"✅ Email sent via Gmail API to {to_email}")
            return True
        except Exception as e:
            print(f"❌ Gmail API Error: {e}")
            return False
    else:
        # --- LOCAL: Use SMTP ---
        try:
            msg = MIMEMultipart()
            msg['From'] = f"AI Project Mentor <{mail_email}>"
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body_html, 'html'))
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(mail_email, mail_password)
            server.send_message(msg)
            server.quit()
            print(f"✅ Email sent via SMTP to {to_email}")
            return True
        except Exception as e:
            print(f"❌ SMTP Error: {e}")
            return False

# ==========================================
# AUTHENTICATION FLOWS
# ==========================================

def send_otp_email(to_email, otp):
    body = f"<h2>Welcome!</h2><p>Your verification code is:</p><h1>{otp}</h1>"
    return _send_email(to_email, "Your Verification Code - AI Project Mentor", body)

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

# ==========================================
# NOTIFICATION EMAILS
# ==========================================

def send_project_started_email(to_email, user_name, project_title, duration_weeks):
    body = f"""
    <h2>Hi {user_name},</h2>
    <p>You have successfully started <strong>{project_title}</strong>!</p>
    <p>Your timeline is set for <strong>{duration_weeks} weeks</strong>. We have generated your roadmap and timeline reminders.</p>
    <p>Log in to your workspace to view your first task and get started.</p>
    <br>
    <p>Best of luck,<br>AI Project Mentor</p>
    """
    return _send_email(to_email, f"🚀 Project Started: {project_title}", body)

def send_urgent_reminder_email(to_email, user_name, reminder_title, due_date):
    body = f"""
    <h2>Hi {user_name},</h2>
    <p>This is a gentle nudge to keep you on track.</p>
    <p>Your milestone <strong>{reminder_title}</strong> is due on <strong>{due_date}</strong>.</p>
    <p>Hurry up and complete this phase so you don't fall behind on your roadmap!</p>
    <br>
    <p>You can do it,<br>AI Project Mentor</p>
    """
    return _send_email(to_email, f"⚠️ Urgent Reminder: {reminder_title}", body)
