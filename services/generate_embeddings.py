import psycopg2
import pandas as pd
from sentence_transformers import SentenceTransformer
import pickle
import time

# Your Supabase URL
db_url = "postgresql://postgres.kqmxnbeisjdkmwdipyfl:ProjectGuide.2026@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"

def generate():
    print("⏳ Connecting to database...")
    conn = psycopg2.connect(db_url)
    
    print("⏳ Fetching projects...")
    df = pd.read_sql("SELECT id, title, description, domain, skills FROM catalogue_projects", conn)
    conn.close()
    
    print(f"✅ Fetched {len(df)} projects.")
    
    # Combine text fields into one string for the AI to read
    df['text_to_embed'] = df['title'].fillna('') + " " + \
                          df['description'].fillna('') + " " + \
                          df['domain'].fillna('') + " " + \
                          df['skills'].fillna('')
                          
    print("🧠 Loading Sentence-BERT model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    print("⚙️ Generating embeddings (this might take 1-2 minutes)...")
    start_time = time.time()
    
    # Convert all text to vectors
    embeddings = model.encode(df['text_to_embed'].tolist(), show_progress_bar=True)
    
    # Save the embeddings and the project IDs to a file
    with open('project_embeddings.pkl', 'wb') as f:
        pickle.dump({
            'ids': df['id'].tolist(),
            'embeddings': embeddings
        }, f)
        
    print(f"✅ Successfully generated and saved embeddings in {time.time() - start_time:.2f} seconds!")

if __name__ == "__main__":
    generate()