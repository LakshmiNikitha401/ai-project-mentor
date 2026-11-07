import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_project_proposal_pdf(project, roadmap_tasks, ai_content):
    """
    Generates a styled PDF proposal for the project.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    story = []

    # --- STYLES ---
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'TitleStyle', parent=styles['Heading1'], fontName='Times-Bold', fontSize=24, spaceAfter=20, alignment=1
    )
    heading_style = ParagraphStyle(
        'HeadingStyle', parent=styles['Heading2'], fontName='Times-Bold', fontSize=16, spaceBefore=20, spaceAfter=10, textColor=colors.HexColor('#1F2937')
    )
    normal_style = ParagraphStyle(
        'NormalStyle', parent=styles['Normal'], fontName='Times-Roman', fontSize=12, leading=16, spaceAfter=10
    )
    bullet_style = ParagraphStyle(
        'BulletStyle', parent=normal_style, leftIndent=20, bulletIndent=10
    )

    # --- HEADER ---
    story.append(Paragraph("AI Project Mentor", ParagraphStyle('Header', fontName='Times-Roman', fontSize=10, alignment=1, textColor=colors.gray)))
    story.append(Spacer(1, 20))
    story.append(Paragraph(f"{project['title']} Project Proposal", title_style))
    story.append(Spacer(1, 10))

    # --- ABSTRACT / DESCRIPTION ---
    story.append(Paragraph("1. Project Abstract", heading_style))
    story.append(Paragraph(project.get('description', 'No description provided.'), normal_style))
    story.append(Spacer(1, 10))

    # --- OBJECTIVES ---
    story.append(Paragraph("2. Objectives", heading_style))
    story.append(Paragraph(ai_content.get('objectives', 'To design and implement a robust system based on the proposed methodology.'), normal_style))
    story.append(Spacer(1, 10))

    # --- METHODOLOGY / TECH STACK ---
    story.append(Paragraph("3. Proposed Methodology", heading_style))
    story.append(Paragraph(ai_content.get('methodology', 'The project will follow an Agile methodology, starting with data acquisition, followed by model development, evaluation, and deployment.'), normal_style))
    
    story.append(Paragraph("Technology Stack", heading_style))
    stack_text = ", ".join(project.get('skills', [])) if isinstance(project.get('skills'), list) else project.get('skills', 'Python, Machine Learning')
    story.append(Paragraph(stack_text, normal_style))
    story.append(Spacer(1, 10))

    # --- DATASETS ---
    story.append(Paragraph("4. Suggested Datasets", heading_style))
    story.append(Paragraph(ai_content.get('datasets', 'Kaggle, UCI Machine Learning Repository, or custom domain-specific datasets.'), normal_style))
    story.append(Spacer(1, 10))
    
    # --- ROADMAP ---
    story.append(PageBreak())
    story.append(Paragraph("5. Week-by-Week Implementation Plan", heading_style))
    story.append(Spacer(1, 10))

    for index, task in enumerate(roadmap_tasks):
        story.append(Paragraph(f"<b>Phase {index + 1}: {task['title']}</b>", normal_style))
        story.append(Paragraph(task['description'], normal_style))
        if task.get('sub_tasks'):
            for sub in task['sub_tasks']:
                story.append(Paragraph(f"• {sub}", bullet_style))
        story.append(Spacer(1, 10))

    # --- VIVA QUESTIONS ---
    story.append(PageBreak())
    story.append(Paragraph("6. Preparation for Viva", heading_style))
    story.append(Paragraph(ai_content.get('viva', 'Be prepared to explain your architecture, dataset choice, and evaluation metrics.'), normal_style))

    # --- BUILD PDF ---
    doc.build(story)
    buffer.seek(0)
    return buffer