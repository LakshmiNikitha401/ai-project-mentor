import json
from services.ai_service import generate_ai_response

def get_next_question(conversation_history):
    """
    Reads the chat history and decides if it needs to ask another question 
    or if it's ready to generate the roadmap.
    """
    system_prompt = (
        "You are an expert academic project architect. You help students refine their project ideas "
        "into solid, feasible academic projects. You ask one question at a time to understand: "
        "1. The core problem and target users. "
        "2. The dataset or resources available. "
        "3. The technical stack they are comfortable with. "
        "4. The timeline/feasibility."
    )
    
    # Format history for the AI
    history_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in conversation_history])
    
    prompt = f"""
    Here is the conversation so far:
    {history_text}
    
    Your task:
    - If you have enough information to build a detailed technical roadmap, return EXACTLY this JSON:
    {{"status": "READY", "project_title": "...", "description": "...", "domain": "..."}}
    - If you need more information, ask ONE highly specific question to clarify the scope. Return EXACTLY this JSON:
    {{"status": "ASKING", "question": "Your specific question here"}}
    
    Return ONLY the raw JSON. No markdown, no backticks.
    """
    
    try:
        response_text, _ = generate_ai_response(prompt, system_prompt)
        # Clean up markdown if the AI hallucinated it
        response_text = response_text.replace("```json", "").replace("```", "").strip()
        return json.loads(response_text)
    except Exception as e:
        print(f"❌ Custom Project AI Error: {e}")
        return {"status": "ERROR", "question": "I'm having trouble analyzing your idea right now. Can you rephrase that?"}

def generate_custom_roadmap(project_title, description, domain, conversation_history):
    """
    Generates the final 6-9 step roadmap once the AI has all the info.
    """
    system_prompt = "You are a senior engineer designing a roadmap for a student thesis."
    
    history_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in conversation_history])
    
    prompt = f"""
    Based on the following project and the student's constraints discussed in the conversation, generate a detailed 6 to 9 step technical roadmap.
    
    Project Title: {project_title}
    Description: {description}
    Domain: {domain}
    Conversation Context:
    {history_text}
    
    Return ONLY a valid JSON array. Format:
    [
      {{"title": "Step Title", "description": "Detailed technical explanation.", "tasks": ["Task 1", "Task 2", "Task 3"]}}
    ]
    """
    
    try:
        response_text, _ = generate_ai_response(prompt, system_prompt)
        response_text = response_text.replace("```json", "").replace("```", "").strip()
        return json.loads(response_text)
    except Exception as e:
        print(f"❌ Roadmap generation failed: {e}")
        return [] # Fallback to empty