import os
from services.ai_service import generate_ai_response # Use the working AI file

def generate_academic_draft(user_id, active_project, tool_type):
    """
    Generates academic content based on the active project and selected tool.
    """
    if not active_project:
        return "Please start a project first so I have context to write your draft.", "error"

    project_title = active_project.get("title", "")
    project_domain = active_project.get("domain", "")
    project_desc = active_project.get("description", "")

    system_prompt = (
        "You are an expert academic thesis advisor. You write formal, academic, "
        "and technically precise content suitable for an M.Tech thesis. "
        "Do not use conversational language. Use markdown formatting."
    )

    # Base context for all tools
    context = f"Project Title: {project_title}\nDomain: {project_domain}\nDescription: {project_desc}\n\n"

    # Generate specific prompts based on the tool selected
    if tool_type == "abstract":
        prompt = context + "Write a 250-word formal academic abstract for this project. Include the problem statement, proposed methodology, and expected outcomes."
    
    elif tool_type == "problem_statement":
        prompt = context + "Write a detailed Problem Statement for this project. Explain the current gap in the domain, why existing solutions are insufficient, and what this project aims to solve."
    
    elif tool_type == "methodology":
        prompt = context + "Write a comprehensive Methodology section for this project. Detail the system architecture, algorithms to be used, dataset requirements, and the step-by-step implementation plan."
    
    elif tool_type == "objectives":
        prompt = context + "List 4-5 clear, measurable Objectives for this project. Format them as a bulleted list."
    
    elif tool_type == "viva":
        prompt = context + "Generate 10 potential Viva (oral exam) questions for this project, along with concise, confident 1-sentence answers for the student to study."
    
    elif tool_type == "report":
        prompt = context + "Create a detailed Table of Contents and a 1-page Introduction for the final Project Report."
    
    else:
        prompt = context + "Provide a brief summary of this project."

    print(f"⏳ Generating {tool_type} for project: {project_title}")
    draft, provider = generate_ai_response(prompt, system_prompt)
    return draft, provider