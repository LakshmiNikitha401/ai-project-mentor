import os
import psycopg2
import pickle
import numpy as np
from psycopg2.extras import RealDictCursor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()
db_url = os.environ.get("DATABASE_URL")

# Load the Semantic Model and Embeddings globally so they stay in memory
print("⏳ Loading Sentence-BERT model...")
semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings_data = None
try:
    with open('project_embeddings.pkl', 'rb') as f:
        embeddings_data = pickle.load(f)
    print("✅ Semantic embeddings loaded successfully.")
except FileNotFoundError:
    print("⚠️ Warning: project_embeddings.pkl not found. Run generate_embeddings.py first!")

def get_db():
    return psycopg2.connect(db_url)

def search_projects(query, domain_filter=None, difficulty_filter=None, duration_filter=None, team_size_filter=None):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    sql = "SELECT * FROM catalogue_projects WHERE 1=1"
    params = []
    
    # --- DOMAIN FILTER ---
    if domain_filter and domain_filter != "All":
        domain_map = {
            "Artificial Intelligence": ["Artificial Intelligence", "AI"],
            "Machine Learning": ["Machine Learning", "ML"],
            "Deep Learning": ["Deep Learning", "DL"],
            "Computer Vision": ["Computer Vision", "CV"],
            "Natural Language Processing": ["Natural Language Processing", "NLP"],
            "IoT": ["IoT", "Internet of Things"],
            "Data Science": ["Data Science", "DS"],
            "Cloud Computing": ["Cloud Computing", "Cloud"]
        }
        search_terms = domain_map.get(domain_filter, [domain_filter])
        clauses = []
        for term in search_terms:
            clauses.append("domain ILIKE %s")
            clauses.append("domain ILIKE %s")
            clauses.append("domain ILIKE %s")
            params.append(f"{term}%")
            params.append(f"% {term}%")
            params.append(f"%,{term}%")
        sql += f" AND ({' OR '.join(clauses)})"
        
    # --- DIFFICULTY FILTER ---
    if difficulty_filter and difficulty_filter != "All":
        diff = difficulty_filter.lower()
        if diff == "beginner":
            sql += " AND (difficulty ILIKE 'beginner' OR difficulty ILIKE 'beginner to intermediate')"
        elif diff == "intermediate":
            sql += " AND (difficulty ILIKE 'intermediate' OR difficulty ILIKE 'beginner to intermediate' OR difficulty ILIKE 'intermediate to advanced')"
        elif diff == "advanced":
            sql += " AND (difficulty ILIKE 'advanced' OR difficulty ILIKE 'intermediate to advanced')"
            
    # --- DURATION FILTER ---
    if duration_filter and str(duration_filter) != "":
        try:
            max_time = int(duration_filter)
            if max_time < 12:
                sql += " AND duration_weeks <= %s"
                params.append(max_time + 2) 
        except ValueError:
            pass
            
    # Execute SQL
    try:
        cursor.execute(sql, params)
        projects = cursor.fetchall()
    except Exception as e:
        print(f"❌ DB Error executing search: {e}")
        projects = []
    finally:
        cursor.close()
        conn.close()

    if not projects:
        return []

    # If no query, return them sorted by duration
    if not query or not query.strip():
        for p in projects:
            p["difficulty"] = str(p.get("difficulty", "")).capitalize()
        projects.sort(key=lambda x: x.get("duration_weeks", 99))
        return [dict(p, match_score=0, match_reason="Matches your filters.") for p in projects]

    # --- HYBRID SCORING ---
    q_lower = query.lower()
    results = []
    
    # 1. Prepare Semantic Search
    query_embedding = semantic_model.encode([q_lower])
    
    # 2. Prepare TF-IDF
    corpus = [f"{p['title']} {p['description']} {p.get('domain', '')} {p.get('skills', '')}".lower() for p in projects]
    vectorizer = TfidfVectorizer(stop_words='english')
    try:
        tfidf_matrix = vectorizer.fit_transform(corpus)
        tfidf_query = vectorizer.transform([q_lower])
        tfidf_scores = cosine_similarity(tfidf_query, tfidf_matrix).flatten()
    except ValueError:
        tfidf_scores = [0.0] * len(projects)

    # 3. Combine Scores
    for i, project in enumerate(projects):
        proj_dict = dict(project)
        proj_id = proj_dict['id']
        
        # Calculate Semantic Score
        semantic_score = 0
        if embeddings_data:
            try:
                # Find the index of this project in the embeddings file
                idx = embeddings_data['ids'].index(proj_id)
                proj_embedding = embeddings_data['embeddings'][idx]
                # Calculate cosine similarity between query and project
                semantic_score = np.dot(query_embedding, proj_embedding) / (np.linalg.norm(query_embedding) * np.linalg.norm(proj_embedding))
            except ValueError:
                pass
        
        # Normalize scores to 0-100
        tfidf_score_pct = tfidf_scores[i] * 100
        semantic_score_pct = float(semantic_score[0] * 100) if isinstance(semantic_score, np.ndarray) else float(semantic_score * 100)
        
        # Hybrid Formula: 60% Semantic, 40% TF-IDF (Weights can be adjusted)
        final_score = (semantic_score_pct * 0.6) + (tfidf_score_pct * 0.4)
        
        proj_dict["match_score"] = round(final_score, 1)
        proj_dict["difficulty"] = str(proj_dict.get("difficulty", "")).capitalize()
        
        # Explainability
        if semantic_score_pct > 50:
            proj_dict["match_reason"] = "High semantic relevance to your idea."
        elif tfidf_score_pct > 30:
            proj_dict["match_reason"] = "Matches keywords in your search."
            
        results.append(proj_dict)

    # Sort by the combined score
    results = sorted(results, key=lambda x: x["match_score"], reverse=True)
    
    # Filter out poor matches if we have enough good ones
    if len(results) > 10:
        results = [r for r in results if r["match_score"] > 10]

    return results

def get_project_by_id(project_id):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM catalogue_projects WHERE id = %s", (project_id,))
    project = cursor.fetchone()
    cursor.close()
    conn.close()
    if project:
        project["difficulty"] = str(project.get("difficulty", "")).capitalize()
    return project