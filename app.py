import io
import json
import re
import secrets
import hashlib
import smtplib
import concurrent.futures
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from supabase import create_client
except Exception:
    create_client = None

try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from pypdf import PdfReader
except Exception:
    try:
        from PyPDF2 import PdfReader
    except Exception:
        PdfReader = None

try:
    import docx  # python-docx
except Exception:
    docx = None

# ======================================================
# CONFIG + SECRETS
# ======================================================
st.set_page_config(page_title="AI Project Mentor", page_icon="🧠", layout="wide")

LOCAL_STORE_PATH = Path("ai_project_mentor_platform_store.json")
RESULTS_PER_PAGE = 8

def get_secret_value(*paths):
    for path in paths:
        try:
            value = st.secrets
            for key in path:
                value = value[key]
            if value:
                return str(value)
        except Exception:
            continue
    return ""

SUPABASE_URL = get_secret_value(("supabase", "URL"))
SUPABASE_KEY = get_secret_value(("supabase", "KEY"))
supabase = None
if create_client and SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        supabase = None

GEMINI_API_KEY = get_secret_value(
    ("gemini", "API_KEY"),
    ("GEMINI_API_KEY",),
    ("GOOGLE_API_KEY",),
)

SMTP_HOST = get_secret_value(("email", "SMTP_HOST"))
SMTP_PORT = int(get_secret_value(("email", "SMTP_PORT")) or 587)
SMTP_USER = get_secret_value(("email", "SMTP_USER"))
SMTP_PASSWORD = get_secret_value(("email", "SMTP_PASSWORD"))
FROM_EMAIL = get_secret_value(("email", "FROM_EMAIL")) or SMTP_USER
EMAIL_ENABLED = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD and FROM_EMAIL)

if genai and GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception:
        pass

# ======================================================
# DOMAIN DATA (Explore button)
# ======================================================
DOMAINS = {
    "Artificial Intelligence": {
        "emoji": "🧠",
        "meaning": "Build systems that can think, reason, assist, and make intelligent decisions.",
        "uses": ["Virtual assistants", "Smart automation", "AI agents", "Decision support"],
        "best_for": "Students interested in smart software systems and future-focused projects.",
        "examples": ["AI study mentor", "AI resume analyzer", "AI career assistant"],
    },
    "Machine Learning": {
        "emoji": "🧪",
        "meaning": "Teach systems to learn patterns from data and make predictions.",
        "uses": ["Prediction systems", "Recommendation engines", "Forecasting", "Fraud detection"],
        "best_for": "Students who enjoy working with datasets and model building.",
        "examples": ["Student performance predictor", "Fraud detection", "Sales forecasting"],
    },
    "Deep Learning": {
        "emoji": "🔮",
        "meaning": "Use multi-layer neural networks for advanced AI problems on text, image, and audio.",
        "uses": ["Medical imaging", "Speech systems", "Advanced NLP", "Deepfake detection"],
        "best_for": "Students wanting strong AI research-oriented projects.",
        "examples": ["Brain tumor detection", "Deepfake detector", "Speech emotion AI"],
    },
    "Natural Language Processing": {
        "emoji": "💬",
        "meaning": "Enable computers to understand, analyze, and generate human language.",
        "uses": ["Chatbots", "Summarizers", "Translation", "Sentiment analysis"],
        "best_for": "Students interested in language, communication, and AI assistants.",
        "examples": ["Research paper summarizer", "Domain chatbot", "Resume parser"],
    },
    "Computer Vision": {
        "emoji": "👁️",
        "meaning": "Make computers understand images and videos.",
        "uses": ["Detection systems", "Surveillance", "Healthcare imaging", "Recognition"],
        "best_for": "Students who like visual and real-time projects.",
        "examples": ["Helmet detection", "Face recognition", "Plant disease detector"],
    },
    "Data Science": {
        "emoji": "📊",
        "meaning": "Analyze and visualize data to discover insights, trends, and stories.",
        "uses": ["Dashboards", "Business intelligence", "Trend analysis", "Reporting"],
        "best_for": "Students who enjoy data analysis and visual storytelling.",
        "examples": ["Crime analytics dashboard", "Sales insights", "Student data analysis"],
    },
    "Recommendation Systems": {
        "emoji": "⭐",
        "meaning": "Suggest relevant items, content, or products based on user patterns.",
        "uses": ["Movie recommendations", "Product suggestions", "Course recommendations"],
        "best_for": "Students who like personalization and ranking problems.",
        "examples": ["Movie recommender", "Career course recommender", "Music suggester"],
    },
    "IoT": {
        "emoji": "🌐",
        "meaning": "Connect sensors and devices to collect and exchange data in real time.",
        "uses": ["Smart homes", "Health monitoring", "Smart agriculture", "Smart parking"],
        "best_for": "Students who enjoy hardware + software integration.",
        "examples": ["Smart irrigation", "Air quality monitor", "Smart parking system"],
    },
    "Cybersecurity": {
        "emoji": "🔐",
        "meaning": "Protect systems, networks, and data from attacks and misuse.",
        "uses": ["Threat detection", "Phishing detection", "Secure login systems"],
        "best_for": "Students interested in security and ethical hacking.",
        "examples": ["Phishing detector", "Malware classifier", "Threat analyzer"],
    },
    "Cloud Computing": {
        "emoji": "☁️",
        "meaning": "Deploy and manage scalable services on cloud platforms.",
        "uses": ["Deployment", "Serverless services", "Cloud automation", "Scaling"],
        "best_for": "Students who like deployment, DevOps, and scalable architecture.",
        "examples": ["Serverless ML API", "Cloud cost analyzer", "Auto-scaling demo"],
    },
    "Robotics": {
        "emoji": "🤖",
        "meaning": "Combine hardware and software to build intelligent machines.",
        "uses": ["Autonomous bots", "Industrial automation", "Drones"],
        "best_for": "Students who enjoy mechanics, sensors, and control logic.",
        "examples": ["Line follower bot", "Obstacle avoidance drone", "Warehouse robot sim"],
    },
    "Image Processing": {
        "emoji": "📷",
        "meaning": "Enhance, transform, and analyze images to extract useful information.",
        "uses": ["Filters and enhancement", "OCR", "Medical image analysis", "Compression"],
        "best_for": "Students who like working close to pixel-level algorithms.",
        "examples": ["Document scanner", "OCR system", "Medical image enhancer"],
    },
}

# Query normalization for the domain/combo input
ALIASES = {
    "ai": "artificial intelligence",
    "ml": "machine learning",
    "dl": "deep learning",
    "nlp": "natural language processing",
    "cv": "computer vision",
    "iot": "iot",
    "ip": "image processing",
    "ds": "data science",
    "recsys": "recommendation systems",
    "cyber": "cybersecurity",
    "cyber security": "cybersecurity",
    "cloud": "cloud computing",
}

# ======================================================
# SESSION STATE
# ======================================================
def init_state():
    defaults = {
        "user": None,
        "page": "home",
        "home_panel": "domain",
        "results": [],
        "db_results": [],
        "arxiv_results": [],
        "db_page": 1,
        "ai_page": 1,
        "arxiv_page": 1,
        "research_directions": [],
        "idea_chat": None,
        "idea_arxiv_query": "",
        "search_mode": "",
        "last_search": "",
        "searched": False,
        "upload_analysis": None,
        "upload_names": [],
        "active_project_id": None,
        "active_project": None,
        "local_bookmarks": [],
        "local_projects": [],
        "local_roadmaps": {},
        "local_chat": {},
        "local_reminders": {},
        "local_step_checks": {},
        "local_final_packs": {},
        "local_auth": {},
        "pending_idea": None,
        "idea_mode": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ======================================================
# CSS — slate + muted teal dark theme
# ======================================================
st.markdown("""
<style>
#MainMenu, footer, header {visibility: hidden;}

/* ============================================================
   Slate + muted teal — restrained professional dark theme.
   Background:  #0a0e14
   Surface:     #12171f
   Surface2:    #1a212b
   Border:      #232b38
   Accent:      #0f766e  (muted teal)
   Accent hover:#115e59
   Text:        #e6edf3
   Muted:       #8b98a9
   ============================================================ */
.stApp {
    background:
        radial-gradient(ellipse 80% 50% at 50% -10%, rgba(15,118,110,0.06), transparent 60%),
        #0a0e14;
    color: #e6edf3;
}
html {font-size: 106%;}

.block-container {
    max-width: 1120px;
    margin: 0 auto;
    padding-top: 2rem;
    padding-left: 2rem;
    padding-right: 2rem;
}

/* Home page: a bit wider than the default, but still leaves breathing room
   on both sides so it reads like a real product page, not a stretched app. */
.home-scope {height: 0;}
.block-container:has(.home-scope) {
    max-width: 1440px !important;
    padding-left: 3rem;
    padding-right: 3rem;
}

.block-container:has(.login-scope) {
    max-width: 420px !important;
    padding-top: 10vh !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
}
.login-scope {height: 0;}

/* ============================================================
   Topbar
   ============================================================ */
.topbar-brand {display: flex; align-items: center; gap: 0.65rem; min-height: 44px;}
.topbar-logo {
    width: 32px; height: 32px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    background: #0f766e;
    color: #e6edf3; font-weight: 900; font-size: 0.85rem;
    letter-spacing: -0.03em;
}
.topbar-name {color: #e6edf3; font-weight: 700; font-size: 0.98rem; letter-spacing: -0.01em; line-height: 1.2;}
.topbar-user {color: #8b98a9; font-size: 0.72rem; line-height: 1.2; margin-top: 1px;}

.stApp [data-testid="stHorizontalBlock"]:has(.topbar-brand) {align-items: center !important;}
.stApp [data-testid="stHorizontalBlock"]:has(.topbar-brand) [data-testid="stColumn"]:not(:has(.topbar-brand)) [data-testid="stVerticalBlock"] {align-items: flex-end;}
.stApp [data-testid="stHorizontalBlock"]:has(.topbar-brand) .stButton {margin-bottom: 0;}
.stApp [data-testid="stHorizontalBlock"]:has(.topbar-brand) .stButton > button {
    width: 40px; min-width: 40px; height: 40px; padding: 0;
    display: inline-flex; align-items: center; justify-content: center;
    background: #12171f; color: #b6c0cc !important;
    border: 1px solid #232b38; border-radius: 9px; line-height: 1;
    box-shadow: none;
}
.stApp [data-testid="stHorizontalBlock"]:has(.topbar-brand) .stButton > button:hover {
    background: #1a212b; border-color: #2f3a4a; color: #e6edf3 !important;
}
.stApp [data-testid="stHorizontalBlock"]:has(.topbar-brand) [data-testid="stColumn"]:nth-child(2) .stButton > button,
.stApp [data-testid="stHorizontalBlock"]:has(.topbar-brand) [data-testid="stColumn"]:nth-child(2) .stButton > button p {
    font-size: 17px !important; line-height: 1; margin: 0;
}
.stApp [data-testid="stHorizontalBlock"]:has(.topbar-brand) [data-testid="stColumn"]:nth-child(3) .stButton > button p {font-size: 0; margin: 0;}
.stApp [data-testid="stHorizontalBlock"]:has(.topbar-brand) [data-testid="stColumn"]:nth-child(3) .stButton > button::before {
    content: ""; display: block; width: 14px; height: 2px;
    background: #b6c0cc;
    box-shadow: 0 -5px 0 #b6c0cc, 0 5px 0 #b6c0cc;
    border-radius: 1px;
}

/* Tighten the topbar action group: kill extra column padding so the two buttons
   sit in a small right-aligned cluster instead of drifting to the far edge. */
.stApp [data-testid="stHorizontalBlock"]:has(.topbar-brand) > [data-testid="stColumn"]:last-child [data-testid="stHorizontalBlock"] {
    justify-content: flex-end;
    gap: 8px !important;
}
.stApp [data-testid="stHorizontalBlock"]:has(.topbar-brand) > [data-testid="stColumn"]:last-child [data-testid="stColumn"] {
    width: auto !important;
    flex: 0 0 auto !important;
    min-width: 0 !important;
}
.stApp [data-testid="stHorizontalBlock"]:has(.topbar-brand) > [data-testid="stColumn"]:last-child [data-testid="stVerticalBlock"] {
    align-items: flex-end;
    gap: 0 !important;
}

.topbar-divider {
    border-top: 1px solid #232b38;
    margin: 0.75rem 0 1.75rem;
}

/* ============================================================
   Menu drawer
   ============================================================ */
[data-testid="stDialog"] div[role="dialog"] {
    position: fixed !important; top: 0 !important; right: 0 !important; left: auto !important;
    height: 100vh !important; max-height: 100vh !important;
    width: 300px !important; min-width: 300px !important; max-width: 86vw !important;
    border-radius: 0 !important; margin: 0 !important; transform: none !important;
    background: #0f141c !important; color: #e6edf3;
    border-left: 1px solid #232b38;
    box-shadow: -20px 0 50px rgba(0,0,0,0.5);
    animation: drawer-in 0.18s ease;
}
@keyframes drawer-in {from {transform: translateX(100%);} to {transform: translateX(0);}}
[data-testid="stDialog"] h3 {color: #e6edf3 !important;}
[data-testid="stDialog"] [data-testid="stCaptionContainer"] p {color: #8b98a9 !important;}
[data-testid="stDialog"] [data-testid="stCloseButton"] {color: #8b98a9 !important;}
[data-testid="stDialog"] .stButton > button {
    justify-content: flex-start; text-align: left; font-size: 0.9rem;
    background: transparent; border: 1px solid #232b38; color: #d3dae3 !important;
}
[data-testid="stDialog"] .stButton > button:hover {background: #1a212b; border-color: #2f3a4a;}

/* ============================================================
   Typography blocks
   ============================================================ */
.top-label {
    text-align: center; color: #8b98a9; font-size: 0.72rem; font-weight: 700;
    letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 1.25rem;
}
.hero-title {
    text-align: center; font-size: 2.1rem; font-weight: 800; color: #e6edf3;
    letter-spacing: -0.035em; margin-bottom: 0.7rem; line-height: 1.18;
}
.hero-sub {
    text-align: center; color: #8b98a9; font-size: 0.98rem; line-height: 1.6;
    margin-bottom: 1.75rem; max-width: 620px; margin-left: auto; margin-right: auto;
}
.form-title {color: #e6edf3; font-size: 1.2rem; font-weight: 700; margin-bottom: 0.3rem;}
.form-sub {color: #8b98a9; margin-bottom: 1.2rem; font-size: 0.9rem;}

/* ============================================================
   Search hero on home
   ============================================================ */
.search-hero {margin-bottom: 0.5rem;}
.search-hero .stTextInput input {
    height: 3rem !important; font-size: 1rem !important;
    background: #12171f !important;
    border: 1px solid #232b38 !important;
    border-radius: 10px !important;
}
.search-hero .stButton > button {
    height: 3rem; padding: 0 1.5rem; white-space: nowrap;
    background: #0f766e !important; color: #e6edf3 !important;
    font-weight: 700; font-size: 0.95rem;
    border: 1px solid #115e59 !important; border-radius: 10px;
    box-shadow: none;
}
.search-hero .stButton > button:hover {background: #115e59 !important; color: #e6edf3 !important; border-color: #0f766e !important;}

.quick-actions {display: flex; align-items: center; justify-content: center; margin-top: 0.75rem;}
.quick-actions .stButton > button {
    background: #12171f; border: 1px solid #232b38; border-radius: 10px;
    padding: 0.7rem 0.5rem; font-size: 0.92rem; color: #d3dae3 !important;
    font-weight: 600;
}
.quick-actions .stButton > button:hover {background: #1a212b; border-color: #2f3a4a;}
.quick-actions .stButton > button[kind="primary"],
.quick-actions .stButton > button[data-testid="stBaseButton-primary"] {
    background: #0f766e !important; color: #e6edf3 !important;
    border: 1px solid #115e59 !important; box-shadow: none !important;
}

/* ============================================================
   Inputs & buttons
   ============================================================ */
.stTextInput input, .stTextArea textarea {
    background-color: #12171f !important;
    border: 1px solid #232b38 !important;
    color: #e6edf3 !important;
    border-radius: 10px !important;
    font-size: 0.95rem;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border: 1px solid #0f766e !important;
    box-shadow: 0 0 0 3px rgba(15,118,110,0.30) !important;
}
.stTextInput input::placeholder, .stTextArea textarea::placeholder {color: #5a6776 !important;}

.stButton > button {
    width: 100%; background: #1a212b; color: #e6edf3 !important;
    border: 1px solid #232b38; border-radius: 10px;
    padding: 0.62rem 0.9rem; font-weight: 600; transition: 0.15s ease;
    box-shadow: none;
}
.stButton > button:hover {
    background: #232b38; color: #ffffff !important; border-color: #2f3a4a;
}
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {
    background: #0f766e !important;
    color: #e6edf3 !important;
    border: 1px solid #115e59 !important;
    font-weight: 700 !important;
    box-shadow: none !important;
}
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="stBaseButton-primary"]:hover {
    background: #115e59 !important; border-color: #0f766e !important; color: #ffffff !important;
}

/* ============================================================
   Section titles
   ============================================================ */
.workspace-title {color: #e6edf3; font-size: 1.75rem; font-weight: 800; margin-bottom: 0.35rem; letter-spacing: -0.02em;}
.workspace-sub {color: #8b98a9; line-height: 1.6; margin-bottom: 1.5rem; font-size: 0.96rem;}
.user-pill {color: #8b98a9; font-size: 0.85rem; margin-bottom: 1rem;}

/* ============================================================
   Domain cards
   ============================================================ */
.domain-card {
    background: #12171f;
    border: 1px solid #232b38;
    border-radius: 12px; padding: 1.2rem; min-height: 420px; margin-bottom: 0.8rem;
    display: flex; flex-direction: column;
    transition: 0.15s ease;
}
.domain-card:hover {border-color: #2f3a4a; background: #141a23;}
.domain-emoji {font-size: 1.4rem; line-height: 1; margin-right: 0.5rem; vertical-align: -0.15rem;}
.domain-title {color: #e6edf3; font-size: 1.1rem; font-weight: 700; margin-bottom: 0.85rem;}
.domain-section {color: #a4b0be; font-size: 0.88rem; line-height: 1.55; margin-bottom: 0.6rem;}
.domain-section b {color: #d3dae3; font-weight: 600;}
.domain-tag {
    display: inline-block; background: #1a212b; color: #a4b0be;
    border: 1px solid #232b38;
    border-radius: 6px; padding: 0.22rem 0.55rem; font-size: 0.76rem; margin: 0.1rem;
}
.stApp [data-testid="stColumn"]:has(.domain-card) > div {height: 100%; display: flex; flex-direction: column;}
.stApp [data-testid="stColumn"]:has(.domain-card) [data-testid="stElementContainer"]:has(.domain-card) {flex: 1; display: flex; flex-direction: column;}
.stApp [data-testid="stColumn"]:has(.domain-card) .domain-card {flex: 1;}

/* ============================================================
   Badges
   ============================================================ */
.difficulty-badge {
    display: inline-block; padding: 0.16rem 0.55rem; border-radius: 5px;
    font-size: 0.72rem; font-weight: 600; margin-right: 0.35rem;
}
.beginner {background: rgba(52,211,153,0.10); color: #34d399; border: 1px solid rgba(52,211,153,0.25);}
.intermediate {background: rgba(251,191,36,0.10); color: #fbbf24; border: 1px solid rgba(251,191,36,0.25);}
.advanced {background: rgba(248,113,113,0.10); color: #f87171; border: 1px solid rgba(248,113,113,0.25);}
.domain-badge {
    display: inline-block; padding: 0.16rem 0.55rem; border-radius: 5px; font-size: 0.72rem;
    font-weight: 600; color: #a4b0be; background: #1a212b;
    border: 1px solid #232b38; margin-right: 0.35rem;
}
.time-badge {
    display: inline-block; padding: 0.16rem 0.55rem; border-radius: 5px; font-size: 0.72rem;
    font-weight: 600; color: #a4b0be; background: #1a212b;
    border: 1px solid #232b38; margin-right: 0.35rem;
}
.source-badge {
    display: inline-block; padding: 0.16rem 0.55rem; border-radius: 5px; font-size: 0.72rem;
    font-weight: 600; color: #8b98a9; background: #12171f;
    border: 1px solid #232b38;
}

/* ============================================================
   Info items, timeline, reminders
   ============================================================ */
.analysis-row {
    background: #12171f; border: 1px solid #232b38;
    border-radius: 12px; padding: 1rem 1.1rem; margin-bottom: 1rem;
}
.analysis-row-title {color: #e6edf3; font-size: 1.05rem; font-weight: 700; margin-bottom: 0.2rem;}
.analysis-row-sub {color: #8b98a9; font-size: 0.84rem; margin-bottom: 0.7rem;}

.info-item {
    background: #0f141c;
    border: 1px solid #1d2430;
    border-left: 2px solid #0f766e;
    border-radius: 8px;
    padding: 0.55rem 0.75rem;
    margin-bottom: 0.5rem;
}
.info-item.green {border-left-color: #34d399;}
.info-item.purple {border-left-color: #a78bfa;}
.info-item-title {color: #e6edf3; font-weight: 600; font-size: 0.86rem; margin-bottom: 0.15rem; line-height: 1.4;}
.info-item-detail {color: #a4b0be; font-size: 0.8rem; line-height: 1.5;}

.timeline-item {display: flex; gap: 0.85rem; padding: 0.35rem 0;}
.timeline-dot {
    min-width: 28px; height: 28px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.8rem; font-weight: 700; margin-top: 0.15rem;
    border: 1px solid #232b38; background: #12171f; color: #8b98a9;
}
.dot-done {background: rgba(52,211,153,0.12); color: #34d399; border-color: rgba(52,211,153,0.3);}
.dot-current {background: rgba(15,118,110,0.20); color: #5eead4; border-color: rgba(15,118,110,0.5);}
.dot-locked {background: #12171f; color: #5a6776;}
.dot-idea {background: rgba(167,139,250,0.12); color: #a78bfa; border-color: rgba(167,139,250,0.35);}

.reminder-box {
    background: #12171f; border: 1px solid #232b38;
    border-left: 2px solid #0f766e; border-radius: 8px;
    padding: 0.65rem 0.85rem; margin-bottom: 0.55rem;
}
.reminder-box.done {border-left-color: #34d399;}
.reminder-box.info {border-left-color: #fbbf24;}
.reminder-box.idea {border-left-color: #a78bfa;}
.reminder-title {color: #e6edf3; font-weight: 600; font-size: 0.88rem; margin-bottom: 0.15rem;}
.reminder-meta {color: #8b98a9; font-size: 0.78rem; line-height: 1.5;}

.locked-step {
    opacity: 0.6; border: 1px dashed #232b38;
    border-radius: 8px; padding: 0.7rem; margin-bottom: 0.5rem;
}

div[data-testid="stAlert"] {
    border-radius: 10px;
    background: #12171f;
    border: 1px solid #232b38;
}
div[data-testid="stExpander"] {
    border-radius: 10px;
    border: 1px solid #232b38 !important;
    background: #12171f;
}
[data-testid="stExpander"] summary {font-size: 0.88rem;}
div[data-testid="stVerticalBlockBorderWrapper"] {border-color: #232b38 !important;}
hr {border: none; border-top: 1px solid #232b38; margin: 1.5rem 0;}

.block-container:has(.login-scope) [role="radiogroup"] {
    gap: 0.5rem;
    margin-bottom: 0.5rem;
}
</style>
""", unsafe_allow_html=True)

# Login page keyboard flow: Enter jumps Email -> Password, and Enter on the
# last field clicks the primary button (Login / Send code / Verify).
components.html(
    """
    <script>
    (function () {
        if (window.__tbEnterWired) return;
        window.__tbEnterWired = true;
        const doc = window.parent.document;
        doc.addEventListener('keydown', function (e) {
            if (e.key !== 'Enter') return;
            if (!doc.querySelector('.login-scope')) return;
            const t = e.target;
            if (!t || t.tagName !== 'INPUT') return;
            const okTypes = ['text', 'email', 'password', 'tel'];
            if (okTypes.indexOf(t.type) === -1) return;
            const inputs = Array.from(doc.querySelectorAll('.block-container input')).filter(function (i) {
                return okTypes.indexOf(i.type) !== -1 && i.offsetParent !== null;
            });
            const idx = inputs.indexOf(t);
            if (idx === -1) return;
            e.preventDefault();
            if (idx < inputs.length - 1) {
                inputs[idx + 1].focus();
            } else {
                const btn = doc.querySelector('.block-container button[kind="primary"]');
                if (btn) btn.click();
            }
        }, true);
    })();
    </script>
    """,
    height=0,
)

# ======================================================
# SMALL HELPERS
# ======================================================
def clean_text(text):
    return str(text).strip().lower()

def current_user_email():
    return st.session_state.get("user")

def normalize_difficulty(value):
    v = str(value).strip().lower()
    if "beginner" in v or "easy" in v or "simple" in v:
        return "Beginner"
    if "advanced" in v or "hard" in v or "research" in v:
        return "Advanced"
    return "Intermediate"

def difficulty_badge_html(difficulty):
    d = str(difficulty).strip().lower()
    if d == "beginner":
        return '<span class="difficulty-badge beginner">Beginner</span>'
    if d == "advanced":
        return '<span class="difficulty-badge advanced">Advanced</span>'
    return '<span class="difficulty-badge intermediate">Intermediate</span>'

def estimate_duration(difficulty):
    d = normalize_difficulty(difficulty)
    if d == "Beginner":
        return "2 - 3 weeks"
    if d == "Advanced":
        return "8 - 12 weeks"
    return "4 - 6 weeks"

def extract_json(text):
    """Best-effort JSON extraction from an LLM response (dict or list)."""
    if not text:
        return None
    text = re.sub(r"```(json)?", "", str(text)).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    for pattern in [r"\{.*\}", r"\[.*\]"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                continue
    return None

def get_gemini_model():
    if not genai or not GEMINI_API_KEY:
        return None
    cached_name = st.session_state.get("_gemini_model_name")
    if cached_name:
        try:
            return genai.GenerativeModel(cached_name)
        except Exception:
            pass
    preferred = get_secret_value(("gemini", "MODEL"), ("GEMINI_MODEL",))
    candidates = [preferred] if preferred else []
    try:
        for m in genai.list_models():
            methods = getattr(m, "supported_generation_methods", []) or []
            name = getattr(m, "name", "")
            if "generateContent" in methods and name:
                candidates.append(name.replace("models/", ""))
    except Exception:
        pass
    candidates.extend([
        "gemini-2.0-flash", "gemini-1.5-flash-latest", "gemini-1.5-pro-latest", "gemini-pro",
    ])
    seen = set()
    for name in candidates:
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            model = genai.GenerativeModel(name)
            st.session_state["_gemini_model_name"] = name
            return model
        except Exception:
            continue
    return None

def ai_generate(prompt, max_tokens=500, model=None):
    """Call Gemini and return text, or None when unavailable/failed."""
    if model is None:
        model = get_gemini_model()
    if model is None:
        return None
    try:
        response = model.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_tokens, "temperature": 0.5},
        )
        text = getattr(response, "text", "")
        return text.strip() if text else None
    except Exception:
        return None

# ======================================================
# LOCAL STORE (persistence fallback)
# ======================================================
def _safe_key(value):
    return str(value or "guest").replace("@", "_at_").replace(".", "_")

def _load_store():
    try:
        if LOCAL_STORE_PATH.exists():
            return json.loads(LOCAL_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _write_store(store):
    try:
        LOCAL_STORE_PATH.write_text(json.dumps(store, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass

def save_local_state():
    email = current_user_email()
    if not email:
        return
    store = _load_store()
    store[_safe_key(email)] = {
        "bookmarks": st.session_state.get("local_bookmarks", []),
        "projects": st.session_state.get("local_projects", []),
        "roadmaps": st.session_state.get("local_roadmaps", {}),
        "chat": st.session_state.get("local_chat", {}),
        "reminders": st.session_state.get("local_reminders", {}),
        "step_checks": st.session_state.get("local_step_checks", {}),
        "final_packs": st.session_state.get("local_final_packs", {}),
        "step_proofs": st.session_state.get("local_step_proofs", {}),
        "reminder_plan": st.session_state.get("local_reminder_plan", {}),
    }
    _write_store(store)

def load_local_state_for_user(email):
    data = _load_store().get(_safe_key(email), {})
    st.session_state["local_bookmarks"] = data.get("bookmarks", [])
    st.session_state["local_projects"] = data.get("projects", [])
    st.session_state["local_roadmaps"] = data.get("roadmaps", {})
    st.session_state["local_chat"] = data.get("chat", {})
    st.session_state["local_reminders"] = data.get("reminders", {})
    st.session_state["local_step_checks"] = data.get("step_checks", {})
    st.session_state["local_final_packs"] = data.get("final_packs", {})
    st.session_state["local_step_proofs"] = data.get("step_proofs", {})
    st.session_state["local_reminder_plan"] = data.get("reminder_plan", {})

def upsert_local_project(project_row):
    projects = st.session_state.setdefault("local_projects", [])
    pid = str(project_row.get("id"))
    for i, old in enumerate(projects):
        if str(old.get("id")) == pid:
            projects[i] = {**old, **project_row}
            save_local_state()
            return
    projects.append(project_row)
    save_local_state()

def merge_unique_by_id(primary, fallback):
    merged, seen = [], set()
    for row in (primary or []) + (fallback or []):
        row_id = str(row.get("id", row.get("title", "")))
        if row_id and row_id not in seen:
            seen.add(row_id)
            merged.append(row)
    return merged

# ======================================================
# SUPABASE HELPERS (best-effort, local fallback)
# ======================================================
def db_insert(table, payload):
    if not supabase:
        return None
    try:
        return supabase.table(table).insert(payload).execute().data
    except Exception:
        return None

def db_select(table, filters=None, order_col=None, desc=True):
    if not supabase:
        return []
    try:
        q = supabase.table(table).select("*")
        if filters:
            for col, val in filters.items():
                q = q.eq(col, val)
        if order_col:
            q = q.order(order_col, desc=desc)
        return q.execute().data or []
    except Exception:
        return []

def db_update(table, row_id, payload):
    if not supabase:
        return None
    try:
        return supabase.table(table).update(payload).eq("id", row_id).execute().data
    except Exception:
        return None

# ======================================================
# AUTH (Supabase first, local fallback)
# ======================================================
def _hash_password(password):
    return hashlib.sha256(str(password).encode("utf-8")).hexdigest()

def local_signup(full_name, email, password):
    store = _load_store()
    auth = store.setdefault("_local_auth", {})
    key = _safe_key(email)
    if key in auth:
        return "An account with this email already exists locally."
    auth[key] = {"full_name": full_name, "password": _hash_password(password)}
    store["_local_auth"] = auth
    _write_store(store)
    return None

def local_login(email, password):
    store = _load_store()
    auth = store.get("_local_auth", {})
    entry = auth.get(_safe_key(email))
    if entry and entry.get("password") == _hash_password(password):
        return None
    return "Invalid email or password."

def signup_user(full_name, email, password):
    """Try Supabase first; fall back to local store if unavailable."""
    if supabase:
        try:
            supabase.auth.sign_up({
                "email": email, "password": password,
                "options": {"data": {"full_name": full_name}},
            })
            return None
        except Exception as e:
            err = str(e)
            if "already registered" in err.lower() or "already exists" in err.lower():
                return err
    return local_signup(full_name, email, password)

def login_user(email, password):
    """Try Supabase first; fall back to local auth if unavailable/failed."""
    if supabase:
        try:
            supabase.auth.sign_in_with_password({"email": email, "password": password})
            return None
        except Exception:
            pass
    return local_login(email, password)

# ======================================================
# EMAIL NOTIFICATIONS
# ======================================================
def send_email_notification(to_email, subject, body):
    if not EMAIL_ENABLED or not to_email:
        st.session_state["last_email_status"] = (
            "Email not sent: SMTP is not configured in .streamlit/secrets.toml."
        )
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = FROM_EMAIL
        msg["To"] = to_email
        msg.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        st.session_state["last_email_status"] = f"Email sent to {to_email}"
        return True
    except Exception as e:
        st.session_state["last_email_status"] = f"Email failed: {e}"
        return False

# ======================================================
# REMINDERS (in-app + best-effort email scheduling)
# ======================================================
def make_reminder(project_id, title, message, due_date=None, status="pending", kind="task"):
    if due_date is None:
        due_date = datetime.utcnow().date().isoformat()
    elif hasattr(due_date, "isoformat"):
        due_date = due_date.isoformat()
    return {
        "project_id": project_id if not str(project_id).startswith("local_") else None,
        "user_email": current_user_email(),
        "title": title,
        "message": message,
        "due_date": str(due_date),
        "status": status,
        "kind": kind,
    }

def append_project_reminder(project_id, reminder):
    pid = str(project_id)
    st.session_state.setdefault("local_reminders", {}).setdefault(pid, []).append(reminder)
    save_local_state()
    if not pid.startswith("local_"):
        db_insert("project_reminders", reminder)

def format_due_date(date_value):
    if not date_value:
        return "No date set"
    try:
        date_obj = datetime.strptime(str(date_value)[:10], "%Y-%m-%d")
        return date_obj.strftime("%d %b %Y")
    except Exception:
        return str(date_value)

def create_project_reminders(project_id, project, steps):
    start_date = datetime.utcnow().date()
    title = project.get("title", "your project")

    append_project_reminder(project_id, make_reminder(
        project_id,
        "Project started",
        f"You started '{title}'. Complete roadmap checklists step-by-step; your mentor chat will guide you.",
        start_date,
        "info",
    ))

    gap_days = 3 if normalize_difficulty(project.get("difficulty", "")) != "Advanced" else 5
    plan_lines = []
    plan_map = st.session_state.setdefault("local_reminder_plan", {}).setdefault(str(project_id), {})
    for idx, step in enumerate(steps, start=1):
        due = start_date + timedelta(days=idx * gap_days)
        plan_map[str(step.get("step_no", idx))] = due.isoformat()
        reminder = make_reminder(
            project_id,
            f"Step {step.get('step_no', idx)} target: {step.get('title', 'Project task')}",
            f"Aim to finish this stage by the target date: {step.get('description', '')}",
            due,
            "pending",
        )
        append_project_reminder(project_id, reminder)
        plan_lines.append(f"Step {step.get('step_no', idx)} — {step.get('title', '')}: target {format_due_date(due)}")
    save_local_state()
    if EMAIL_ENABLED and plan_lines:
        send_email_notification(
            current_user_email(),
            f"Your project plan: {title}",
            f"Project: {title}\n\nHere is your step-by-step target plan:\n\n"
            + "\n".join(plan_lines)
            + "\n\nIn-app reminders will track each step as you complete it.\n\n— AI Project Mentor",
        )

# ======================================================
# LOCAL DATASET SEARCH (optional curated source)
# ======================================================
@st.cache_data
def load_dataset():
    paths = [
        Path("dataset.xlsx"),
        Path("dataset.csv"),
        Path("Project recommender/dataset/cleaned_dataset.xlsx"),
        Path("Project recommender/dataset/Dataset.xlsx"),
    ]
    file_path = next((p for p in paths if p.exists()), None)
    if not file_path:
        return pd.DataFrame()
    try:
        df = pd.read_excel(file_path) if file_path.suffix == ".xlsx" else pd.read_csv(file_path)
        df.columns = [str(c).strip().lower() for c in df.columns]
        if "domain_name" in df.columns and "domain" in df.columns:
            df = df.drop(columns=["domain"])
        df = df.rename(columns={"domain_name": "domain", "clean_text": "description"})
        if "title" not in df.columns:
            return pd.DataFrame()
        for col, default in {"description": "", "domain": "General", "difficulty": "Intermediate", "skills": ""}.items():
            if col not in df.columns:
                df[col] = default
        for col in ["title", "description", "domain", "difficulty", "skills"]:
            df[col] = df[col].fillna("").astype(str)
        df = df[df["title"].str.strip() != ""].drop_duplicates(subset=["title"])
        df["combined"] = (df["title"] + " " + df["description"] + " " + df["domain"] + " " + df["skills"]).str.lower()
        return df.reset_index(drop=True)
    except Exception:
        return pd.DataFrame()

@st.cache_resource
def get_dataset_search_index():
    """Build the TF-IDF index ONCE instead of refitting on every search (big speedup)."""
    df = load_dataset()
    if df.empty:
        return None, None, None
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(df["combined"])
    return df, vectorizer, matrix

def search_local_dataset(query, limit=12):
    df, vectorizer, matrix = get_dataset_search_index()
    if df is None:
        return []
    words = [w for w in re.findall(r"[a-zA-Z0-9]+", clean_text(query)) if len(w) > 2]
    words = [w for w in words if w not in {
        "want", "build", "make", "create", "something", "with", "and", "for",
        "using", "based", "project", "idea", "system", "app", "application", "the",
    }]
    if not words:
        return []
    try:
        q_vec = vectorizer.transform([clean_text(query)])
        scores = cosine_similarity(q_vec, matrix).flatten()
        df = df.copy()
        df["score"] = scores
        df["overlap"] = df["combined"].apply(lambda t: sum(1 for w in words if w in t))
        df = df[(df["score"] >= 0.06) | (df["overlap"] >= 1)]
        df = df.sort_values(["overlap", "score"], ascending=False).head(limit)
        results = []
        for _, row in df.iterrows():
            difficulty = normalize_difficulty(row.get("difficulty", "Intermediate"))
            results.append({
                "title": str(row["title"]),
                "description": str(row["description"]) or f"{row['title']} is a project in {row['domain']}.",
                "domain": str(row["domain"]),
                "difficulty": difficulty,
                "skills": str(row["skills"]) or "Python, Problem Solving",
                "duration": estimate_duration(difficulty),
                "source": "Curated Dataset",
                "why": "Matched from the curated project dataset using TF-IDF relevance.",
            })
        return results
    except Exception:
        return []

# ======================================================
# AI PROJECT PACKAGE (idea/domain -> projects + research expansion)
# ======================================================
def fallback_project_package(query):
    pretty = query.strip().title() if query.strip() else "Selected Domain"
    base = [
        {"title": f"Beginner {pretty} Mini Project",
         "description": f"A simple, feasible project introducing the core of {query} with clear input, process, and output.",
         "research_expansion": "Add a small comparison of 2 approaches and write up when each works better."},
        {"title": f"Applied {pretty} Project with Dashboard",
         "description": f"A practical project applying {query} to a real use case, presenting results through a clean UI or dashboard.",
         "research_expansion": "Add user feedback collection and analyze how real users benefit from the system."},
        {"title": f"Advanced {pretty} Research Prototype",
         "description": f"A stronger project with literature survey, baseline comparison, evaluation, and an improved model/architecture for {query}.",
         "research_expansion": "Survey 5 recent papers, reproduce one baseline, and propose a measurable improvement."},
    ]
    projects = []
    levels = ["Beginner", "Beginner", "Beginner", "Intermediate", "Intermediate", "Intermediate", "Advanced", "Advanced", "Advanced"]
    variants = ["with Real Dataset", "using Python + Open Tools", "with Evaluation Report",
                "with Web Interface", "with Automation Angle", "with Analytics Focus",
                "with Novel Twist", "with Comparative Study", "with Deployment Demo"]
    for i, level in enumerate(levels):
        b = base[min(i // 3, 2)]
        projects.append({
            "title": f"{b['title']} {variants[i]}",
            "description": b["description"],
            "domain": pretty,
            "difficulty": level,
            "skills": "Python, Data Handling, Problem Analysis" if level == "Beginner" else ("Python, Modeling, Streamlit" if level == "Intermediate" else "Research Reading, Modeling, Evaluation"),
            "duration": estimate_duration(level),
            "why": "Fallback suggestion generated offline — connect Gemini for tailored ideas.",
            "research_expansion": b["research_expansion"],
            "source": "Mentor (offline)",
        })
    directions = [
        {"title": f"Survey of recent work in {pretty}", "detail": "Collect 8-10 recent papers and summarize techniques, datasets, and gaps."},
        {"title": f"{pretty} + another domain combo", "detail": "Combine with healthcare, education, or finance for a fresh problem space."},
        {"title": f"Efficiency angle for {pretty}", "detail": "Study speed/memory tradeoffs of existing methods and propose a lighter version."},
        {"title": f"Fairness/ethics angle for {pretty}", "detail": "Analyze bias, privacy, or explainability issues and add safeguards."},
        {"title": f"Deployment-focused study for {pretty}", "detail": "Package the working model as an API/app and measure real-world performance."},
    ]
    return {"projects": projects, "research_directions": directions}

def fetch_gemini_projects(query, model=None, limit=9, context=""):
    """Gemini: doable projects (3 per difficulty) + research directions in ONE call."""
    if model is None:
        model = get_gemini_model()
    ai_projects, directions = [], []
    if model is not None:
        context_block = (
            f"\nThe student first shared this idea, then answered brainstorming questions about it:\n{context}\n"
            "Tailor every idea to these answers (target users, data, scope, skills).\n"
            if context else ""
        )
        prompt = f"""
You are an academic AI project mentor for engineering/MTech students.
Student input (domain, combination, or raw idea): "{query}"
{context_block}
Task:
1. Generate 9 doable project ideas from this input: 3 Beginner, 3 Intermediate, 3 Advanced.
2. Generate 5 research expansion directions (how a student can extend this area toward research/publication-level work).

Rules:
- Ideas must be distinct, specific, and directly relevant to the input.
- If the input combines domains (e.g., "ai + ml" or "cv + healthcare"), ideas should genuinely combine them.
- Each project needs: title, description (2-3 lines), domain, difficulty (Beginner/Intermediate/Advanced),
  skills, duration (e.g. "4 - 6 weeks"), why (why it is worth doing), research_expansion (how it can be extended further/research angle).
- Each research direction needs: title, detail.

Return ONLY valid JSON in exactly this shape:
{{
  "projects": [{{"title": "...", "description": "...", "domain": "...", "difficulty": "...", "skills": "...", "duration": "...", "why": "...", "research_expansion": "..."}}],
  "research_directions": [{{"title": "...", "detail": "..."}}]
}}
"""
        data = extract_json(ai_generate(prompt, max_tokens=4096, model=model))
        if isinstance(data, dict):
            for item in (data.get("projects") or [])[:limit]:
                if not isinstance(item, dict) or not item.get("title"):
                    continue
                difficulty = normalize_difficulty(item.get("difficulty", "Intermediate"))
                ai_projects.append({
                    "title": str(item.get("title", "Project Idea")),
                    "description": str(item.get("description", "")),
                    "domain": str(item.get("domain", query.title())),
                    "difficulty": difficulty,
                    "skills": str(item.get("skills", "Python, Problem Solving")),
                    "duration": str(item.get("duration") or estimate_duration(difficulty)),
                    "why": str(item.get("why", "Generated based on your input.")),
                    "research_expansion": str(item.get("research_expansion", "")),
                    "source": "AI Mentor",
                })
            for item in (data.get("research_directions") or [])[:8]:
                if isinstance(item, dict) and item.get("title"):
                    directions.append({"title": str(item["title"]), "detail": str(item.get("detail", ""))})

    return ai_projects, directions

def generate_project_package(query):
    """Search all three sources; the slow ones (Gemini + arXiv) run in parallel."""
    package = {
        "db_projects": [],
        "ai_projects": [],
        "arxiv_projects": [],
        "research_directions": [],
    }

    package["db_projects"] = search_local_dataset(query, limit=12)

    model = get_gemini_model()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        future_ai = pool.submit(fetch_gemini_projects, query, model)
        future_arxiv = pool.submit(fetch_arxiv_research_ideas, query, 12)
        try:
            ai_projects, directions = future_ai.result() or ([], [])
        except Exception:
            ai_projects, directions = [], []
        try:
            package["arxiv_projects"] = future_arxiv.result() or []
        except Exception:
            package["arxiv_projects"] = []

    ai_projects = ai_projects or []
    directions = directions or []
    fallback = fallback_project_package(query)
    if not ai_projects:
        ai_projects = fallback["projects"]
    if not directions:
        directions = fallback["research_directions"]

    package["ai_projects"] = ai_projects
    package["research_directions"] = directions
    return package

FRIENDLY_FALLBACK_TURNS = [
    ("Okay, noted 👍", "Who do you picture using this — students, farmers, doctors, someone else?"),
    ("Ahh nice, that clears a lot up!", "What would the system actually take as input — photos, text, sensor readings, anything?"),
    ("Perfect, keep going.", "And what should the final output look like — a web app, a dashboard, alerts, a report?"),
    ("Got it, we're almost there.", "Last one: how many weeks do you have, and which tools/languages are you comfy with?"),
]

def brainstorm_fallback_reply(messages):
    """Friendly scripted mentor turn used when Gemini is unavailable."""
    user_turns = sum(1 for m in messages if m.get("role") == "user")
    idea = next((str(m.get("content", "")) for m in messages if m.get("role") == "user"), "")
    if 0 < user_turns <= len(FRIENDLY_FALLBACK_TURNS):
        react, question = FRIENDLY_FALLBACK_TURNS[user_turns - 1]
        return {"reply": f"{react} {question}", "ready": False, "arxiv_query": idea[:80]}
    return {
        "reply": "I think I've got a clear picture now! Hit the button below and I'll turn this chat into doable projects for you. 🚀",
        "ready": True,
        "arxiv_query": idea[:80],
    }

def brainstorm_mentor_reply(messages):
    """One friendly mentor turn: react to the student, share possible ways/timelines/best
    approach, then ask exactly ONE next question — like chatting with a friend."""
    model = get_gemini_model()
    if model is None:
        return brainstorm_fallback_reply(messages)
    transcript = "\n".join(
        f"{'STUDENT' if m.get('role') == 'user' else 'MENTOR'}: {str(m.get('content', ''))[:400]}"
        for m in messages[-12:]
    )
    prompt = f"""
You are a friendly senior mentor chatting with an engineering student about their project idea.
Talk like a supportive friend: casual, warm, short sentences. Never lecture. Never open with
praise filler like "great idea" or "awesome".

CHAT SO FAR (oldest first):
{transcript}

YOUR JOB THIS TURN:
1. React naturally to the student's latest message (1-2 lines, like a friend would).
2. Share useful thoughts based on the chat so far: possible ways this could be built, which
   approach would work best and why, a realistic time estimate in weeks, anything about data
   or difficulty. Keep it 2-4 short lines — this is a chat, not an essay.
3. Ask exactly ONE next question — the most useful thing you still don't know
   (target users, data availability, expected output, skills, timeline).
4. ready: set true ONLY if you already know the target user, the data/input, the expected
   output, and a rough timeline. Otherwise false.
5. arxiv_query: 3-6 plain keywords (no quotes, no AND) capturing the refined idea, for finding
   research papers later.

Return ONLY valid JSON:
{{"reply": "...", "ready": false, "arxiv_query": "..."}}
"""
    data = extract_json(ai_generate(prompt, max_tokens=1024, model=model))
    if isinstance(data, dict) and data.get("reply"):
        first_user = next((str(m.get("content", "")) for m in messages if m.get("role") == "user"), "")
        arxiv_query = str(data.get("arxiv_query", "")).replace('"', "").strip()[:120]
        return {
            "reply": str(data["reply"]).strip(),
            "ready": bool(data.get("ready")),
            "arxiv_query": arxiv_query or first_user[:80],
        }
    return brainstorm_fallback_reply(messages)

def generate_idea_package(idea, context, arxiv_query):
    """'Your Idea' final step: ONLY Gemini + arXiv (no database), run in parallel."""
    package = {"db_projects": [], "ai_projects": [], "arxiv_projects": [], "research_directions": []}
    model = get_gemini_model()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        future_ai = pool.submit(fetch_gemini_projects, idea, model, 9, context)
        future_arxiv = pool.submit(fetch_arxiv_research_ideas, arxiv_query or idea, 12)
        try:
            ai_projects, directions = future_ai.result() or ([], [])
        except Exception:
            ai_projects, directions = [], []
        try:
            package["arxiv_projects"] = future_arxiv.result() or []
        except Exception:
            package["arxiv_projects"] = []

    fallback = fallback_project_package(idea)
    package["ai_projects"] = ai_projects or fallback["projects"]
    package["research_directions"] = directions or fallback["research_directions"]
    return package

def run_idea_search():
    """Turn the whole brainstorming chat into results from Gemini and arXiv (no database)."""
    chat = st.session_state.get("idea_chat") or {}
    messages = [m for m in (chat.get("messages") or []) if m.get("content")]
    idea = next((str(m["content"]) for m in messages if m.get("role") == "user"), "") or "student idea"
    context = "\n".join(
        f"{'Student' if m.get('role') == 'user' else 'Mentor'}: {str(m.get('content', ''))[:500]}"
        for m in messages[-16:]
    )

    st.session_state["last_search"] = idea
    st.session_state["searched"] = True
    st.session_state["search_mode"] = "idea"
    st.session_state["results"] = []
    st.session_state["db_results"] = []
    st.session_state["arxiv_results"] = []
    st.session_state["research_directions"] = []
    st.session_state["db_page"] = 1
    st.session_state["ai_page"] = 1
    st.session_state["arxiv_page"] = 1

    with st.spinner("Turning our chat into doable projects..."):
        package = generate_idea_package(idea, context, str(st.session_state.get("idea_arxiv_query", "")).strip())
    st.session_state["results"] = package["ai_projects"]
    st.session_state["arxiv_results"] = package["arxiv_projects"]
    st.session_state["research_directions"] = package["research_directions"]
    st.rerun()

# ======================================================
# arXiv RESEARCH (fresh research ideas column support)
# ======================================================
def fetch_arxiv_papers(query, limit=5):
    try:
        encoded = requests.utils.quote(clean_text(query))
        url = (f"https://export.arxiv.org/api/query?search_query=all:{encoded}"
               f"&start=0&max_results={limit}&sortBy=relevance&sortOrder=descending")
        res = requests.get(url, timeout=12)
        res.raise_for_status()
        root = ET.fromstring(res.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        papers = []
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            link_el = entry.find("atom:id", ns)
            title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else "Research Paper"
            summary = summary_el.text.strip().replace("\n", " ") if summary_el is not None and summary_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            papers.append({"title": title[:110], "summary": summary[:280], "link": link})
        return papers
    except Exception:
        return []

def fetch_arxiv_research_ideas(query, limit=12):
    """Latest arXiv papers turned into research-flavored project ideas (3rd results column).
    Handles combos too: 'ai + ml' -> (all:"artificial intelligence") AND (all:"machine learning").
    """
    try:
        q = clean_text(query)
        parts = [ALIASES.get(p, p) for p in re.split(r"\s*\+\s*|\s*,\s*|\s*/\s*|\s*&\s*|\s+and\s+", q) if p.strip()]
        if len(parts) > 1:
            search_query = " AND ".join(f'all:"{p}"' for p in parts)
        else:
            search_query = f"all:{q}"
        url = (
            f"https://export.arxiv.org/api/query?search_query={requests.utils.quote(search_query)}"
            f"&start=0&max_results={limit}&sortBy=relevance&sortOrder=descending"
        )
        res = requests.get(url, timeout=12)
        res.raise_for_status()
        root = ET.fromstring(res.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        ideas = []
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            link_el = entry.find("atom:id", ns)
            published_el = entry.find("atom:published", ns)
            title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else "Research Paper"
            summary = summary_el.text.strip().replace("\n", " ") if summary_el is not None and summary_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            published = published_el.text[:10] if published_el is not None and published_el.text else ""
            if published:
                summary = f"Published {published}. {summary}"
            ideas.append({
                "title": title[:110],
                "description": summary[:400] or "Read the paper and build a simplified working version of its method.",
                "domain": "Research · " + (query.strip().title()[:40] if query.strip() else "General"),
                "difficulty": "Advanced",
                "skills": "Research Reading, Literature Survey, Implementation",
                "duration": "6 - 10 weeks",
                "why": "Fresh from current research — implement a simplified version of this paper as your project.",
                "research_expansion": "Reproduce the paper's baseline, identify one gap, and propose your own improvement.",
                "source": "arXiv Research",
                "link": link,
            })
        return ideas
    except Exception:
        return []

# ======================================================
# FILE UPLOAD + PARSING
# ======================================================
TEXT_EXTS = {".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rb", ".php",
             ".txt", ".md", ".csv", ".json", ".html", ".css", ".ipynb", ".yaml", ".yml", ".xml", ".sql", ".r"}

def parse_uploaded_file(uploaded_file):
    """Return extracted text (truncated) plus a note for unsupported types."""
    name = uploaded_file.name
    suffix = Path(name).suffix.lower()
    max_chars = 8000
    try:
        if suffix in TEXT_EXTS:
            raw = uploaded_file.getvalue().decode("utf-8", errors="ignore")
            if suffix == ".ipynb":
                try:
                    nb = json.loads(raw)
                    cells = []
                    for cell in nb.get("cells", []):
                        cells.append("".join(cell.get("source", [])))
                    raw = "\n".join(cells)
                except Exception:
                    pass
            return raw[:max_chars], None
        if suffix == ".pdf":
            if PdfReader is None:
                return "", "PDF parsing needs pypdf (pip install pypdf)."
            reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:40])
            return text[:max_chars], None
        if suffix == ".docx":
            if docx is None:
                return "", "DOCX parsing needs python-docx (pip install python-docx)."
            document = docx.Document(io.BytesIO(uploaded_file.getvalue()))
            text = "\n".join(p.text for p in document.paragraphs[:400])
            return text[:max_chars], None
        return "", f"Unsupported file type: {suffix or 'unknown'} (supported: code/text, pdf, docx)."
    except Exception as e:
        return "", f"Could not read {name}: {e}"

def heuristic_upload_analysis(combined_text, file_names):
    """Offline analysis used when Gemini is unavailable."""
    text = clean_text(combined_text)
    domain_hits = {
        "Machine Learning": ["model", "train", "accuracy", "sklearn", "classifier", "regression", "dataset"],
        "Deep Learning": ["neural", "cnn", "lstm", "epoch", "tensorflow", "torch", "transformer"],
        "Computer Vision": ["image", "opencv", "camera", "pixel", "detection", "frame"],
        "NLP": ["text", "sentiment", "token", "nlp", "language", "chatbot", "corpus"],
        "Data Analysis": ["pandas", "dataframe", "plot", "visualization", "statistics", "analysis"],
        "Web/App Development": ["flask", "django", "streamlit", "html", "api", "frontend", "react"],
        "IoT/Embedded": ["sensor", "arduino", "raspberry", "gpio", "serial"],
    }
    detected = [d for d, keys in domain_hits.items() if any(k in text for k in keys)][:4] or ["General Software"]

    appreciation = (
        f"👏 Nice work getting {len(file_names)} file(s) to this stage — you already have "
        f"{', '.join(detected[:2])} working together, and that's the hardest part of any project. "
        "Let's build on what you've made!"
    )
    summary = (
        f"You uploaded {len(file_names)} file(s): {', '.join(file_names[:5])}. "
        f"The content appears to relate to: {', '.join(detected)}. "
        "Below is a structured breakdown based on keyword analysis (connect Gemini for a deeper AI read)."
    )
    row1 = [
        {"point": "Main focus area", "detail": f"Content is centered around {', '.join(detected)}."},
        {"point": "File composition", "detail": f"Files include: {', '.join(file_names[:6])}."},
        {"point": "Observed building blocks", "detail": "Functions, data handling, and outputs were detected in the content."},
        {"point": "Documentation level", "detail": "README/report-style explanations appear " + ("present." if any(w in text for w in ['readme', 'introduction', 'abstract', 'conclusion']) else "minimal — a report section would strengthen it.")},
    ]
    row2 = [
        {"title": "Add evaluation metrics", "detail": "Add measurable evaluation (accuracy/F1, error rates, or user testing) to make results credible."},
        {"title": "Add a clean user interface", "detail": "Wrap the core logic in a Streamlit/web UI so non-technical users can try it."},
        {"title": "Add comparison baselines", "detail": "Compare your method against at least one simple baseline to show improvement."},
        {"title": "Add data preprocessing documentation", "detail": "Document cleaning steps and assumptions so results are reproducible."},
        {"title": "Add deployment", "detail": "Deploy the working version (Streamlit Cloud/HuggingFace) and link it in your report."},
    ]
    row3 = [
        {"title": f"Extend toward {detected[0]} + real-world data", "detail": "Test your existing work on a larger/new dataset and report how performance changes."},