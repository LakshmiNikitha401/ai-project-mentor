import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
# TEMPORARY HARDCODE (Replace with your actual password)
db_url = "postgresql://postgres.kqmxnbeisjdkmwdipyfl:ProjectGuide.2026@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"

def get_db():
    return psycopg2.connect(db_url)

def toggle_bookmark(user_id, project):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        project_id = project["id"]
        
        # Check if already bookmarked
        cursor.execute("SELECT id FROM bookmarks WHERE user_id = %s AND project_id = %s", (user_id, project_id))
        existing = cursor.fetchone()
        
        if existing:
            # Remove bookmark
            cursor.execute("DELETE FROM bookmarks WHERE id = %s", (existing['id'],))
            conn.commit()
            return {"success": True, "action": "removed"}
        else:
            # Add bookmark (saving all details)
            cursor.execute("""
                INSERT INTO bookmarks 
                (user_id, project_id, title, description, domain, difficulty, skills) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id, 
                project_id, 
                project.get("title"), 
                project.get("description"), 
                project.get("domain"), 
                project.get("difficulty"), 
                project.get("skills", [])
            ))
            conn.commit()
            return {"success": True, "action": "added"}
            
    except Exception as e:
        conn.rollback()
        print(f"❌ Toggle Bookmark Error: {e}") 
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()

def get_user_bookmarks(user_id):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("SELECT * FROM bookmarks WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
        bookmarks = cursor.fetchall()
        
        # Format difficulty for the UI
        for b in bookmarks:
            b["difficulty"] = str(b.get("difficulty", "")).capitalize()
            
        return bookmarks
    except Exception as e:
        print(f"❌ Fetch Bookmarks Error: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def is_bookmarked(user_id, project_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM bookmarks WHERE user_id = %s AND project_id = %s", (user_id, project_id))
        return cursor.fetchone() is not None
    except Exception as e:
        return False
    finally:
        cursor.close()
        conn.close()