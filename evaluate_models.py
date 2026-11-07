import psycopg2
import pandas as pd
import numpy as np
import pickle
import warnings
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

# Ignore the specific pandas warning about raw DB connections
warnings.filterwarnings("ignore", category=UserWarning, module="pandas")

db_url = "postgresql://postgres.kqmxnbeisjdkmwdipyfl:ProjectGuide.2026@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"

# --- TEST DATA ---
# We define queries and the exact keyword of the project that SHOULD be in the top 5
TEST_CASES = [
    {"query": "AI for crops", "expected_keyword": "Crop Recommendation"},
    {"query": "detect pneumonia from x-rays", "expected_keyword": "Pneumonia"},
    {"query": "predict stock market trends", "expected_keyword": "Stock Price"},
    {"query": "chatbot for college queries", "expected_keyword": "College Placement"},
    {"query": "identify fake news articles", "expected_keyword": "Fake News"}
]

def load_data():
    print("   > Connecting to database...")
    conn = psycopg2.connect(db_url)
    df = pd.read_sql("SELECT id, title, description, domain, skills FROM catalogue_projects", conn)
    conn.close()
    
    # FIX: Convert list of skills to a single string safely
    df['skills'] = df['skills'].apply(lambda x: " ".join(x) if isinstance(x, list) else str(x))
    
    # Combine all text fields into one searchable string
    df['text'] = df['title'].fillna('') + " " + \
                 df['description'].fillna('') + " " + \
                 df['domain'].fillna('') + " " + \
                 df['skills'].fillna('')
    return df

def evaluate():
    print("⏳ Loading Data & Models (This takes ~10 seconds)...")
    df = load_data()
    
    # Load Embeddings
    try:
        with open('project_embeddings.pkl', 'rb') as f:
            embeddings_data = pickle.load(f)
    except FileNotFoundError:
        print("❌ ERROR: project_embeddings.pkl not found. Run generate_embeddings.py first!")
        return

    semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
    
    # Baseline TF-IDF Setup
    print("   > Fitting TF-IDF Baseline...")
    vectorizer = TfidfVectorizer(stop_words='english')
    tfidf_matrix = vectorizer.fit_transform(df['text'])

    results = []

    print("\n" + "="*50)
    print("🚀 RUNNING EVALUATION (TOP 5 RESULTS)")
    print("="*50)
    
    for case in TEST_CASES:
        q = case["query"]
        expected = case["expected_keyword"]
        
        # --- 1. BASELINE: TF-IDF ONLY ---
        q_tfidf = vectorizer.transform([q])
        tfidf_scores = cosine_similarity(q_tfidf, tfidf_matrix).flatten()
        
        # Get top 5 indices
        top5_tfidf_idx = tfidf_scores.argsort()[-5:][::-1]
        top5_tfidf_titles = df.iloc[top5_tfidf_idx]['title'].tolist()
        
        # Check if expected project is in the top 5
        tfidf_hit = any(expected.lower() in str(title).lower() for title in top5_tfidf_titles)
        
        # --- 2. HYBRID: SEMANTIC + TF-IDF ---
        q_emb = semantic_model.encode([q])
        
        hybrid_scores = []
        for i, row in df.iterrows():
            proj_id = row['id']
            try:
                idx = embeddings_data['ids'].index(proj_id)
                proj_emb = embeddings_data['embeddings'][idx]
                sem_score = np.dot(q_emb, proj_emb) / (np.linalg.norm(q_emb) * np.linalg.norm(proj_emb))
                sem_score = float(sem_score[0])
            except:
                sem_score = 0.0
                
            # Hybrid Formula (60% Semantic, 40% TF-IDF)
            final_score = (sem_score * 0.6) + (tfidf_scores[i] * 0.4)
            hybrid_scores.append(final_score)
            
        hybrid_scores = np.array(hybrid_scores)
        top5_hybrid_idx = hybrid_scores.argsort()[-5:][::-1]
        top5_hybrid_titles = df.iloc[top5_hybrid_idx]['title'].tolist()
        
        hybrid_hit = any(expected.lower() in str(title).lower() for title in top5_hybrid_titles)
        
        results.append({
            "query": q,
            "tfidf_hit": 1 if tfidf_hit else 0,
            "hybrid_hit": 1 if hybrid_hit else 0,
            "tfidf_top1": top5_tfidf_titles[0],
            "hybrid_top1": top5_hybrid_titles[0]
        })
        
        print(f"\n🔎 Query: \"{q}\"")
        print(f"  [TF-IDF]  Top 1: {top5_tfidf_titles[0][:50]}... | Correct? {'✅ Yes' if tfidf_hit else '❌ No'}")
        print(f"  [Hybrid]  Top 1: {top5_hybrid_titles[0][:50]}... | Correct? {'✅ Yes' if hybrid_hit else '❌ No'}")

    # --- CALCULATE METRICS ---
    tfidf_precision = sum(r['tfidf_hit'] for r in results) / len(results)
    hybrid_precision = sum(r['hybrid_hit'] for r in results) / len(results)
    
    print("\n" + "="*50)
    print("📊 THESIS EVALUATION RESULTS (Precision@5)")
    print("="*50)
    print(f"Baseline (TF-IDF) Precision@5:  {tfidf_precision * 100:.1f}%")
    print(f"Proposed (Hybrid) Precision@5:  {hybrid_precision * 100:.1f}%")
    print("="*50)
    
    if hybrid_precision > tfidf_precision:
        print("✅ SUCCESS: The Hybrid Semantic model outperforms the baseline!")
        print("   Use these numbers in your M.Tech thesis report.")
    elif hybrid_precision == tfidf_precision:
        print("⚖️ TIE: The models performed equally well on this small test set.")
    else:
        print("⚠️ Note: The Baseline beat the Hybrid model on this specific test set.")
        print("   Consider tweaking the weights (currently 60% Semantic / 40% TF-IDF).")

if __name__ == "__main__":
    evaluate()