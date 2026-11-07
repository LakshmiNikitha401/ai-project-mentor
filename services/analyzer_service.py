import io
import json
from PyPDF2 import PdfReader
import docx
from services.ai_service import generate_ai_response

def extract_text_from_file(file):
    """Extracts text from PDF, DOCX, or TXT files."""
    filename = file.filename.lower()
    text = ""
    
    try:
        if filename.endswith(".pdf"):
            reader = PdfReader(io.BytesIO(file.read()))
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        elif filename.endswith(".docx"):
            doc = docx.Document(io.BytesIO(file.read()))
            for para in doc.paragraphs:
                text += para.text + "\n"
        elif filename.endswith(".txt"):
            text = file.read().decode("utf-8", errors="ignore")
        else:
            return None, "Unsupported file type. Please upload PDF, DOCX, or TXT."
            
        if not text.strip():
            return None, "Could not extract text. The file might be a scanned image."
            
        return text.strip(), None
    except Exception as e:
        return None, f"Error reading file: {str(e)}"

def analyze_existing_project(text, goal="expand"):
    """
    Analyzes the text and generates expansion/pivot ideas.
    """
    system_prompt = "You are an expert academic project consultant. You analyze existing projects and suggest upgrades for a Major thesis."
    
    # We limit text to 10,000 characters to avoid overwhelming the AI
    truncated_text = text[:10000]
    
    prompt = f"""
    Analyze the following existing project text:
    \"\"\"
    {truncated_text}
    \"\"\"
    
    Goal: The student wants to turn this into a Major project. 
    If 'expand', suggest adding advanced features (ML, deployment, UI).
    If 'pivot', suggest changing the domain slightly to make it unique.
    
    STRICT RULES:
    1. Generate as many specific, high-quality ways they can expand this project as you can think of. Usually between 3 and 6 ideas.
    2. Each idea must have a "title", "description", "domain", and a 4-5 step "roadmap".
    
    Return ONLY a valid JSON response with:
    {{
      "summary": "A 2-sentence summary of what the current project does.",
      "ideas": [
        {{
          "title": "...",
          "description": "...",
          "domain": "...",
          "roadmap": [
            {{"title": "Step 1", "description": "Detailed instructions", "tasks": ["task1", "task2"]}}
          ]
        }}
      ]
    }}
    """
    
    try:
        response_text, _ = generate_ai_response(prompt, system_prompt)
        response_text = response_text.replace("```json", "").replace("```", "").strip()
        return json.loads(response_text)
    except Exception as e:
        print(f"❌ Analyzer AI Error: {e}")
        return {"error": "Failed to analyze the document. Please try again."}