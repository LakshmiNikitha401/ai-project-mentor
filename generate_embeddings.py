import psycopg2
import pandas as pd
from fastembed import TextEmbedding
import pickle
import time
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.environ.get("DATABASE_URL")

def generate():
    print("⏳ Connecting to database...")
    conn = psycopg2.connect(db_url)
    
    print("⏳ Fetching projects...")
    df = pd.read_sql("SELECT id, title, description, domain, skills FROM catalogue_projects", conn)
    conn.close()
    
    print(f"✅ Fetched {len(df)} projects.")
    
    df['skills'] = df['skills'].apply(lambda x: " ".join(x) if isinstance(x, list) else str(x))
    df['text_to_embed'] = df['title'].fillna('') + " " + \
                          df['description'].fillna('') + " " + \
                          df['domain'].fillna('') + " " + \
                          df['skills'].fillna('')
                          
    print("🧠 Loading FastEmbed model (BAAI/bge-small-en-v1.5)...")
    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    
    print("⚙️ Generating embeddings (this might take 1-2 minutes)...")
    start_time = time.time()
    
    # FastEmbed returns a generator, so we convert to list
    embeddings = list(model.embed(df['text_to_embed'].tolist()))
    
    with open('project_embeddings.pkl', 'wb') as f:
        pickle.dump({
            'ids': df['id'].tolist(),
            'embeddings': embeddings
        }, f)
        
    print(f"✅ Successfully generated and saved embeddings in {time.time() - start_time:.2f} seconds!")

if __name__ == "__main__":
    generate()
