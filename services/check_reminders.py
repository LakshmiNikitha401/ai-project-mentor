import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from services.auth_service import send_urgent_reminder_email
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.environ.get("DATABASE_URL")

def check_and_send_reminders():
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Find reminders due in exactly 2 days that haven't been emailed yet
    target_date = datetime.now().date() + timedelta(days=2)
    
    cursor.execute("""
        SELECT r.id, r.title, r.due_date, u.email, u.full_name 
        FROM user_reminders r
        JOIN user_credentials u ON r.user_id = u.user_id
        WHERE r.due_date = %s 
        AND r.status = 'pending'
    """, (target_date,))
    
    reminders = cursor.fetchall()
    
    for r in reminders:
        print(f"Sending urgent email to {r['email']} for {r['title']}")
        send_urgent_reminder_email(r['email'], r['full_name'], r['title'], r['due_date'].strftime("%b %d, %Y"))
        
    cursor.close()
    conn.close()

if __name__ == "__main__":
    check_and_send_reminders()