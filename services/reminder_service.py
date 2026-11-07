import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os

load_dotenv()
db_url = os.environ.get("DATABASE_URL")

def get_db():
    return psycopg2.connect(db_url)

def get_user_reminders(user_id):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # --- CLEANUP GHOST REMINDERS ---
        # If a project was deleted, but cascade didn't trigger, clean them up here
        cursor.execute("""
            DELETE FROM user_reminders 
            WHERE user_id = %s 
            AND project_id IS NOT NULL 
            AND project_id NOT IN (SELECT id FROM projects WHERE user_id = %s)
        """, (user_id, user_id))
        conn.commit()
        # -------------------------------

        # JOIN with projects to get the project title
        cursor.execute("""
            SELECT r.*, p.title as project_title
            FROM user_reminders r
            LEFT JOIN projects p ON r.project_id = p.id
            WHERE r.user_id = %s 
            ORDER BY r.due_date ASC
        """, (user_id,))
        reminders = cursor.fetchall()
        
        grouped = {}
        for r in reminders:
            r_dict = dict(r)
            
            # Format Date
            if r_dict.get("due_date"):
                r_dict["formatted_date"] = r_dict["due_date"].strftime("%b %d, %Y")
            else:
                r_dict["formatted_date"] = "No Date Set"
                
            # Group by Project Title (or 'General' if no project)
            proj_title = r_dict.get("project_title") or "General Reminders"
            
            if proj_title not in grouped:
                grouped[proj_title] = []
                
            grouped[proj_title].append(r_dict)
            
        return grouped
    except Exception as e:
        print(f"❌ Fetch Reminders Error: {e}")
        return {}
    finally:
        cursor.close()
        conn.close()

def add_reminder(user_id, title, due_date):
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Manual reminders have no project_id (NULL)
        cursor.execute("INSERT INTO user_reminders (user_id, title, due_date) VALUES (%s, %s, %s)", (user_id, title, due_date))
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()

def delete_reminder(user_id, reminder_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM user_reminders WHERE id = %s AND user_id = %s", (reminder_id, user_id))
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()

def generate_timeline_reminders(user_id, project_id, duration_weeks):
    print(f"🔔 Generating timeline reminders for project {project_id} over {duration_weeks} weeks...")
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("SELECT id, title, order_index FROM roadmap_tasks WHERE project_id = %s ORDER BY order_index", (project_id,))
        tasks = cursor.fetchall()
        
        if not tasks:
            return
            
        total_tasks = len(tasks)
        total_days = duration_weeks * 7
        days_per_task = total_days / total_tasks
        start_date = datetime.now().date()
        
        for task in tasks:
            days_offset = int(days_per_task * (task['order_index'] - 1))
            due_date = start_date + timedelta(days=days_offset)
            
            # SAVE THE PROJECT_ID!
            cursor.execute("""
                INSERT INTO user_reminders (user_id, project_id, title, due_date, status)
                VALUES (%s, %s, %s, %s, 'pending')
            """, (user_id, project_id, f"Complete: {task['title']}", due_date))
        
        conn.commit()
        print(f"✅ Successfully generated {total_tasks} timeline reminders!")
    except Exception as e:
        conn.rollback()
        print(f"❌ FAILED to generate reminders: {e}")
    finally:
        cursor.close()
        conn.close()