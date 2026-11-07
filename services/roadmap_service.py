import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from services.ai_service import generate_ai_response

load_dotenv()
# TEMPORARY HARDCODE (Replace with your actual password)
db_url = "postgresql://postgres.kqmxnbeisjdkmwdipyfl:ProjectGuide.2026@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"

def get_db():
    return psycopg2.connect(db_url)

def generate_ai_roadmap(project_title, domain, difficulty):
    """
    Calls the AI to generate a deeply specific roadmap for the project.
    """
    system_prompt = "You are an expert technical project manager and senior engineer. You create highly specific, actionable roadmaps."
    
    prompt = f"""
    Create a detailed project roadmap for a student building this project:
    Title: "{project_title}"
    Domain: "{domain}"
    Difficulty: "{difficulty}"

    STRICT RULES:
    1. Generate between 6 and 9 steps based on the project's complexity.
    2. Each step MUST have a short title and a highly detailed technical description. 
    3. The description should explain HOW to do it (e.g., mention specific libraries, database schemas, or algorithms to use).
    4. Generate 3 specific sub-tasks for each step that the student can check off.
    
    Return ONLY a valid JSON array. No markdown formatting, no backticks.
    Format:
    [
      {{
        "title": "Step Title",
        "description": "Detailed technical explanation of what to do and how to do it.",
        "tasks": ["Specific task 1", "Specific task 2", "Specific task 3"]
      }}
    ]
    """
    
    try:
        response_text, provider = generate_ai_response(prompt, system_prompt)
        
        if response_text.startswith("```json"):
            response_text = response_text.replace("```json", "").replace("```", "").strip()
        elif response_text.startswith("```"):
            response_text = response_text.replace("```", "").strip()
            
        roadmap_json = json.loads(response_text)
        return roadmap_json
    except Exception as e:
        print(f"❌ Failed to generate AI roadmap: {e}")
        # Fallback roadmap if AI fails
        return [
            {"title": "Project Setup", "description": "Initialize the project structure and install dependencies.", "tasks": ["Setup environment", "Install libraries", "Initialize git"]},
            {"title": "Core Development", "description": "Implement the main logic of the project.", "tasks": ["Write core functions", "Test logic", "Refine code"]},
            {"title": "Testing & Evaluation", "description": "Test the project with real data and measure results.", "tasks": ["Write test cases", "Run evaluation", "Document results"]},
            {"title": "Final Report", "description": "Prepare the final documentation and presentation.", "tasks": ["Write report", "Create slides", "Practice viva"]}
        ]

def start_project_workspace(user_id, catalogue_project, duration_weeks=4):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # 1. CHECK IF PROJECT ALREADY EXISTS FOR THIS USER
        cursor.execute("""
            SELECT id FROM projects 
            WHERE user_id = %s AND catalogue_project_id = %s AND status = 'active'
        """, (user_id, catalogue_project['id']))
        
        existing = cursor.fetchone()
        if existing:
            print(f"⚠️ Project already exists. Returning existing ID: {existing['id']}")
            return {"success": True, "project_id": existing['id'], "already_existed": True}

        # 2. CREATE THE PROJECT
        cursor.execute("""
            INSERT INTO projects (user_id, catalogue_project_id, title, description, domain, difficulty, duration_weeks, status, progress_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', 0)
            RETURNING id;
        """, (
            user_id, 
            catalogue_project['id'],
            catalogue_project['title'],
            catalogue_project['description'],
            catalogue_project['domain'],
            catalogue_project['difficulty'],
            duration_weeks
        ))
        
        project_id = cursor.fetchone()['id']
        
        # 3. GENERATE THE ROADMAP
        print(f"🧠 Generating AI roadmap for {catalogue_project['title']}...")
        roadmap_steps = generate_ai_roadmap(
            catalogue_project['title'], 
            catalogue_project['domain'], 
            catalogue_project['difficulty']
        )
        
        # 4. INSERT TASKS
        for index, step in enumerate(roadmap_steps):
            status = 'ready' if index == 0 else 'locked'
            cursor.execute("""
                INSERT INTO roadmap_tasks (project_id, user_id, title, description, sub_tasks, order_index, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """, (
                project_id, user_id, step['title'], step['description'], 
                json.dumps(step.get('tasks', [])), index + 1, status
            ))
            
        conn.commit()
        return {"success": True, "project_id": project_id, "already_existed": False}
        
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()

def get_project_workspace(user_id, project_id):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT * FROM projects WHERE id = %s AND user_id = %s", (project_id, user_id))
    project = cursor.fetchone()
    
    if not project:
        cursor.close()
        conn.close()
        return None
        
    cursor.execute("SELECT * FROM roadmap_tasks WHERE project_id = %s ORDER BY order_index ASC", (project_id,))
    tasks = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return {"project": project, "tasks": tasks}

def complete_task_and_unlock_next(user_id, task_id):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # 1. Mark the current task as completed
        cursor.execute("""
            UPDATE roadmap_tasks 
            SET status = 'completed', completed_at = NOW() 
            WHERE id = %s AND user_id = %s AND status = 'ready'
            RETURNING project_id, order_index, title;
        """, (task_id, user_id))
        
        result = cursor.fetchone()
        if not result:
            return {"success": False, "error": "Task not found or is locked."}
            
        project_id = result['project_id']
        current_order = result['order_index']
        task_title = result['title']
        
                # --- NEW: SYNC WITH REMINDERS ---
        # Mark the corresponding reminder as completed
        cursor.execute("""
            UPDATE user_reminders 
            SET status = 'completed' 
            WHERE user_id = %s AND project_id = %s AND title LIKE %s
        """, (user_id, project_id, f"%{task_title}%"))
        # --------------------------------

        # 2. Unlock the NEXT task
        cursor.execute("""
            UPDATE roadmap_tasks 
            SET status = 'ready' 
            WHERE project_id = %s AND order_index = %s AND status = 'locked';
        """, (project_id, current_order + 1))
        
        # 3. Update the project's overall progress percentage
        cursor.execute("SELECT COUNT(*) as total FROM roadmap_tasks WHERE project_id = %s", (project_id,))
        total = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as done FROM roadmap_tasks WHERE project_id = %s AND status = 'completed'", (project_id,))
        done = cursor.fetchone()['done']
        
        progress = int((done / total) * 100) if total > 0 else 0
        
        cursor.execute("UPDATE projects SET progress_pct = %s WHERE id = %s", (progress, project_id))
        
        conn.commit()
        return {"success": True, "project_id": project_id}
        
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()

def get_active_project(user_id):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT * FROM projects 
        WHERE user_id = %s AND status = 'active' 
        ORDER BY created_at DESC LIMIT 1
    """, (user_id,))
    project = cursor.fetchone()
    
    cursor.close()
    conn.close()
    return project

def get_all_user_projects(user_id):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("""
        SELECT * FROM projects 
        WHERE user_id = %s 
        ORDER BY created_at DESC
    """, (user_id,))
    projects = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return projects

def delete_project(user_id, project_id):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM projects WHERE id = %s AND user_id = %s", (project_id, user_id))
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()

def create_custom_workspace(user_id, title, description, domain, difficulty, roadmap_steps):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # 1. Create the project
        cursor.execute("""
            INSERT INTO projects (user_id, title, description, domain, difficulty, status, progress_pct)
            VALUES (%s, %s, %s, %s, %s, 'active', 0)
            RETURNING id;
        """, (user_id, title, description, domain, difficulty))
        
        project_id = cursor.fetchone()['id']
        
        # 2. Insert the AI-generated steps
        for index, step in enumerate(roadmap_steps):
            status = 'ready' if index == 0 else 'locked'
            cursor.execute("""
                INSERT INTO roadmap_tasks (project_id, user_id, title, description, sub_tasks, order_index, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """, (
                project_id, user_id, step['title'], step['description'], 
                json.dumps(step.get('tasks', [])), index + 1, status
            ))
            
        conn.commit()
        return {"success": True, "project_id": project_id}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()

def apply_project_pivot(user_id, project_id, new_title, new_description, new_domain, new_roadmap):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            UPDATE roadmap_tasks 
            SET status = 'archived' 
            WHERE project_id = %s AND status != 'completed'
        """, (project_id,))
        
        cursor.execute("""
            UPDATE projects 
            SET title = %s, description = %s, domain = %s, difficulty = 'Advanced'
            WHERE id = %s AND user_id = %s
        """, (new_title, new_description, new_domain, project_id, user_id))
        
        cursor.execute("""
            SELECT MAX(order_index) as max_idx FROM roadmap_tasks WHERE project_id = %s
        """, (project_id,))
        max_idx_result = cursor.fetchone()
        start_idx = max_idx_result['max_idx'] if max_idx_result['max_idx'] else 0
        
        for index, step in enumerate(new_roadmap):
            status = 'ready' if index == 0 else 'locked'
            cursor.execute("""
                INSERT INTO roadmap_tasks (project_id, user_id, title, description, sub_tasks, order_index, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """, (
                project_id, user_id, step['title'], step['description'], 
                json.dumps(step.get('tasks', [])), start_idx + index + 1, status
            ))
            
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()

def append_custom_step(user_id, project_id, step_data):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT MAX(order_index) as max_idx FROM roadmap_tasks WHERE project_id = %s", (project_id,))
        max_idx = cursor.fetchone()['max_idx'] or 0
        
        cursor.execute("SELECT COUNT(*) as pending FROM roadmap_tasks WHERE project_id = %s AND status != 'completed'", (project_id,))
        pending = cursor.fetchone()['pending']
        new_status = 'ready' if pending == 0 else 'locked'
        
        cursor.execute("""
            INSERT INTO roadmap_tasks (project_id, user_id, title, description, sub_tasks, order_index, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (project_id, user_id, step_data['title'], step_data['description'], json.dumps(step_data.get('tasks', [])), max_idx + 1, new_status))
        
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cursor.close()
        conn.close()