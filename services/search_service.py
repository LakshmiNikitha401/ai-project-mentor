import os
import psycopg2
import pickle
import numpy as np
from psycopg2.extras import RealDictCursor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from fastembed import TextEmbedding
from dotenv import load_dotenv

load_dotenv()
db_url = os.environ.get("DATABASE_URL")

# Load FastEmbed model lazily to save memory on startup
print("⏳ Loading FastEmbed model...")
semantic_model = None
embeddings_data = None

try:
    with open('project_embeddings.pkl', 'rb') as f:
        embeddings_data = pickle.load(f)
    print("✅ Semantic embeddings loaded successfully.")
except FileNotFoundError:
    print("⚠️ Warning: project_embeddings.pkl not found. Run generate_embeddings.py first!")

def get_db():
    return psycopg2.connect(db_url)

def get_semantic_model():
    global semantic_model
    if semantic_model is None:
        print("⏳ Initializing FastEmbed model...")
        # Default model is BAAI/bge-small-en-v1.5 (384 dims) [citation:1]
        semantic_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        print("✅ FastEmbed model ready.")
    return semantic_model

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

    if not query or not query.strip():
        for p in projects:
            p["difficulty"] = str(p.get("difficulty", "")).capitalize()
        projects.sort(key=lambda x: x.get("duration_weeks", 99))
        return [dict(p, match_score=0, match_reason="Matches your filters.") for p in projects]

    # --- HYBRID SCORING ---
    q_lower = query.lower()
    results = []
    
    # 1. Get Query Embedding from FastEmbed
    query_embedding = None
    if embeddings_data:
        try:
            model = get_semantic_model()
            # FastEmbed returns a generator, so we convert to list and get the first item
            query_embedding = list(model.embed([q_lower]))[0]
        except Exception as e:
            print(f"❌ FastEmbed error: {e}")

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
        
        semantic_score_pct = 0
        if query_embedding is not None and embeddings_data:
            try:
                idx = embeddings_data['ids'].index(proj_id)
                proj_embedding = embeddings_data['embeddings'][idx]
                # Ensure both are numpy arrays for dot product
                q_emb = np.array(query_embedding)
                p_emb = np.array(proj_embedding)
                semantic_score = np.dot(q_emb, p_emb) / (np.linalg.norm(q_emb) * np.linalg.norm(p_emb))
                semantic_score_pct = float(semantic_score) * 100
            except (ValueError, IndexError):
                pass
        
        tfidf_score_pct = tfidf_scores[i] * 100
        
        # If semantic is missing, rely 100% on TF-IDF
        if semantic_score_pct == 0:
            final_score = tfidf_score_pct
        else:
            final_score = (semantic_score_pct * 0.6) + (tfidf_score_pct * 0.4)
        
        proj_dict["match_score"] = round(final_score, 1)
        proj_dict["difficulty"] = str(proj_dict.get("difficulty", "")).capitalize()
        results.append(proj_dict)

    results = sorted(results, key=lambda x: x["match_score"], reverse=True)
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
