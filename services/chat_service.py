import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
# TEMPORARY HARDCODE (Match the one you used elsewhere)
db_url = "postgresql://postgres.kqmxnbeisjdkmwdipyfl:ProjectGuide.2026@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"

def get_db():
    return psycopg2.connect(db_url)

def get_chat_history(user_id, project_id):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        "SELECT role, content FROM mentor_chats WHERE user_id = %s AND project_id = %s ORDER BY created_at ASC",
        (user_id, project_id)
    )
    history = cursor.fetchall()
    cursor.close()
    conn.close()
    return history

def save_chat_message(user_id, project_id, role, content):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO mentor_chats (user_id, project_id, role, content) VALUES (%s, %s, %s, %s)",
            (user_id, project_id, role, content)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"❌ Chat Save Error: {e}")
    finally:
        cursor.close()
        conn.close()

def clear_chat_history(user_id, project_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM mentor_chats WHERE user_id = %s AND project_id = %s",
            (user_id, project_id)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"❌ Chat Clear Error: {e}")
    finally:
        cursor.close()
        conn.close()