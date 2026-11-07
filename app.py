import os
import random
import json
import markdown
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash
from dotenv import load_dotenv

# Services
from services.auth_service import (
    login_user, check_email_exists, generate_otp, send_otp_email, create_user_after_otp
)
from services.search_service import search_projects, get_project_by_id
from services.roadmap_service import (
    start_project_workspace, get_project_workspace, complete_task_and_unlock_next, 
    get_active_project, get_all_user_projects, delete_project, create_custom_workspace,
    apply_project_pivot, append_custom_step
)
from services.bookmark_service import toggle_bookmark, get_user_bookmarks, is_bookmarked
from services.reminder_service import get_user_reminders, add_reminder, delete_reminder, generate_timeline_reminders
from services.studio_service import generate_academic_draft
from services.research_service import search_arxiv
from services.chat_service import get_chat_history, save_chat_message, clear_chat_history
from services.ai_service import generate_ai_response
from services.custom_project_service import get_next_question, generate_custom_roadmap
from services.analyzer_service import extract_text_from_file, analyze_existing_project
from services.auth_service import get_user_profile, update_user_profile
from services.auth_service import get_user_profile, update_user_profile, send_project_started_email
from flask import send_file
from services.pdf_service import generate_project_proposal_pdf
from services.ai_service import generate_ai_response

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super-secret-dev-key")

# ==========================================
# PUBLIC ROUTES
# ==========================================

@app.route("/")
def home():
    if "access_token" in session:
        return redirect(url_for("dashboard"))
    view = request.args.get("view", "home")
    return render_template("index.html", view=view)

@app.route("/login", methods=["GET", "POST"])
def login():
    if "access_token" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        result = login_user(email, password)
        
        if result["success"]:
            session["access_token"] = result["access_token"]
            session["user_id"] = result["user"]["id"]
            session["user_email"] = result["user"]["email"]
            session["full_name"] = result["user"].get("full_name", "Student")
            return redirect(url_for("dashboard"))
        else:
            flash(result['error'], "error")
            
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if "access_token" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        
        # Handle the degree logic (Other vs Dropdown)
        degree = request.form.get("degree_level")
        if degree == "Other":
            degree = request.form.get("custom_degree", "Other")
            
        dept = request.form.get("department", "Computer Science")
        skills_str = request.form.get("skills", "")
        
        # Convert comma-separated string to a list for the DB
        skills_list = [s.strip() for s in skills_str.split(",") if s.strip()]
        
        if check_email_exists(email):
            flash("Email already registered.", "error")
            return render_template("register.html")

        otp_code = generate_otp()
        if send_otp_email(email, otp_code):
            # Save all these details temporarily in the Flask session
            session["signup_data"] = {
                "name": name,
                "email": email,
                "password": password,
                "otp": otp_code,
                "degree": degree,
                "dept": dept,
                "skills": skills_list,
                "expires": (datetime.now() + timedelta(minutes=10)).isoformat()
            }
            flash("Account created pending verification! Please check your email.", "success")
            return redirect(url_for("verify"))
        else:
            flash("Failed to send OTP email. Check server logs.", "error")
            
    return render_template("register.html")

@app.route("/verify", methods=["GET", "POST"])
def verify():
    signup_data = session.get("signup_data")
    if not signup_data:
        flash("No pending signup found. Please register again.", "error")
        return redirect(url_for("register"))

    if request.method == "POST":
        entered_otp = request.form.get("otp")
        expiry_time = datetime.fromisoformat(signup_data["expires"])
        
        if datetime.now() > expiry_time:
            session.pop("signup_data", None)
            flash("OTP has expired. Please register again.", "error")
            return redirect(url_for("register"))

        if entered_otp == signup_data["otp"]:
            result = create_user_after_otp(
                signup_data["email"], 
                signup_data["password"], 
                signup_data["name"],
                signup_data["degree"],
                signup_data["dept"],
                signup_data["skills"]
            )
            if result["success"]:
                session.pop("signup_data", None)
                flash("Email verified successfully! You can now log in.", "success")
                return redirect(url_for("login"))
            else:
                flash(f"Database error: {result['error']}", "error")
        else:
            flash("Invalid OTP code. Try again.", "error")
            
    return render_template("verify.html", email=signup_data["email"])

# ==========================================
# AUTHENTICATED ROUTES
# ==========================================

@app.route("/dashboard")
def dashboard():
    if "access_token" not in session:
        flash("Please log in to access your dashboard.", "error")
        return redirect(url_for("login"))
    
    user_name = session.get("full_name", "Student")
    active_project = get_active_project(session["user_id"])

    # Simplified greeting
    greeting = "Welcome"

    recommendations = []
    total_phases = 0
    
    if active_project:
        workspace_data = get_project_workspace(session["user_id"], active_project["id"])
        if workspace_data:
            total_phases = len(workspace_data["tasks"])
            
        active_title = str(active_project.get("title", "")).strip().lower()
        recs = search_projects(active_project["domain"], domain_filter=active_project["domain"])
        
        clean_recs = [r for r in recs if str(r.get("title", "")).strip().lower() != active_title]
        random.shuffle(clean_recs)
        recommendations = clean_recs[:3]
        
        if len(recommendations) < 3:
            all_projects = search_projects("")
            for p in all_projects:
                if str(p.get("title", "")).strip().lower() != active_title and p not in recommendations:
                    recommendations.append(p)
                if len(recommendations) == 3:
                    break
    else:
        all_projects = search_projects("")
        random.shuffle(all_projects)
        recommendations = all_projects[:3]
        
    user_bookmarks = get_user_bookmarks(session["user_id"])[:3]
    
    return render_template(
        "dashboard.html", 
        user_name=user_name, 
        active_project=active_project,
        recommendations=recommendations, 
        bookmarks=user_bookmarks,
        total_phases=total_phases, 
        greeting=greeting
    )

@app.route("/my-workspace")
def my_workspace():
    if "access_token" not in session:
        return redirect(url_for("login"))
    projects = get_all_user_projects(session["user_id"])
    return render_template("my_workspace.html", projects=projects)

@app.route("/projects/<project_id>/delete", methods=["POST"])
def delete_project_route(project_id):
    if "access_token" not in session:
        return redirect(url_for("login"))
    result = delete_project(session["user_id"], project_id)
    if result["success"]:
        flash("Project deleted successfully.", "success")
    else:
        flash(f"Error deleting project: {result['error']}", "error")
    return redirect(url_for("my_workspace"))

@app.route("/api/trending-ideas")
def trending_ideas():
    if "access_token" not in session:
        return {"ideas": []}
    try:
        all_projects = search_projects("")
        if not all_projects:
            return {"ideas": ["Artificial Intelligence", "Machine Learning", "Data Science"]}
        random.shuffle(all_projects)
        ideas = [p["title"] for p in all_projects[:10]]
        return {"ideas": ideas}
    except Exception as e:
        print(f"❌ Trending Ideas API Error: {e}")
        return {"ideas": ["Data Science", "Web Development", "IoT"]}

@app.route("/discover")
def discover():
    if "access_token" not in session:
        return redirect(url_for("login"))
        
    query = request.args.get("q", "").strip()
    domain = request.args.get("domain", "All")
    
    # Wizard params
    wizard_mode = request.args.get("wizard", "")
    w_duration = request.args.get("duration", "")
    w_difficulty = request.args.get("difficulty", "")
    
    # Determine states
    is_wizard_home = (not wizard_mode and not query and domain == "All")
    is_domain_explore = (wizard_mode == "explore")
    is_search_mode = (wizard_mode == "search") or bool(query) or (domain != "All")
    
    results = []
    fallback_results = []
    total_pages = 1
    page = int(request.args.get("page", 1))
    
    if is_search_mode:
        # 1. Get User's Skills
        user_profile = get_user_profile(session["user_id"])
        user_skills = user_profile.get("skills_list", []) if user_profile else []
        
                # 1. Get User's Skills (Moved to the top so it's always available)
        user_profile = get_user_profile(session["user_id"])
        user_skills = user_profile.get("skills_list", []) if user_profile else []
        skills_str = " ".join(user_skills) if user_skills else ""

        # 2. Primary Strict Search
        all_results = search_projects(
            query,
            domain_filter=domain,
            difficulty_filter=w_difficulty if w_difficulty else "All",
            duration_filter=w_duration,
            team_size_filter=None 
        )
        
        # 3. FALLBACK 1: Relax Time & Difficulty (but keep Domain if selected)
        if not all_results:
            print(f"⚠️ No strict matches. Relaxing filters for '{query}'...")
            
            # If they selected a domain, keep it. If "All", ignore domain.
            fallback_domain = domain if domain != "All" else None
            
            all_results = search_projects(
                query, # Keep the search query!
                domain_filter=fallback_domain,
                difficulty_filter=None,  # Drop difficulty
                duration_filter=None,    # Drop time
                team_size_filter=None
            )
            
        # 4. FALLBACK 2: If STILL 0 results, search using just their skills
        if not all_results:
            print(f"⚠️ Still no matches. Searching by skills only...")
            fallback_domain = domain if domain != "All" else None
            
            all_results = search_projects(
                skills_str, 
                domain_filter=fallback_domain,
                difficulty_filter=None, 
                duration_filter=None, 
                team_size_filter=None
            )
            
        # 4. PAGINATION MATH
        results_per_page = 7
        total_results = len(all_results)
        total_pages = max(1, (total_results + results_per_page - 1) // results_per_page)
        
        if page < 1: page = 1
        if page > total_pages: page = total_pages
        
        start_idx = (page - 1) * results_per_page
        results = all_results[start_idx:start_idx + results_per_page]
        
        # --- THE SMART "WHY" & FEASIBILITY GENERATOR ---
        for proj in results:
            reasons = []
            is_fallback = False
            
            # 1. TIME FEASIBILITY
            proj_duration = proj.get("duration_weeks", 4)
            user_time = int(w_duration) if w_duration else 12
            
            if proj_duration <= user_time:
                time_score = 100
                if not w_difficulty or w_difficulty.lower() in str(proj.get("difficulty", "")).lower():
                    reasons.append(f"fits your {user_time}-week timeline")
            else:
                time_score = max(0, 100 - ((proj_duration - user_time) * 15))
                is_fallback = True
                
            # 2. HARDWARE FEASIBILITY
            hardware_reqs = str(proj.get("hardware_reqs", "")).lower()
            hardware_score = 100
            if "gpu" in hardware_reqs or "nvidia" in hardware_reqs:
                hardware_score = 50 
                if not is_fallback:
                    reasons.append("requires a GPU (check your resources)")
            
            # 3. SKILLS FEASIBILITY
            skill_score = 0
            if user_skills and proj.get("skills"):
                proj_skills_raw = proj.get("skills")
                if isinstance(proj_skills_raw, list):
                    proj_skills = [str(s).lower().strip() for s in proj_skills_raw]
                else:
                    proj_skills = [s.strip().lower() for s in str(proj_skills_raw).split(',')]
                
                matched = [s for s in user_skills if s.lower() in proj_skills]
                if matched:
                    skill_score = min(100, len(matched) * 30) 
                    if len(reasons) < 2:
                        reasons.append(f"utilizes your {matched[0].capitalize()} skills")
            
            # --- CALCULATE OVERALL FEASIBILITY ---
            total_score = (time_score * 0.4) + (hardware_score * 0.3) + (skill_score * 0.3)
            
            if total_score >= 80:
                proj["feasibility"] = "High"
                proj["feasibility_color"] = "#2D7A63"
            elif total_score >= 50:
                proj["feasibility"] = "Medium"
                proj["feasibility_color"] = "#EAB308"
            else:
                proj["feasibility"] = "Low"
                proj["feasibility_color"] = "#EF4444"
                
                        # We keep the semantic match score from search_service, but we can add the feasibility to the "why" reason
            
            # 4. NOVELTY
            if "advanced" in str(proj.get("difficulty", "")).lower():
                proj["novelty"] = "High"
            elif "intermediate" in str(proj.get("difficulty", "")).lower():
                proj["novelty"] = "Medium"
            else:
                proj["novelty"] = "Standard"

            # Format the "Why" reason
            if not reasons:
                proj["why_reason"] = "Recommended based on your overall profile."
            else:
                if len(reasons) == 1:
                    proj["why_reason"] = f"This project {reasons[0]}."
                else:
                    proj["why_reason"] = f"This project {reasons[0]} and {reasons[1]}."
        # ---------------------------------

    explore_domains = [
        {"name": "Artificial Intelligence", "icon": "brain-circuit", "desc": "Build systems that think and reason."},
        {"name": "Machine Learning", "icon": "trending-up", "desc": "Teach systems to learn from data."},
        {"name": "Deep Learning", "icon": "network", "desc": "Use multi-layer neural networks."},
        {"name": "Computer Vision", "icon": "eye", "desc": "Make computers understand images."},
        {"name": "Natural Language Processing", "icon": "message-square", "desc": "Understand and generate human language."},
        {"name": "IoT", "icon": "cpu", "desc": "Connect sensors and devices."},
        {"name": "Cybersecurity", "icon": "shield", "desc": "Protect systems from attacks."},
        {"name": "Data Science", "icon": "bar-chart-2", "desc": "Analyze data to discover insights."},
        {"name": "Cloud Computing", "icon": "cloud", "desc": "Deploy and scale on the cloud."}
    ]
    
    return render_template(
        "discover.html",
        results=results,
        fallback_results=fallback_results,
        query=query,
        selected_domain=domain,
        explore_domains=explore_domains,
        page=page,
        total_pages=total_pages,
        show_wizard=is_wizard_home,
        show_search_results=is_search_mode,
        wizard_mode=wizard_mode,
        w_duration=w_duration,
        w_difficulty=w_difficulty,
    )

@app.route("/projects/<project_id>")
def project_details(project_id):
    if "access_token" not in session:
        return redirect(url_for("login"))
    project = get_project_by_id(project_id)
    if not project:
        flash("Project not found.", "error")
        return redirect(url_for("discover"))
    bookmarked = is_bookmarked(session["user_id"], project_id)
    return render_template("project_details.html", project=project, bookmarked=bookmarked)

@app.route("/projects/<project_id>/start", methods=["POST"])
def start_project(project_id):
    if "access_token" not in session:
        return redirect(url_for("login"))
    catalogue_project = get_project_by_id(project_id)
    if not catalogue_project:
        flash("Project not found.", "error")
        return redirect(url_for("discover"))
        
    duration_weeks = int(request.form.get("duration_weeks", 4))
    
    result = start_project_workspace(session["user_id"], catalogue_project, duration_weeks)
    
    if result["success"]:
        if not result.get("already_existed"):
            generate_timeline_reminders(session["user_id"], result["project_id"], duration_weeks)
            
            # --- SEND STARTED EMAIL ---
            try:
                send_project_started_email(
                    session["user_email"], 
                    session.get("full_name", "Student"), 
                    catalogue_project['title'], 
                    duration_weeks
                )
            except Exception as e:
                print(f"Failed to send start email: {e}")
            # --------------------------
            
            flash("Project started! Your roadmap and timeline reminders are ready.", "success")
        else:
            flash("Resumed your existing project.", "success")
            
        return redirect(url_for("workspace", project_id=result["project_id"]))
    else:
        flash(f"FAILED TO START: {result['error']}", "error")
        return redirect(url_for("project_details", project_id=project_id))

@app.route("/workspace/<project_id>")
def workspace(project_id):
    if "access_token" not in session:
        return redirect(url_for("login"))
    workspace_data = get_project_workspace(session["user_id"], project_id)
    if not workspace_data:
        flash("Workspace not found or you don't have access.", "error")
        return redirect(url_for("dashboard"))
    return render_template("workspace.html", project=workspace_data["project"], tasks=workspace_data["tasks"])

@app.route("/tasks/<task_id>/complete", methods=["POST"])
def complete_task(task_id):
    if "access_token" not in session:
        return redirect(url_for("login"))
    result = complete_task_and_unlock_next(session["user_id"], task_id)
    if result["success"]:
        flash("Task completed! Next step unlocked.", "success")
        return redirect(url_for("workspace", project_id=result["project_id"]))
    else:
        flash(f"Error: {result['error']}", "error")
        return redirect(request.referrer or url_for("dashboard"))

@app.route("/workspace/<project_id>/propose", methods=["POST"])
def propose_feature(project_id):
    if "access_token" not in session:
        return redirect(url_for("login"))
        
    idea_text = request.form.get("idea_text")
    if not idea_text:
        return redirect(url_for("workspace", project_id=project_id))
        
    workspace_data = get_project_workspace(session["user_id"], project_id)
    project = workspace_data["project"]
    
    system_prompt = "You are an expert technical project manager. You evaluate if new feature ideas fit an existing project."
    prompt = f"""
    Current Project: {project['title']} - {project['description']}
    
    The student wants to add this new feature: "{idea_text}"
    
    1. Evaluate if this is a good fit for the project's scope. 
    2. If it is a good fit, generate ONE new roadmap step for this feature with 3 sub-tasks.
    3. If it is a bad fit, explain WHY it doesn't fit.
    
    Return ONLY JSON format:
    {{
      "is_good_fit": true/false,
      "reason": "Why it is good or bad.",
      "step": {{
        "title": "Step Title",
        "description": "Detailed technical explanation of how to build this feature.",
        "tasks": ["Task 1", "Task 2", "Task 3"]
      }}
    }}
    """
    
    try:
        response_text, _ = generate_ai_response(prompt, system_prompt)
        response_text = response_text.replace("```json", "").replace("```", "").strip()
        result = json.loads(response_text)
        
        if result.get("is_good_fit"):
            append_custom_step(session["user_id"], project_id, result["step"])
            flash(f"Feature added! {result['reason']}", "success")
        else:
            flash(f"Idea rejected by AI: {result['reason']}", "error")
            
    except Exception as e:
        flash(f"AI Error: {str(e)}", "error")
        
    return redirect(url_for("workspace", project_id=project_id))

@app.route("/bookmarks")
def bookmarks():
    if "access_token" not in session:
        return redirect(url_for("login"))
    user_bookmarks = get_user_bookmarks(session["user_id"])
    return render_template("bookmarks.html", bookmarks=user_bookmarks)

@app.route("/bookmarks/toggle/<project_id>", methods=["POST"])
def toggle_bookmark_route(project_id):
    if "access_token" not in session:
        return redirect(url_for("login"))
    project = get_project_by_id(project_id)
    if not project:
        flash("Project not found.", "error")
        return redirect(url_for("discover"))
    result = toggle_bookmark(session["user_id"], project)
    if result["success"]:
        flash("Project bookmarked!" if result["action"] == "added" else "Bookmark removed.", "success")
    else:
        flash(f"Error: {result['error']}", "error")
    return redirect(request.referrer or url_for("discover"))

@app.route("/reminders")
def reminders():
    if "access_token" not in session:
        return redirect(url_for("login"))
        
    grouped_reminders = get_user_reminders(session["user_id"])
    
    return render_template("reminders.html", grouped_reminders=grouped_reminders)

@app.route("/reminders/add", methods=["POST"])
def add_reminder_route():
    if "access_token" not in session:
        return redirect(url_for("login"))
    title = request.form.get("title")
    due_date = request.form.get("due_date")
    if title and due_date:
        result = add_reminder(session["user_id"], title, due_date)
        if result["success"]:
            flash("Reminder added!", "success")
        else:
            flash(f"Error: {result['error']}", "error")
    return redirect(url_for("reminders"))

@app.route("/reminders/delete/<reminder_id>", methods=["POST"])
def delete_reminder_route(reminder_id):
    if "access_token" not in session:
        return redirect(url_for("login"))
    result = delete_reminder(session["user_id"], reminder_id)
    if result["success"]:
        flash("Reminder deleted.", "success")
    else:
        flash(f"Error: {result['error']}", "error")
    return redirect(url_for("reminders"))

@app.route("/mentor", methods=["GET", "POST"])
def mentor():
    if "access_token" not in session:
        return redirect(url_for("login"))
        
    active_project = get_active_project(session["user_id"])
    all_projects = get_all_user_projects(session["user_id"])
    context_id = request.args.get("context", "General")
    return_to = request.args.get("return_to", "/dashboard") 
    
    context_title = "General Question"
    if context_id != "General":
        for p in all_projects:
            if str(p["id"]) == str(context_id):
                context_title = p["title"]
                break
                
    if request.method == "POST":
        user_message = request.form.get("message")
        if user_message:
            save_chat_message(session["user_id"], context_id, "user", user_message)
            system_prompt = "You are a friendly, helpful academic project advisor. Keep answers concise."
            if context_id != "General":
                system_prompt += f" The student is asking about their project titled '{context_title}'."
            try:
                ai_response, provider = generate_ai_response(user_message, system_prompt)
                ai_response_html = markdown.markdown(ai_response, extensions=['tables', 'fenced_code'])
            except Exception as e:
                ai_response_html = f"Error: {str(e)}"
            save_chat_message(session["user_id"], context_id, "ai", ai_response_html)
        return redirect(url_for("mentor", context=context_id, return_to=return_to))
        
    chat_history = get_chat_history(session["user_id"], context_id)
    
    suggested_prompts = []
    if not chat_history:
        if context_id == "General":
            suggested_prompts = ["How do I write a strong problem statement?", "What is the difference between supervised and unsupervised learning?", "Give me 3 dataset ideas for a sentiment analysis project.", "How do I structure my literature review?"]
        else:
            prompt_for_questions = f"Generate 4 short, specific questions a student might ask about their project titled '{context_title}'. Return them as a plain list separated by newlines."
            try:
                questions_text, _ = generate_ai_response(prompt_for_questions, "You are an academic advisor.")
                suggested_prompts = [q.strip("- ").strip() for q in questions_text.split("\n") if q.strip()]
            except:
                suggested_prompts = [f"What dataset should I use for {context_title}?", "How do I evaluate the success of this project?", "Can you give me a code snippet to get started?", "What are the main challenges in this project?"]
    
    return render_template("mentor.html", all_projects=all_projects, chat_history=chat_history, context_id=context_id, context_title=context_title, return_to=return_to, suggested_prompts=suggested_prompts)

@app.route("/mentor/clear")
def clear_chat():
    context_id = request.args.get("context", "General")
    clear_chat_history(session["user_id"], context_id)
    return redirect(url_for("mentor", context=context_id))

@app.route("/projects/custom/start")
def custom_project_start():
    if "access_token" not in session:
        return redirect(url_for("login"))
    session["custom_chat"] = [{"role": "ai", "content": "Hi! I'm your project architect. Tell me about the project idea you have in mind. What are you trying to build?"}]
    session.pop("custom_project_data", None)
    return render_template("custom_wizard.html", chat=session["custom_chat"], is_ready=False, project_data=None)

@app.route("/projects/custom/chat", methods=["POST"])
def custom_project_chat():
    if "access_token" not in session:
        return redirect(url_for("login"))
    user_message = request.form.get("message")
    if not user_message:
        return redirect(url_for("custom_project_start"))
        
    chat = session.get("custom_chat", [])
    chat.append({"role": "user", "content": user_message})
    ai_response = get_next_question(chat)
    
    if ai_response.get("status") == "READY":
        project_title = ai_response.get("project_title", "Custom Project")
        description = ai_response.get("description", user_message)
        domain = ai_response.get("domain", "General")
        roadmap_steps = generate_custom_roadmap(project_title, description, domain, chat)
        
        if not roadmap_steps:
            flash("Failed to generate roadmap. Please try again.", "error")
            return redirect(url_for("custom_project_start"))
            
        result = create_custom_workspace(session["user_id"], project_title, description, domain, "Intermediate", roadmap_steps)
        if result["success"]:
            session.pop("custom_chat", None)
            flash("Your custom project and roadmap are ready!", "success")
            return redirect(url_for("workspace", project_id=result["project_id"]))
        else:
            flash(f"Database error: {result['error']}", "error")
            return redirect(url_for("custom_project_start"))
            
    elif ai_response.get("status") == "ASKING":
        question = ai_response.get("question", "Can you tell me more about your project?")
        chat.append({"role": "ai", "content": question})
        session["custom_chat"] = chat
        return render_template("custom_wizard.html", chat=chat, is_ready=False, project_data=None)
    else:
        flash("The AI got confused. Let's try starting over.", "error")
        return redirect(url_for("custom_project_start"))

@app.route("/analyzer")
def analyzer():
    if "access_token" not in session:
        return redirect(url_for("login"))
    return render_template("analyzer.html", analysis=None, page=1)

@app.route("/analyzer/upload", methods=["POST"])
def analyzer_upload():
    if "access_token" not in session:
        return redirect(url_for("login"))
        
    file = request.files.get("project_file")
    goal = request.form.get("goal", "expand")
    
    if not file:
        flash("Please select a file.", "error")
        return redirect(url_for("analyzer"))
        
    text, error = extract_text_from_file(file)
    if error:
        flash(error, "error")
        return redirect(url_for("analyzer"))
        
    analysis = analyze_existing_project(text, goal)
    if "error" in analysis:
        flash(analysis["error"], "error")
        return redirect(url_for("analyzer"))
        
    session["analyzer_result"] = analysis
    return redirect(url_for("analyzer_view", page=1))

@app.route("/analyzer/view")
def analyzer_view():
    if "access_token" not in session:
        return redirect(url_for("login"))
        
    analysis = session.get("analyzer_result")
    if not analysis:
        flash("Please upload a file first.", "error")
        return redirect(url_for("analyzer"))
        
    page = int(request.args.get("page", 1))
    total_ideas = len(analysis["ideas"])
    
    if page < 1: page = 1
    if page > total_ideas: page = total_ideas
    
    current_idea = analysis["ideas"][page - 1]
    
    return render_template("analyzer.html", analysis=analysis, current_idea=current_idea, page=page, total_ideas=total_ideas)

@app.route("/analyzer/generate/<int:idea_index>")
def analyzer_generate(idea_index):
    if "access_token" not in session:
        return redirect(url_for("login"))
        
    analysis = session.get("analyzer_result")
    if not analysis or "ideas" not in analysis:
        flash("Analysis session expired.", "error")
        return redirect(url_for("analyzer"))
        
    try:
        idea = analysis["ideas"][idea_index]
        result = create_custom_workspace(
            session["user_id"], idea["title"], idea["description"], idea["domain"], "Advanced", idea["roadmap"]
        )
        if result["success"]:
            session.pop("analyzer_result", None)
            flash("Expanded project created! Here is your new roadmap.", "success")
            return redirect(url_for("workspace", project_id=result["project_id"]))
        else:
            flash(f"Database error: {result['error']}", "error")
            return redirect(url_for("analyzer"))
    except IndexError:
        flash("Invalid idea selected.", "error")
        return redirect(url_for("analyzer"))

@app.route("/studio", methods=["GET", "POST"])
def studio():
    if "access_token" not in session:
        return redirect(url_for("login"))
    active_project = get_active_project(session["user_id"])
    draft = None
    active_tool = "abstract"
    if request.method == "POST":
        active_tool = request.form.get("tool_type", "abstract")
        draft, provider = generate_academic_draft(session["user_id"], active_project, active_tool)
    return render_template("studio.html", active_project=active_project, draft=draft, active_tool=active_tool)

@app.route("/research")
def research():
    if "access_token" not in session:
        return redirect(url_for("login"))
    query = request.args.get("q", "")
    results = search_arxiv(query) if query else []
    return render_template("research.html", query=query, results=results)

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if "access_token" not in session:
        return redirect(url_for("login"))
        
    user_id = session["user_id"]
    
    if request.method == "POST":
        full_name = request.form.get("full_name")
        degree = request.form.get("degree_level")
        if degree == "Other":
            degree = request.form.get("custom_degree", "Other")
        dept = request.form.get("department")
        skills_str = request.form.get("skills", "")
        skills_list = [s.strip() for s in skills_str.split(",") if s.strip()]
        
        result = update_user_profile(user_id, full_name, degree, dept, skills_list)
        if result["success"]:
            flash("Profile updated successfully!", "success")
            # Update the session name just in case they changed it
            session["full_name"] = full_name
        else:
            flash(f"Error updating profile: {result['error']}", "error")
            
        return redirect(url_for("settings"))
        
    # GET Request - Fetch current data
    profile = get_user_profile(user_id)
    # Convert the skills array back to a comma-separated string for the input field
    if profile and profile.get("skills_list"):
        profile["skills_string"] = ", ".join(profile["skills_list"])
    else:
        profile["skills_string"] = ""
        
    return render_template("settings.html", profile=profile)

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/workspace/<project_id>/download_pdf")
def download_pdf(project_id):
    if "access_token" not in session:
        return redirect(url_for("login"))
        
    workspace_data = get_project_workspace(session["user_id"], project_id)
    if not workspace_data:
        flash("Workspace not found.", "error")
        return redirect(url_for("dashboard"))
        
    project = workspace_data["project"]
    tasks = workspace_data["tasks"]
    
    # Ask AI to generate the text for Objectives, Methodology, Datasets, Viva
    print("📄 Generating PDF Content...")
    prompt = f"""
    You are an academic thesis advisor. Generate the following sections for a project titled "{project['title']}".
    Description: {project['description']}
    
    Format the output as a valid JSON object with exactly these keys:
    {{
      "objectives": "3-4 clear objectives separated by newlines",
      "methodology": "A short paragraph explaining the technical approach and algorithm",
      "datasets": "2-3 specific dataset names and links (e.g., Kaggle, UCI)",
      "viva": "3 potential viva questions with short answers separated by newlines"
    }}
    """
    
    try:
        ai_text, _ = generate_ai_response(prompt, "You are an academic advisor. Return ONLY valid JSON.")
        ai_text = ai_text.replace("```json", "").replace("```", "").strip()
        ai_content = json.loads(ai_text)
    except Exception as e:
        print(f"AI Generation failed: {e}")
        ai_content = {} 
        
    # Generate the PDF
    pdf_buffer = generate_project_proposal_pdf(project, tasks, ai_content)
    
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"{project['title'].replace(' ', '_')}_Proposal.pdf",
        mimetype='application/pdf'
    )

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, port=5000)