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
        # Already registered locally — treat as success so verification doesn't
        # fail on a repeat attempt; the account is what the user wanted.
        return None
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
    """Try Supabase first; fall back to local store if unavailable.

    Returns None on success. If the account already exists, we still return None
    (treating it as success) — the caller is verifying an email, not creating a
    brand-new account, so an existing record is the expected outcome on retry.
    """
    if supabase:
        try:
            supabase.auth.sign_up({
                "email": email, "password": password,
                "options": {"data": {"full_name": full_name}},
            })
            return None
        except Exception as e:
            err = str(e).lower()
            if "already registered" in err or "already exists" in err or "user already" in err:
                # Account already exists — that's fine for verification.
                return None
            # Any other Supabase error: fall through to local so the user isn't blocked.
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
        {"title": "Research expansion", "detail": "Survey 5 recent papers in your area, identify one gap, and prototype the improvement."},
        {"title": "Cross-domain pivot", "detail": "Apply the same pipeline to a different domain (education, healthcare, finance) for a new project."},
        {"title": "Efficiency/optimization direction", "detail": "Optimize speed or memory usage and quantify the improvement."},
    ]
    base_domain = detected[0].title()
    suggested = [
        {"title": f"Simple web demo for {base_domain}", "description": "Wrap your existing work in a clean Streamlit page so anyone can try it without code.", "difficulty": "Beginner", "duration": "2 - 3 weeks"},
        {"title": f"Sample data pack for {base_domain}", "description": "Collect and document a small clean dataset your project can run on end-to-end.", "difficulty": "Beginner", "duration": "2 - 3 weeks"},
        {"title": f"Evaluation mini-report for {base_domain}", "description": "Add basic metrics and a one-page results write-up to make your work credible.", "difficulty": "Beginner", "duration": "3 - 4 weeks"},
        {"title": f"Baseline comparison for {base_domain}", "description": "Compare your method against one simple baseline and report where it wins or loses.", "difficulty": "Intermediate", "duration": "4 - 6 weeks"},
        {"title": f"End-to-end automation for {base_domain}", "description": "Chain input → processing → output into one automated pipeline with a single click.", "difficulty": "Intermediate", "duration": "4 - 6 weeks"},
        {"title": f"Analytics dashboard for {base_domain}", "description": "Visualize your results with charts and filters so patterns are easy to see.", "difficulty": "Intermediate", "duration": "4 - 6 weeks"},
        {"title": f"Research prototype in {base_domain}", "description": "Survey recent papers, reproduce one baseline, and propose a measurable improvement.", "difficulty": "Advanced", "duration": "8 - 12 weeks"},
        {"title": f"Deployed API version of {base_domain}", "description": "Package the core logic as an API, deploy it, and measure real-world performance.", "difficulty": "Advanced", "duration": "8 - 12 weeks"},
        {"title": f"Cross-domain pivot study for {base_domain}", "description": "Apply the same pipeline to education, healthcare, or finance and compare results.", "difficulty": "Advanced", "duration": "8 - 12 weeks"},
    ]
    return {
        "appreciation": appreciation,
        "summary": summary,
        "row1_contents": row1,
        "row2_additions": row2,
        "row3_expansions": row3,
        "detected_domains": detected,
        "suggested_projects": suggested,
    }

def _gemini_upload_overview(combined, file_names, model):
    """Gemini call 1: appreciation + summary + what's inside the files."""
    prompt = f"""
You are an academic AI project mentor. A student uploaded their previous/existing project files for review.
File names: {', '.join(file_names)}
File contents (may be truncated):
\"\"\"
{combined[:10000]}
\"\"\"

FIRST: silently read the content above carefully — actual function/class names, section headings,
dataset names, libraries, methods, results, topic. Everything you output MUST come from THIS text.

STRICT RULES (violating these makes the analysis useless):
- Reference CONCRETE things you found: real function/module/section names, real libraries
  (e.g. 'pandas', 'tensorflow'), real methods (e.g. 'Random Forest', 'convolutional layers'),
  real datasets, real findings or paper contributions. Name them explicitly.
- FORBIDDEN: generic statements that could be true for any project (e.g. "functions and data
  handling were detected"). If you cannot ground a statement in the actual text, do not write it.
- If the files are a research paper, use its actual title/topic, its proposed method, its
  experiments and its stated results.

Analyze and return ONLY valid JSON in exactly this shape:
{{
  "appreciation": "2-3 line warm, friendly appreciation naming the genuinely good SPECIFIC parts of this work",
  "summary": "2-3 line summary of what THIS student built/wrote, using the actual content",
  "row1_contents": [{{"point": "...", "detail": "..."}}],
  "detected_domains": ["..."]
}}

Where:
- row1_contents: 5-6 entries, each naming a concrete thing found (module, section, technique,
  dataset, library, result) and what it does in THIS work. 'point' = its name, 'detail' = the specific role it plays.
- detected_domains: 2-4 domain names this work belongs to (e.g. Machine Learning, Web/App Development).
"""
    return extract_json(ai_generate(prompt, max_tokens=2048, model=model))

def _gemini_upload_suggestions(combined, file_names, model):
    """Gemini call 2: additions + expansions + 9 next projects."""
    prompt = f"""
You are an academic AI project mentor. A student uploaded their previous/existing project files for review.
File names: {', '.join(file_names)}
File contents (may be truncated):
\"\"\"
{combined[:10000]}
\"\"\"

FIRST: read the content above carefully — methods used, modules present, data handled, results
obtained, gaps left open. Every suggestion below MUST grow out of THIS specific work.

STRICT RULES:
- Each entry must explicitly connect to something concrete found in the files (name the
  module/method/dataset/finding it builds on, e.g. "your CNN classifier currently uses only
  2 classes — extend it to...").
- FORBIDDEN: generic advice that would fit any project (e.g. plain "add evaluation metrics",
  "add a UI") unless you tie it to what their work specifically lacks.
- The 9 projects must be a progression of THIS student's work — not random popular ideas.

Analyze and return ONLY valid JSON in exactly this shape:
{{
  "row2_additions": [{{"title": "...", "detail": "..."}}],
  "row3_expansions": [{{"title": "...", "detail": "..."}}],
  "suggested_projects": [{{"title": "...", "description": "...", "difficulty": "Beginner|Intermediate|Advanced", "duration": "..."}}]
}}

Where:
- row2_additions: 5-6 entries of NEW features/improvements on top of THEIR existing modules.
- row3_expansions: 4-5 entries of bigger directions (research angle, pivot, scale-up) grounded in their topic.
- suggested_projects: exactly 9 concrete next projects building on this work — 3 Beginner, 3 Intermediate, 3 Advanced.
"""
    return extract_json(ai_generate(prompt, max_tokens=3072, model=model))

def analyze_uploads(parsed_texts, file_names):
    combined = "\n\n".join(t for t, _ in parsed_texts if t)[:12000]
    model = get_gemini_model()
    if model is not None and combined.strip():
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f_overview = pool.submit(_gemini_upload_overview, combined, file_names, model)
            f_suggest = pool.submit(_gemini_upload_suggestions, combined, file_names, model)
            try:
                overview = f_overview.result() or {}
            except Exception:
                overview = {}
            try:
                suggestions = f_suggest.result() or {}
            except Exception:
                suggestions = {}

        if isinstance(overview, dict) and (overview.get("row1_contents") or overview.get("summary")):
            merged = {
                "appreciation": overview.get("appreciation", ""),
                "summary": overview.get("summary", ""),
                "row1_contents": overview.get("row1_contents", []),
                "detected_domains": overview.get("detected_domains", []),
                "row2_additions": suggestions.get("row2_additions", []),
                "row3_expansions": suggestions.get("row3_expansions", []),
                "suggested_projects": suggestions.get("suggested_projects", []),
            }
            if not merged["row2_additions"] and not merged["row3_expansions"] and not merged["suggested_projects"]:
                offline = heuristic_upload_analysis(combined, file_names)
                merged["row2_additions"] = offline["row2_additions"]
                merged["row3_expansions"] = offline["row3_expansions"]
                merged["suggested_projects"] = offline["suggested_projects"]
                merged["_offline_partial"] = True
            return merged
    result = heuristic_upload_analysis(combined, file_names)
    result["_offline"] = True
    return result

# ======================================================
# BOOKMARKS
# ======================================================
def save_bookmark(project):
    payload = {
        "id": f"bm_{abs(hash(project.get('title', '')))}",
        "user_email": current_user_email(),
        "title": project.get("title", ""),
        "description": project.get("description", ""),
        "domain": project.get("domain", ""),
        "difficulty": project.get("difficulty", ""),
        "skills": project.get("skills", ""),
        "duration": project.get("duration") or project.get("time", ""),
        "why": project.get("why", ""),
        "research_expansion": project.get("research_expansion", ""),
        "source": project.get("source", ""),
        "link": project.get("link", ""),
    }
    existing = {str(b.get("title", "")).lower() for b in st.session_state.get("local_bookmarks", [])}
    if str(payload["title"]).lower() not in existing:
        st.session_state.setdefault("local_bookmarks", []).append(payload)
        save_local_state()
    db_insert("bookmarks", {k: payload.get(k, "") for k in
                            ["user_email", "title", "description", "domain", "difficulty", "skills"]})

def get_bookmarks():
    rows = db_select("bookmarks", {"user_email": current_user_email()}, "created_at")
    local = st.session_state.get("local_bookmarks", [])
    return merge_unique_by_id(local, rows) if local else (rows or local)

# ======================================================
# ROADMAP (dynamic, with idea-injection support)
# ======================================================
def fallback_roadmap(project):
    title = project.get("title", "Project")
    return [
        {"step_no": 1, "title": f"Define the {title} problem clearly",
         "description": "Write exactly what the system takes as input, produces as output, and who will use it.",
         "tasks": ["Write the problem statement", "List inputs and outputs", "Identify target users"]},
        {"step_no": 2, "title": "Collect resources, papers, and sample data",
         "description": "Gather datasets, sample inputs, and related references before coding.",
         "tasks": ["Find 2 datasets or sample inputs", "Save 3 related papers/links", "Note data limitations"]},
        {"step_no": 3, "title": "Design the method and architecture",
         "description": "Plan the workflow: how data moves between modules and which algorithms/libraries you will use.",
         "tasks": ["Draw the architecture diagram", "Choose libraries and algorithms", "Define evaluation strategy"]},
        {"step_no": 4, "title": "Build the core working prototype",
         "description": "Implement the main logic with a small working version before building the full app.",
         "tasks": ["Create the project skeleton", "Implement core logic", "Verify output on 3 sample cases"]},
        {"step_no": 5, "title": "Evaluate and improve the result",
         "description": "Test correctness and quality with suitable metrics and improve weak areas.",
         "tasks": ["Run tests on multiple inputs", "Record evaluation metrics", "Fix weak cases"]},
        {"step_no": 6, "title": "Build a clean demo interface",
         "description": "Create a simple interface where anyone can try the project without touching code.",
         "tasks": ["Build Streamlit/UI input section", "Display results clearly", "Add sample demo data"]},
        {"step_no": 7, "title": "Prepare report, PPT, and viva explanation",
         "description": "Write the final academic material: report, slides, and viva answers.",
         "tasks": ["Write report with screenshots", "Prepare PPT", "Prepare viva answers"]},
    ]

def generate_dynamic_roadmap(project):
    model = get_gemini_model()
    if model is not None:
        prompt = f"""
Create a project execution roadmap for this student project.
Project: {json.dumps(project)}
Return ONLY a valid JSON list with 7 steps.
Each step must have: step_no, title, description, tasks (list of 3 short checklist items).
Make it specific to this project, not generic.
"""
        data = extract_json(ai_generate(prompt))
        if isinstance(data, list) and data:
            steps = []
            for i, step in enumerate(data[:7], start=1):
                if not isinstance(step, dict):
                    continue
                tasks = step.get("tasks", ["Understand", "Implement", "Verify"])
                if isinstance(tasks, str):
                    tasks = [tasks]
                steps.append({
                    "step_no": int(step.get("step_no", i)),
                    "title": str(step.get("title", f"Step {i}")),
                    "description": str(step.get("description", "Complete this phase.")),
                    "tasks": [str(t) for t in tasks][:5],
                })
            if steps:
                return steps
    return fallback_roadmap(project)

def get_project_steps(project_id):
    pid = str(project_id)
    local_steps = st.session_state.get("local_roadmaps", {}).get(pid, [])
    if pid.startswith("local_"):
        return local_steps
    try:
        if supabase:
            rows = supabase.table("roadmap_steps").select("*").eq("project_id", pid).order("step_no").execute().data or []
            if rows:
                return merge_unique_by_id(rows, local_steps)
    except Exception:
        pass
    return local_steps

def add_idea_step_to_roadmap(project_id, idea):
    """Insert a student's chat idea as a new roadmap step + timeline entry."""
    steps = get_project_steps(project_id)
    if not steps:
        return None
    max_no = max(int(s.get("step_no", 0)) for s in steps)
    new_step_no = max_no + 1

    last = steps[-1]
    if any(w in str(last.get("title", "")).lower() for w in ["report", "ppt", "viva", "final", "presentation"]):
        insert_index = len(steps) - 1
        new_step_no = int(last.get("step_no", max_no))
        for s in steps:
            if int(s.get("step_no", 0)) >= new_step_no:
                s["step_no"] = int(s["step_no"]) + 1
    else:
        insert_index = len(steps)

    new_step = {
        "step_no": new_step_no,
        "title": f"💡 Student idea: {idea.get('step_title', 'New direction')}",
        "description": idea.get("step_description", ""),
        "tasks": idea.get("step_tasks", ["Explore the idea", "Add it to your work", "Document the result"]),
        "status": "pending",
        "origin": "chat_idea",
        "verdict": idea.get("rating", ""),
        "verdict_reason": idea.get("reason", ""),
    }
    steps.insert(insert_index, new_step)
    st.session_state.setdefault("local_roadmaps", {})[str(project_id)] = steps
    save_local_state()

    append_project_reminder(project_id, make_reminder(
        project_id,
        "New idea added to roadmap",
        f"You added: {idea.get('step_title', 'a new idea')}. AI verdict: {idea.get('rating', '')}. {idea.get('reason', '')}",
        datetime.utcnow().date(),
        "info",
        "idea",
    ))
    project_title = st.session_state.get("active_project", {}).get("title", "your project") if steps else "your project"
    send_email_notification(
        current_user_email(),
        "New idea added to your roadmap",
        f"Project: {project_title}\n"
        f"Idea: {idea.get('step_title', '')}\nAI verdict: {idea.get('rating', '')}\n\n{idea.get('reason', '')}\n\n— AI Project Mentor",
    )
    return new_step

# ======================================================
# CHAT: mentor replies + idea evaluation
# ======================================================
def get_chat(project_id):
    pid = str(project_id)
    local_chat = st.session_state.get("local_chat", {}).get(pid, [])
    if pid.startswith("local_"):
        return local_chat
    rows = db_select("project_chat_history", {"project_id": pid}, "created_at", desc=False)
    return rows if rows else local_chat

def save_chat(project_id, role, message, meta=None):
    pid = str(project_id)
    payload = {
        "project_id": None if pid.startswith("local_") else pid,
        "user_email": current_user_email(),
        "role": role,
        "message": message,
        "meta": json.dumps(meta) if meta else "",
        "created_at": datetime.utcnow().isoformat(),
    }
    st.session_state.setdefault("local_chat", {}).setdefault(pid, []).append(payload)
    save_local_state()
    if not pid.startswith("local_"):
        db_insert("project_chat_history", payload)

def mentor_reply(project, steps, user_message, chat_history=None):
    current_step = next((s for s in steps if s.get("status") != "completed"), None)
    if current_step:
        step_title = current_step.get("title", "current step")
        step_description = current_step.get("description", "")
        tasks = current_step.get("tasks", [])
    else:
        step_title = "Final preparation"
        step_description = "Prepare final report, PPT, screenshots, and viva answers."
        tasks = ["Prepare report", "Prepare PPT", "Prepare viva answers"]

    roadmap_text = "\n".join(
        f"Step {s.get('step_no')}: {s.get('title')} [{s.get('status', 'pending')}]" for s in steps[:12]
    )
    history_text = "\n".join(
        f"{m.get('role', 'user')}: {str(m.get('message', ''))[:200]}"
        for m in (chat_history or [])[-8:]
    )

    model = get_gemini_model()
    if model is None:
        return ("AI mentor is offline right now (Gemini API not connected). "
                "Meanwhile: focus on the current roadmap step's checklist, and tick tasks as you finish them. "
                "You can still add ideas via 'Rate as new idea' — they will be stored and rated later.")

    prompt = f"""
You are the AI Project Mentor for an engineering student working on this project.

PROJECT: {project.get('title', 'this project')}
Description: {str(project.get('description', ''))[:300]}
Domain: {project.get('domain', 'General')} | Difficulty: {project.get('difficulty', 'Intermediate')}
Current step: {step_title} - {step_description}

Recent conversation (for context, oldest first):
{history_text or '(this is the first message)'}

Student asked: "{user_message}"

Answer rules (follow ALL):
1. FIRST, identify every part of the question. If the student asks two or more things
   (e.g., "what is X and how is it different from Y?"), you MUST answer ALL parts.
   Skipping any part is the worst mistake you can make here.
2. VERY FIRST LINE = the actual answer. NEVER open with praise or filler like
   "That's a great question", "Good question", "I'm glad you asked", "Certainly",
   or any restatement of the question. Jump straight into the answer.
3. After the first line, briefly explain each part of the question.
4. Maximum 170 words. Stay concise, but NEVER cut a part of the answer just to be short.
5. Use short bullets or short lines; no long code — at most 3-4 lines if truly needed.
6. Be specific to this project. No filler, no summaries of what they already know.
7. Tone: friendly and encouraging, like a supportive senior explaining to a friend.
   Warm but direct — friendliness comes from simple wording, not from praise or fluff.
"""
    reply = ai_generate(prompt)
    return reply or "The AI mentor could not respond right now. Please try again in a moment."

def evaluate_student_idea(project, steps, idea_text):
    """Rate a mid-project idea: good/bad/doable + proposed roadmap step."""
    model = get_gemini_model()
    if model is None:
        return {
            "rating": "Doable with changes",
            "reason": "AI rating is offline, so this is a neutral heuristic: the idea is stored and you can validate it with your guide.",
            "suggestion": "Discuss feasibility with your project guide before investing time.",
            "step_title": idea_text[:70],
            "step_description": f"Explore this student-proposed idea: {idea_text}",
            "step_tasks": ["Define scope of the idea", "Prototype quickly", "Decide keep/drop based on results"],
        }

    roadmap_text = "\n".join(f"Step {s.get('step_no')}: {s.get('title')}" for s in steps[:12])
    prompt = f"""
You are an academic project mentor. A student is mid-way through a project and pitches a NEW idea.
Project: {json.dumps({k: project.get(k, "") for k in ["title", "domain", "difficulty", "description"]})}
Current roadmap:
{roadmap_text}

STUDENT'S NEW IDEA:
{idea_text}

Evaluate the idea honestly:
- rating: one of "Good", "Bad", "Doable with changes"
- reason: 2-3 lines why (feasibility, value, time cost, fit with current project)
- suggestion: one concrete improvement or caution
- If rating is not "Bad", also propose how to add it to the project roadmap as one new step:
  step_title (short), step_description (2 lines), step_tasks (list of 3 short checklist items).

Return ONLY valid JSON:
{{"rating": "...", "reason": "...", "suggestion": "...",
  "step_title": "...", "step_description": "...", "step_tasks": ["...", "...", "..."]}}
"""
    data = extract_json(ai_generate(prompt))
    if isinstance(data, dict) and data.get("rating"):
        tasks = data.get("step_tasks") or ["Explore the idea", "Prototype quickly", "Decide keep/drop"]
        if isinstance(tasks, str):
            tasks = [tasks]
        data["step_tasks"] = [str(t) for t in tasks][:4]
        return data
    return {
        "rating": "Doable with changes",
        "reason": "The AI could not rate this right now. The idea is noted; try rephrasing it more specifically.",
        "suggestion": "Add concrete details: what input, what output, which technique.",
        "step_title": idea_text[:70],
        "step_description": f"Student idea noted during the project: {idea_text}",
        "step_tasks": ["Clarify scope", "Check feasibility with guide", "Prototype if approved"],
    }

# ======================================================
# STEP COMPLETION (gated roadmap)
# ======================================================
def get_tasks_list(step):
    tasks = step.get("tasks", [])
    if isinstance(tasks, str):
        try:
            tasks = json.loads(tasks)
        except Exception:
            tasks = [tasks]
    if not isinstance(tasks, list):
        tasks = [str(tasks)]
    return [str(t) for t in tasks if str(t).strip()]

def get_step_check_key(project_id, step):
    return f"{current_user_email()}::{project_id}::{step.get('step_no')}"

def get_saved_step_checks(project_id, step):
    key = get_step_check_key(project_id, step)
    tasks = get_tasks_list(step)
    saved = st.session_state.setdefault("local_step_checks", {}).get(key, [])
    if not isinstance(saved, list):
        saved = []
    return (saved + [False] * len(tasks))[:len(tasks)]

def save_step_checks(project_id, step, checks):
    key = get_step_check_key(project_id, step)
    st.session_state.setdefault("local_step_checks", {})[key] = checks
    save_local_state()

def first_pending_step(steps):
    for step in steps:
        if step.get("status", "pending") != "completed":
            return step
    return None

def _proof_key(project_id, step_no):
    """Composite key for a step's submitted proof inside local_step_proofs."""
    return f"{project_id}_{step_no}"

def complete_step(step, project_id, proof=None):
    """Mark a roadmap step completed (proof = dict with kind/name + timestamp)."""
    pid = str(project_id)
    step_no = int(step.get("step_no", 0))
    step_title = step.get("title", "Roadmap step")
    if proof:
        st.session_state.setdefault("local_step_proofs", {})[_proof_key(project_id, step_no)] = {
            "kind": proof.get("kind", "screenshot"),
            "name": proof.get("name", ""),
            "submitted_at": datetime.utcnow().isoformat(),
        }

    for s in st.session_state.setdefault("local_roadmaps", {}).get(pid, []):
        if int(s.get("step_no", 0)) == step_no:
            s["status"] = "completed"
            s["completed_at"] = datetime.utcnow().isoformat()

    for r in st.session_state.setdefault("local_reminders", {}).get(pid, []):
        if str(step_no) in str(r.get("title", "")) and r.get("status") == "pending":
            r["status"] = "completed"
            r["message"] = f"Completed: {step_title}"

    steps_after = st.session_state["local_roadmaps"].get(pid, [])
    pending_steps = [s for s in steps_after if s.get("status") != "completed"]

    if pending_steps:
        next_step = sorted(pending_steps, key=lambda x: int(x.get("step_no", 0)))[0]
        st.session_state["roadmap_notice"] = (
            f"Great work! You completed Step {step_no}: {step_title}. "
            f"Next: Step {next_step.get('step_no')}: {next_step.get('title')}."
        )
    else:
        st.session_state["roadmap_notice"] = (
            "Congratulations! All roadmap stages are complete. Generate the Final Pack for report, PPT, viva, and share posts."
        )

    if not pid.startswith("local_") and step.get("id"):
        db_update("roadmap_steps", step["id"], {"status": "completed", "completed_at": datetime.utcnow().isoformat()})

    proof = st.session_state.get("local_step_proofs", {}).get(_proof_key(project_id, step_no))
    proof_line = f"Proof attached: {proof.get('name', 'n/a')}" if proof else "No proof attached."
    send_email_notification(
        current_user_email(),
        f"Stage completed: {step_title}",
        f"You completed Step {step_no}: {step_title}.\n{proof_line}\n"
        + (f"Next: {pending_steps[0].get('title')}" if pending_steps else "All stages complete — generate your Final Pack!")
        + "\n\n— AI Project Mentor",
    )

    save_local_state()
    update_project_progress(project_id)
    st.rerun()

def update_project_progress(project_id):
    steps = get_project_steps(project_id)
    if not steps:
        return
    done = sum(1 for s in steps if s.get("status") == "completed")
    progress = int((done / len(steps)) * 100)
    for p in st.session_state.get("local_projects", []):
        if str(p.get("id")) == str(project_id):
            p["progress"] = progress
    save_local_state()
    if not str(project_id).startswith("local_"):
        db_update("user_projects", project_id, {"progress": progress, "updated_at": datetime.utcnow().isoformat()})

# ======================================================
# START PROJECT
# ======================================================
def start_project(project):
    payload = {
        "user_email": current_user_email(),
        "title": project.get("title", ""),
        "description": project.get("description", ""),
        "domain": project.get("domain", ""),
        "difficulty": project.get("difficulty", ""),
        "skills": project.get("skills", ""),
        "estimated_time": project.get("duration") or project.get("time", ""),
        "source": project.get("source", ""),
        "status": "active",
        "progress": 0,
    }
    project_id = f"local_{len(st.session_state.get('local_projects', [])) + 1}_{abs(hash(payload.get('title', 'project'))) % 10_000_000}"
    project_row = {**payload, "id": project_id}
    upsert_local_project(project_row)

    inserted = db_insert("user_projects", payload)
    if inserted:
        try:
            project_id = inserted[0]["id"]
            project_row = {**payload, "id": project_id}
            upsert_local_project(project_row)
        except Exception:
            pass

    steps = generate_dynamic_roadmap(project)
    local_steps = [{**s, "id": f"{project_id}_{s['step_no']}", "status": "pending"} for s in steps]
    st.session_state.setdefault("local_roadmaps", {})[str(project_id)] = local_steps
    save_local_state()

    if inserted and not str(project_id).startswith("local_"):
        try:
            step_rows = [{
                "project_id": project_id,
                "user_email": current_user_email(),
                "step_no": s["step_no"],
                "title": s["title"],
                "description": s["description"],
                "tasks": s.get("tasks", []),
                "status": "pending",
            } for s in steps]
            db_insert("roadmap_steps", step_rows)
        except Exception:
            pass

    try:
        create_project_reminders(project_id, project_row, local_steps)
    except Exception:
        pass

    send_email_notification(
        current_user_email(),
        f"You started your project: {project_row.get('title', '')}",
        f"You started: {project_row.get('title', '')}\n"
        f"First stage: {local_steps[0].get('title') if local_steps else 'Understand the problem'}\n"
        f"{local_steps[0].get('description') if local_steps else ''}\n\n"
        f"Open AI Project Mentor and work through the checklist.\n\n— AI Project Mentor",
    )

    st.session_state["active_project_id"] = project_id
    st.session_state["active_project"] = project_row
    st.session_state["page"] = "workspace"
    st.rerun()

def get_projects():
    rows = db_select("user_projects", {"user_email": current_user_email()}, "created_at")
    local = st.session_state.get("local_projects", [])
    return merge_unique_by_id(local, rows) if local else (rows or [])

# ======================================================
# FINAL PACK (report + viva + share posts)
# ======================================================
def fallback_final_pack(project, steps):
    title = project.get("title", "Selected Project")
    domain = project.get("domain", "General")
    modules = "\n".join(f"- {s.get('title', 'Roadmap step')}" for s in steps[:7])
    viva = "\n".join(
        f"{i}. {q}" for i, q in enumerate([
            "What real-world problem does your project solve, and for whom?",
            "Why did you choose this approach over alternative methods?",
            "Explain your system architecture and data flow.",
            "What dataset did you use, and how did you preprocess it?",
            "Which evaluation metrics did you choose and why?",
            "What were your results, and how did you validate them?",
            "What are the main limitations of your system?",
            "How would you scale this project for real users?",
            "What did you learn technically and personally from this project?",
            "If given one more month, what would you improve first?",
        ], start=1)
    )
    return {
        "report": f"""### 1. Problem Statement
The project **{title}** addresses a real-world problem in **{domain}** by designing and implementing a working solution.

### 2. Objectives
- Understand the problem and target users
- Build a functional prototype
- Evaluate with measurable metrics
- Prepare report, PPT, and demonstration

### 3. Proposed Methodology
Collect data/resources → preprocess → implement core algorithm → evaluate → build demo interface.

### 4. Modules
{modules}

### 5. Expected Output
A working prototype with clear input, processing flow, results screen, and evaluation summary.

### 6. Evaluation Plan
Test with multiple examples, compare expected vs actual output, note limitations, and suggest improvements.

### 7. PPT Slide Outline
Title → Abstract → Problem Statement → Existing System → Proposed System → Architecture → Modules → Implementation → Results → Conclusion → Future Scope""",
        "viva": viva,
        "github_lines": f"""# {title}
{project.get('description', '')}

## Features
- End-to-end working pipeline for {domain}
- Clean demo interface
- Evaluation results included

## Tech Stack
{project.get('skills', 'Python')}

## Setup
```bash
pip install -r requirements.txt
streamlit run app.py
```""",
        "linkedin_lines": f"""🚀 Excited to share my latest project: "{title}"!

As part of my academic journey, I built a {normalize_difficulty(project.get('difficulty', ''))} level project in {domain}.
💡 What it does: {str(project.get('description', ''))[:180]}...

🛠️ Skills used: {project.get('skills', 'Python')}

This project taught me a lot about problem-solving, implementation, and evaluation. Feedback and suggestions are welcome!

#ProjectShowcase #{domain.replace(' ', '')} #MachineLearning #Python #StudentProject""",
        "devpost_lines": f"""## {title}
**Tagline:** {str(project.get('description', ''))[:100]}...

**What it does:** A {normalize_difficulty(project.get('difficulty', ''))} level {domain} project.

**Built with:** {project.get('skills', 'Python')}

**Challenges we ran into:** Data collection, model tuning, and clean evaluation.

**Accomplishments:** A working end-to-end demo with measurable results.""",
    }

def generate_final_pack(project, steps):
    model = get_gemini_model()
    if model is not None:
        prompt = f"""
Create a final academic project support pack for this student project.
Project: {json.dumps(project)}
Roadmap: {json.dumps(steps)}

Return ONLY valid JSON:
{{
  "report": "markdown with sections: Problem Statement, Objectives, Proposed Methodology, Modules, Expected Output, Evaluation Plan, PPT Slide Outline",
  "viva": "10 numbered viva questions with 1-line answer hints, in markdown",
  "github_lines": "ready-to-paste GitHub repository README content in markdown (title, description, features, tech stack, setup steps)",
  "linkedin_lines": "ready-to-paste LinkedIn post announcing the completed project, professional tone with hashtags",
  "devpost_lines": "ready-to-paste Devpost/hackathon project description"
}}
"""
        data = extract_json(ai_generate(prompt))
        if isinstance(data, dict) and data.get("report"):
            data.setdefault("viva", "")
            data.setdefault("github_lines", "")
            data.setdefault("linkedin_lines", "")
            data.setdefault("devpost_lines", "")
            return data
    return fallback_final_pack(project, steps)

# ======================================================
# RENDERING: PROJECT CARDS
# ======================================================
def render_project_card(project, index, source_key, show_research=True):
    unique_key = f"{source_key}_{index}_{abs(hash(project.get('title', 'x'))) % 100000}"
    with st.container(border=True):
        st.caption(f"Project idea · {project.get('source', 'AI Mentor')}")
        st.markdown(f"#### {project.get('title', 'Project Idea')}")
        badges = (
            difficulty_badge_html(project.get("difficulty", "Intermediate"))
            + f'<span class="time-badge">⏱ {project.get("duration") or project.get("time") or estimate_duration(project.get("difficulty", ""))}</span>'
            + f'<span class="domain-badge">{project.get("domain", "General")}</span>'
        )
        st.markdown(badges, unsafe_allow_html=True)
        st.write(str(project.get("description", ""))[:260])
        with st.expander("View details"):
            st.markdown(f"**Full description:** {project.get('description', '')}")
            st.markdown(f"**Skills:** {project.get('skills', 'Python, Problem Solving')}")
            st.markdown(f"**Why this fits:** {project.get('why', '')}")
            if show_research and project.get("research_expansion"):
                st.markdown(f"**🔬 Research expansion:** {project.get('research_expansion')}")
            if project.get("link"):
                st.markdown(f"[Open research paper]({project.get('link')})")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("⭐ Bookmark", key=f"bm_{unique_key}", use_container_width=True):
                save_bookmark(project)
                st.success("Bookmarked!")
        with c2:
            if st.button("▶️ Start", key=f"start_{unique_key}", type="primary", use_container_width=True):
                start_project(project)

# ======================================================
# PAGE: LOGIN
# ======================================================
def _new_otp_code():
    return str(secrets.randbelow(900000) + 100000)

def _otp_email_body(name, code):
    return (
        f"Hi {name},\n\n"
        f"Your AI Project Mentor verification code is:\n\n    {code}\n\n"
        "It expires in 10 minutes. If you didn't request this, you can ignore this email.\n\n"
        "— AI Project Mentor"
    )

def _render_signup_form():
    """Step 1: details form -> sends a 6-digit OTP to the email."""
    full_name = st.text_input("Full Name", placeholder="Enter your full name", key="su_name")
    email = st.text_input("Email", placeholder="you@example.com", key="su_email")
    password = st.text_input("Password", type="password", placeholder="Create password (min 6 chars)", key="su_pass")
    confirm = st.text_input("Confirm Password", type="password", placeholder="Re-enter password", key="su_confirm")
    if st.button("📧 Send Verification Code", type="primary", use_container_width=True):
        if not full_name or not email or not password or not confirm:
            st.error("Please fill all fields.")
        elif "@" not in email or "." not in email.split("@")[-1]:
            st.error("Enter a valid email address.")
        elif password != confirm:
            st.error("Passwords do not match.")
        elif len(password) < 6:
            st.error("Password must be at least 6 characters.")
        else:
            code = _new_otp_code()
            st.session_state["signup_otp"] = {
                "code": code,
                "expires": datetime.now() + timedelta(minutes=10),
                "name": full_name.strip(),
                "email": email.strip().lower(),
                "password": password,
            }
            sent = send_email_notification(
                email.strip(),
                "Your AI Project Mentor verification code",
                _otp_email_body(full_name.strip(), code),
            )
            if sent:
                st.session_state["otp_notice"] = f"Verification code sent to {email.strip()}. Check your inbox (and spam)."
                # No st.rerun() here — Streamlit will re-render automatically and
                # the OTP step will pick up signup_otp on the next pass.
            else:
                st.session_state.pop("signup_otp", None)
                st.error("Could not send the verification email. Check the [email] SMTP settings in .streamlit/secrets.toml.")

def _verify_signup_otp(code):
    """Step 2 verification: on success creates the account. Returns error string or None."""
    data = st.session_state.get("signup_otp")
    if not data:
        return "No verification pending. Fill the signup form again."
    if datetime.now() > data["expires"]:
        st.session_state.pop("signup_otp", None)
        return "That code expired. Send a new one."
    if not code or str(code).strip() != data["code"]:
        return "Incorrect code. Check your email and try again."

    err = signup_user(data["name"], data["email"], data["password"])
    if err:
        return err

    # Verification succeeded — the account exists (created now, or already there).
    send_email_notification(
        data["email"],
        "Welcome to AI Project Mentor",
        f"Hi {data['name']},\n\nYour email is verified and your account is ready. Log in and start building!\n\n— AI Project Mentor",
    )

    email_clean = data["email"]
    name_clean = data["name"]

    # Wipe every auth-related widget key so the next render starts clean.
    # Streamlit keeps radio/text_input values around by key; if we don't clear
    # them, the login page re-renders from cached widget state even after we
    # set `user`, and the routing block never fires.
    for key in [
        "auth_mode", "login_email", "login_pass",
        "su_name", "su_email", "su_pass", "su_confirm",
        "otp_code", "signup_otp", "otp_notice", "signup_done",
    ]:
        st.session_state.pop(key, None)

    # Now set the logged-in state and route to home.
    st.session_state["user"] = email_clean
    try:
        load_local_state_for_user(email_clean)
    except Exception:
        pass
    st.session_state["page"] = "home"
    st.session_state["home_panel"] = "domain"
    st.session_state["signup_success_notice"] = f"Welcome, {name_clean}! Your account is ready."

    # Force a clean rerun so the routing block at the bottom of the file
    # re-evaluates with `user` set and no stale widget keys.
    st.rerun()
    return None

def _render_otp_step():
    """Step 2: enter the emailed 6-digit code."""
    otp = st.session_state.get("signup_otp")
    if not otp:
        # State got cleared (e.g. after a successful verify). Nothing to show.
        return
    mins_left = max(1, int((otp["expires"] - datetime.now()).total_seconds() // 60) + 1)
    if st.session_state.get("otp_notice"):
        st.info(st.session_state["otp_notice"])
    st.markdown("<div class='form-title'>Verify your email</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='form-sub'>We sent a 6-digit code to <b>{otp['email']}</b>. It expires in ~{mins_left} min.</div>",
        unsafe_allow_html=True,
    )
    code = st.text_input("Verification code", placeholder="Enter 6-digit code", max_chars=6, key="otp_code")
    col_v, col_r, col_b = st.columns([2, 1, 1])
    with col_v:
        if st.button("Verify & Create Account", type="primary", use_container_width=True):
            err = _verify_signup_otp(code)
            if err:
                st.error(err)
            # On success, _verify_signup_otp already set session state and
            # called st.rerun() — nothing more to do here.
    with col_r:
        if st.button("Resend", use_container_width=True):
            otp["code"] = _new_otp_code()
            otp["expires"] = datetime.now() + timedelta(minutes=10)
            if send_email_notification(otp["email"], "Your AI Project Mentor verification code",
                                       _otp_email_body(otp["name"], otp["code"])):
                st.session_state["otp_notice"] = f"New code sent to {otp['email']}"
                st.rerun()
            else:
                st.error("Could not resend the email. Check the [email] SMTP settings.")
    with col_b:
        if st.button("Back", use_container_width=True):
            st.session_state.pop("signup_otp", None)
            st.session_state.pop("otp_notice", None)
            st.rerun()

def show_login_page():
    # If the user got set (e.g. right after verification), bail out so the
    # top-level routing can show the home page instead.
    if st.session_state.get("user"):
        return

    st.markdown("<div class='login-scope'></div>", unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("<div class='top-label'>AI Project Mentor</div>", unsafe_allow_html=True)
        st.markdown("<div class='hero-title'>Your AI-powered project journey</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='hero-sub'>Discover domains, generate doable projects from your own ideas, analyze your "
            "previous work, and get mentored step-by-step from start to finish.</div>",
            unsafe_allow_html=True,
        )

        if st.session_state.get("auth_mode") not in ("Login", "Signup"):
            st.session_state["auth_mode"] = "Login"

        mode = st.radio("Choose", ["Login", "Signup"], horizontal=True,
                        label_visibility="collapsed", key="auth_mode")

        if mode == "Login":
            email = st.text_input("Email", placeholder="you@example.com", key="login_email")
            password = st.text_input("Password", type="password", placeholder="Enter password", key="login_pass")
            if st.button("Login", type="primary", use_container_width=True):
                if not email or not password:
                    st.error("Enter email and password.")
                else:
                    err = login_user(email.strip(), password)
                    if err:
                        st.error(err)
                    else:
                        st.session_state["user"] = email.strip()
                        load_local_state_for_user(email.strip())
                        st.session_state["page"] = "home"
                        st.rerun()
        else:
            otp_data = st.session_state.get("signup_otp")
            if otp_data and datetime.now() <= otp_data["expires"]:
                _render_otp_step()
            else:
                _render_signup_form()

# ======================================================
# PAGE: HOME (4 panels)
# ======================================================
def _apply_logout():
    save_local_state()
    for key in ["user", "active_project_id", "active_project"]:
        st.session_state[key] = None
    st.session_state["page"] = "home"
    st.session_state["home_panel"] = "domain"

def _render_menu_items():
    st.caption(f"Signed in as {current_user_email()}")
    page = st.session_state.get("page", "home")
    if st.button("⭐ Bookmarks", key="menu_bookmarks", use_container_width=True,
                 type="primary" if page == "bookmarks" else "secondary"):
        st.session_state["page"] = "bookmarks"
        st.rerun()
    if st.button("🗂 My Projects", key="menu_projects", use_container_width=True,
                 type="primary" if page == "projects" else "secondary"):
        st.session_state["page"] = "projects"
        st.rerun()
    st.markdown("<div style='height:0.8rem;'></div>", unsafe_allow_html=True)
    if st.button("👋 Logout", key="menu_logout", use_container_width=True):
        _apply_logout()
        st.rerun()

if hasattr(st, "dialog"):
    @st.dialog("Menu", width="small")
    def open_menu_drawer():
        """Right-side slide-in panel: bookmarks / projects / logout."""
        _render_menu_items()
else:
    def open_menu_drawer():
        with st.container(border=True):
            st.markdown("##### Menu")
            _render_menu_items()

def render_top_bar():
    """Brand left; right side: home button + menu button grouped tightly."""
    brand, spacer, actions = st.columns([6, 4, 2], gap="small")
    with brand:
        st.markdown(
            f"""
            <div class='topbar-brand'>
                <div class='topbar-logo'>AI</div>
                <div>
                    <div class='topbar-name'>Project Mentor</div>
                    <div class='topbar-user'>{current_user_email()}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with actions:
        home_col, menu_col = st.columns(2, gap="small")
        with home_col:
            if st.button("🏠", key="nav_home", help="Home"):
                st.session_state["page"] = "home"
                st.rerun()
        with menu_col:
            if st.button("☰", key="nav_menu", help="Menu"):
                open_menu_drawer()
    st.markdown("<div class='topbar-divider'></div>", unsafe_allow_html=True)

def render_quick_actions():
    """Three quick-access buttons under the big search bar."""
    actions = [
        ("idea", "💭", "Your Idea"),
        ("upload", "📁", "Upload Project"),
        ("explore", "🗂", "Explore"),
    ]
    st.markdown("<div class='quick-actions'>", unsafe_allow_html=True)
    cols = st.columns(3, gap="small")
    for col, (key, icon, title) in zip(cols, actions):
        with col:
            active = st.session_state["home_panel"] == key
            if st.button(f"{icon} {title}", key=f"panel_{key}", use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state["home_panel"] = key
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

def render_search_hero():
    """Big search bar with a Recommend button beside it."""
    st.markdown("<div class='search-hero'>", unsafe_allow_html=True)
    st.markdown("<div class='hero-title'>What do you want to build?</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='hero-sub'>Type a domain, a combination, or a raw idea — e.g. <b>ai + ml</b>, "
        "<b>cv + healthcare</b>, or <b>a plant disease detector for farmers</b>.</div>",
        unsafe_allow_html=True,
    )
    bar, btn = st.columns([6, 1], gap="small")
    with bar:
        query = st.text_input(
            "Search",
            placeholder="Search domains, combos, or your own idea...",
            label_visibility="collapsed",
            key="domain_query",
        )
    with btn:
        if st.button("Recommend", type="primary", use_container_width=True):
            if query.strip():
                run_search(query.strip())
            else:
                st.warning("Type a domain or idea first.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.caption("Tip: combine two areas with a + sign — the mentor generates ideas that genuinely mix them.")

def panel_domain():
    st.markdown("<div class='workspace-title'>Search by Domain or Category</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='workspace-sub'>Type above in the search bar and hit <b>Recommend</b>. "
        "Popular starts: ai, ml, nlp, computer vision, iot, cybersecurity, data science.</div>",
        unsafe_allow_html=True,
    )

def panel_idea():
    st.markdown("<div class='workspace-title'>Brainstorm With Your Mentor</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='workspace-sub'>Got an idea in your head? Just say it — your mentor chats with you like a friend, "
        "asks what matters, suggests possible ways and timelines, and then turns the conversation into doable projects "
        "(AI mentor + live arXiv research — no dataset involved).</div>",
        unsafe_allow_html=True,
    )

    if st.session_state.get("idea_chat") is None:
        st.session_state["idea_chat"] = {"messages": [{
            "role": "assistant",
            "content": (
                "Hey! 👋 What's the idea you've got in mind right now? "
                "Don't worry about wording it perfectly — say it like you'd tell a friend, and we'll figure it out together."
            ),
        }]}

    chat = st.session_state["idea_chat"]
    messages = chat.get("messages", [])
    user_turns = sum(1 for m in messages if m.get("role") == "user")
    mentor_ready = (bool(chat.get("ready")) and user_turns >= 2) or user_turns >= 6

    for msg in messages[-30:]:
        if msg.get("role") == "user":
            with st.chat_message("user"):
                st.write(msg["content"])
        else:
            with st.chat_message("assistant"):
                st.write(msg["content"])

    if mentor_ready:
        st.success("🎉 Your mentor has doable projects for the idea you shared — ready when you are!")
        b1, b2, _ = st.columns([1.6, 1, 2])
        with b1:
            if st.button("🎯 Show me the doable projects", type="primary", use_container_width=True):
                run_idea_search()
        with b2:
            if st.button("🗑 Start over", use_container_width=True):
                st.session_state["idea_chat"] = None
                st.session_state["idea_arxiv_query"] = ""
                st.session_state["searched"] = False
                st.session_state["search_mode"] = ""
                st.rerun()
    elif user_turns >= 1:
        st.caption("💬 Keep chatting — the buttons will appear once your mentor knows enough about your idea.")

    user_msg = st.chat_input("Reply to your mentor...")
    if user_msg:
        messages.append({"role": "user", "content": user_msg.strip()})
        with st.spinner("Your mentor is thinking..."):
            reply_pack = brainstorm_mentor_reply(messages)
        messages.append({"role": "assistant", "content": reply_pack["reply"]})
        st.session_state["idea_arxiv_query"] = reply_pack.get("arxiv_query", "")
        chat["ready"] = bool(reply_pack.get("ready"))
        st.rerun()

def panel_upload():
    st.markdown("<div class='workspace-title'>Upload Your Previous Project</div>", unsafe_allow_html=True)
    st.markdown("<div class='workspace-sub'>Upload code files, PDFs, or Word documents of anything you've built before. You'll get a 3-row analysis: what's inside, what you can add, and new directions.</div>", unsafe_allow_html=True)
    files = st.file_uploader(
        "Upload files",
        accept_multiple_files=True,
        type=["py", "js", "ts", "java", "c", "cpp", "txt", "md", "csv", "json", "html", "ipynb", "pdf", "docx"],
        key="upload_files",
    )
    if st.button("📊 Analyze My Files", type="primary", use_container_width=True):
        if not files:
            st.warning("Upload at least one file.")
        else:
            parsed = []
            skipped = []
            for f in files:
                text, note = parse_uploaded_file(f)
                if text:
                    parsed.append((text, f.name))
                if note:
                    skipped.append(note)
            if not parsed:
                st.error("No files could be read. " + " ".join(skipped))
            else:
                with st.spinner("Reading your files and analyzing them with the AI mentor..."):
                    st.session_state["upload_analysis"] = analyze_uploads(parsed, [f.name for f in files])
                    st.session_state["upload_names"] = [f.name for f in files]
                    st.session_state["upload_snippets"] = [
                        {"name": name, "chars": len(text), "preview": text[:350]}
                        for text, name in parsed
                    ]
                if skipped:
                    st.caption("Skipped: " + " ".join(skipped))
    if st.session_state.get("upload_analysis"):
        render_upload_analysis(st.session_state["upload_analysis"])

def panel_explore():
    st.markdown("<div class='workspace-title'>Explore Domains</div>", unsafe_allow_html=True)
    st.markdown("<div class='workspace-sub'>Understand what each domain means, where it is used, and what you can build in it.</div>", unsafe_allow_html=True)
    items = list(DOMAINS.items())
    for i in range(0, len(items), 3):
        cols = st.columns(3, gap="medium")
        for col, (domain_name, info) in zip(cols, items[i:i + 3]):
            with col:
                uses_html = "".join(f"<li>{u}</li>" for u in info["uses"])
                examples_html = "".join(f"<span class='domain-tag'>{x}</span>" for x in info["examples"])
                st.markdown(
                    f"""
                    <div class='domain-card'>
                        <div class='domain-title'><span class='domain-emoji'>{info['emoji']}</span>{domain_name}</div>
                        <div class='domain-section'><b>What it is:</b><br>{info['meaning']}</div>
                        <div class='domain-section'><b>Used for:</b></div>
                        <div class='domain-section' style='margin-top:-0.5rem;'>
                            <ul style='margin-top:0.1rem; padding-left:1.1rem;'>{uses_html}</ul>
                        </div>
                        <div class='domain-section'><b>Best for:</b> {info['best_for']}</div>
                        <div class='domain-section'><b>Example ideas:</b><br>{examples_html}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(f"See projects in {domain_name}", key=f"explore_{domain_name}", use_container_width=True):
                    st.session_state["home_panel"] = "domain"
                    run_search(domain_name)

def show_home_page():
    st.markdown("<div class='home-scope'></div>", unsafe_allow_html=True)

    # Welcome toast shown once, right after a fresh signup.
    if st.session_state.pop("signup_success_notice", None):
        st.success("🎉 Account created successfully — welcome to AI Project Mentor!")

    render_top_bar()

    render_search_hero()
    render_quick_actions()

    panel = st.session_state["home_panel"]
    if panel == "idea":
        panel_idea()
    elif panel == "upload":
        panel_upload()
    elif panel == "explore":
        panel_explore()

    if panel in ("domain", "idea") and st.session_state.get("searched") \
            and st.session_state.get("search_mode") == panel:
        render_search_results(include_db=(panel == "domain"))

def run_search(query):
    st.session_state["last_search"] = query
    st.session_state["searched"] = True
    st.session_state["search_mode"] = "domain"
    st.session_state["results"] = []
    st.session_state["db_results"] = []
    st.session_state["arxiv_results"] = []
    st.session_state["research_directions"] = []
    st.session_state["db_page"] = 1
    st.session_state["ai_page"] = 1
    st.session_state["arxiv_page"] = 1
    with st.spinner("Searching the database, AI mentor, and arXiv in parallel..."):
        package = generate_project_package(query)
        st.session_state["db_results"] = package["db_projects"]
        st.session_state["results"] = package["ai_projects"]
        st.session_state["arxiv_results"] = package["arxiv_projects"]
        st.session_state["research_directions"] = package["research_directions"]
    st.rerun()

def render_expander_card(project, number, source_key, show_research=True):
    """Result card: numbered expander with badges + actions."""
    unique_key = f"{source_key}_{number}_{abs(hash(project.get('title', 'x'))) % 100000}"
    with st.expander(f"{number}. {project.get('title', 'Project Idea')}", expanded=False):
        st.markdown(
            f"""
            <div style="margin-bottom:0.6rem;">
                {difficulty_badge_html(project.get("difficulty", "Intermediate"))}
                <span class="domain-badge">{project.get("domain", "General")}</span>
                <span class="source-badge">{project.get("source", "AI Mentor")}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        why = str(project.get("why", "")).strip()
        if why:
            st.caption(why)
        st.write(str(project.get("description", "")))
        st.markdown(f"**Skills:** {project.get('skills', 'Python, Problem Solving')}")
        st.markdown(f"**Duration:** {project.get('duration') or project.get('time') or estimate_duration(project.get('difficulty', ''))}")
        if show_research and project.get("research_expansion"):
            st.markdown(f"**🔬 Research expansion:** {project.get('research_expansion')}")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("⭐ Bookmark", key=f"bm_{unique_key}", use_container_width=True):
                save_bookmark(project)
                st.success("Bookmarked!")
        with c2:
            if st.button("▶️ Start", key=f"start_{unique_key}", type="primary", use_container_width=True):
                start_project(project)
        with c3:
            link = project.get("link") or project.get("url") or ""
            if link:
                st.markdown(f"[Open link]({link})")

def render_project_stream(projects, source_key, page_key, show_research=True, empty_text="No results in this column yet."):
    """Vertical stack of numbered expander cards with Previous/Next paging."""
    if not projects:
        st.info(empty_text)
        return
    page = max(1, int(st.session_state.get(page_key, 1)))
    start = (page - 1) * RESULTS_PER_PAGE
    end = start + RESULTS_PER_PAGE
    page_data = projects[start:end]

    if not page_data:
        st.session_state[page_key] = 1
        st.rerun()

    for i, project in enumerate(page_data, start=1):
        render_expander_card(project, start + i, source_key, show_research=show_research)

    st.caption(f"Showing {start + 1}–{min(end, len(projects))} of {len(projects)} results.")
    p1, p2 = st.columns(2)
    with p1:
        if st.button("⬅ Previous", key=f"prev_{source_key}", use_container_width=True, disabled=page <= 1):
            st.session_state[page_key] = page - 1
            st.rerun()
    with p2:
        if st.button("Next ➡", key=f"next_{source_key}", use_container_width=True, disabled=end >= len(projects)):
            st.session_state[page_key] = page + 1
            st.rerun()
    if end >= len(projects):
        st.info("You have reached the end of the results for this search.")

def render_search_results(include_db=True):
    query = st.session_state.get("last_search", "")
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown(f'## 🎯 Results for "{query}"')
    if include_db:
        st.caption("Three sources searched in parallel — pick by difficulty and duration, then press Start.")
    else:
        st.caption("Tailored to your brainstorming answers — AI mentor + live arXiv research (no dataset used).")

    db_results = st.session_state.get("db_results", [])
    ai_results = st.session_state.get("results", [])
    arxiv_results = st.session_state.get("arxiv_results", [])
    directions = st.session_state.get("research_directions", [])

    if include_db:
        col_db, col_ai, col_research = st.columns(3, gap="medium")
    else:
        col_ai, col_research = st.columns(2, gap="medium")

    if include_db:
        with col_db:
            st.markdown("### 🗄 Database Results")
            st.caption(f"{len(db_results)} curated ideas matched from the project dataset.")
            render_project_stream(
                db_results, "db_result", "db_page", show_research=False,
                empty_text="No database matches for this query. Try a broader domain word.",
            )

    with col_ai:
        st.markdown("### 🧠 AI Mentor Ideas")
        st.caption(f"{len(ai_results)} doable ideas generated for you — spread across all difficulties.")
        render_project_stream(
            ai_results, "ai_result", "ai_page", show_research=True,
            empty_text="AI mentor is offline or busy — check the Gemini API key and search again.",
        )
        if directions:
            with st.expander(f"🔬 Research expansion directions ({len(directions)})"):
                for direction in directions:
                    st.markdown(f"- **{direction.get('title', '')}** — {direction.get('detail', '')}")

    with col_research:
        st.markdown("### 📚 arXiv Research Ideas")
        st.caption(f"{len(arxiv_results)} fresh research directions pulled live from arXiv.")
        render_project_stream(
            arxiv_results, "arxiv_result", "arxiv_page", show_research=True,
            empty_text="Live research ideas are temporarily unavailable.",
        )

def render_upload_analysis(analysis):
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown(f"## 📊 Analysis of: {', '.join(st.session_state.get('upload_names', [])[:4])}")

    if analysis.get("appreciation"):
        st.success(f"🌟 {analysis['appreciation']}")

    if analysis.get("summary"):
        st.info(analysis["summary"])
    if analysis.get("detected_domains"):
        st.markdown(
            "".join(f'<span class="domain-badge">{d}</span>' for d in analysis["detected_domains"]),
            unsafe_allow_html=True,
        )

    snippets = st.session_state.get("upload_snippets") or []
    if snippets:
        with st.expander("📄 What the mentor actually read from your files"):
            for snip in snippets:
                st.caption(f"**{snip['name']}** — {snip['chars']:,} characters extracted")
                st.text(snip["preview"].replace("\n", " ")[:350] + "...")

    if analysis.get("_offline") or analysis.get("_offline_partial"):
        st.warning(
            "⚡ Gemini couldn't complete the full AI analysis for this upload (it may be busy or rate-limited), "
            "so part of this breakdown is offline/quick-mode. Wait a minute and click 'Analyze My Files' again for fully tailored AI results."
        )

    col_inside, col_add, col_dirs = st.columns(3, gap="medium")

    def _fill_section_box(container, header_html, items, empty_text, accent=""):
        with container:
            with st.container(border=True):
                st.markdown(header_html, unsafe_allow_html=True)
                rendered = 0
                for item in (items or [])[:8]:
                    point = item.get("point", item.get("title", ""))
                    detail = item.get("detail", item.get("description", ""))
                    if not str(point).strip() and not str(detail).strip():
                        continue
                    accent_cls = f" {accent}" if accent else ""
                    st.markdown(
                        f"""
                        <div class='info-item{accent_cls}'>
                            <div class='info-item-title'>{point}</div>
                            <div class='info-item-detail'>{detail}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    rendered += 1
                if not rendered:
                    st.caption(empty_text)

    _fill_section_box(
        col_inside,
        """
        <div class='analysis-row' style='margin-bottom:0.6rem;'>
            <div class='analysis-row-title'>📄 What your files contain</div>
            <div class='analysis-row-sub' style='margin-bottom:0;'>Modules, topics, techniques and sections found in your upload.</div>
        </div>
        """,
        analysis.get("row1_contents"),
        "Nothing detected inside the files yet.",
    )
    _fill_section_box(
        col_add,
        """
        <div class='analysis-row' style='margin-bottom:0.6rem;'>
            <div class='analysis-row-title'>➕ What new you can add</div>
            <div class='analysis-row-sub' style='margin-bottom:0;'>Improvements and features to build on top of your existing work.</div>
        </div>
        """,
        analysis.get("row2_additions"),
        "No additions suggested yet.",
        "green",
    )
    _fill_section_box(
        col_dirs,
        """
        <div class='analysis-row' style='margin-bottom:0.6rem;'>
            <div class='analysis-row-title'>🧭 New directions & expansions</div>
            <div class='analysis-row-sub' style='margin-bottom:0;'>Bigger scope, research angles, and pivots you can take this toward.</div>
        </div>
        """,
        analysis.get("row3_expansions"),
        "No expansion directions yet.",
        "purple",
    )

    suggested = analysis.get("suggested_projects") or []
    if suggested:
        st.markdown("### 🚀 Next projects building on this work")
        cols = st.columns(3, gap="medium")
        for i, project in enumerate(suggested[:9]):
            if not isinstance(project, dict) or not project.get("title"):
                continue
            normalized = {
                "title": project.get("title", "Next Project"),
                "description": project.get("description", ""),
                "domain": ", ".join(analysis.get("detected_domains", [])[:2]) or "Your Previous Work",
                "difficulty": normalize_difficulty(project.get("difficulty", "Intermediate")),
                "skills": project.get("skills", "Python, Problem Solving"),
                "duration": project.get("duration") or estimate_duration(project.get("difficulty", "")),
                "why": "Builds directly on your uploaded work.",
                "source": "AI Mentor",
            }
            with cols[i % 3]:
                render_expander_card(normalized, i + 1, "upload_suggested", show_research=False)

# ======================================================
# PAGE: MY PROJECTS
# ======================================================
def show_projects_page():
    render_top_bar()
    st.markdown("## 🗂 My Projects")
    projects = get_projects()
    if not projects:
        st.info("No active projects yet. Start one from the Home panel.")
        return
    cols = st.columns(3)
    for i, p in enumerate(projects):
        with cols[i % 3]:
            with st.container(border=True):
                st.markdown(f"### {p.get('title')}")
                desc = str(p.get("description", ""))
                st.write(desc[:130] + "..." if len(desc) > 130 else desc)
                progress = int(p.get("progress", 0))
                st.progress(progress)
                st.caption(f"Progress: {progress}% | {p.get('difficulty', 'Intermediate')} | "
                           f"{p.get('estimated_time') or p.get('duration') or ''}")
                reminders = st.session_state.get("local_reminders", {}).get(str(p.get("id")), [])
                pending_count = sum(1 for r in reminders if r.get("status") == "pending")
                if pending_count:
                    st.caption(f"🔔 {pending_count} pending reminder(s)")
                if st.button("Open Workspace", key=f"open_project_{p.get('id')}", use_container_width=True):
                    st.session_state["active_project_id"] = p.get("id")
                    st.session_state["active_project"] = p
                    st.session_state["page"] = "workspace"
                    st.rerun()

# ======================================================
# PAGE: BOOKMARKS
# ======================================================
def build_bookmarks_export(bookmarks):
    rows = []
    for bm in bookmarks:
        rows.append({
            "Title": str(bm.get("title", "")),
            "Description": str(bm.get("description", "")),
            "Domain": str(bm.get("domain", "")),
            "Difficulty": str(bm.get("difficulty", "")),
            "Skills": str(bm.get("skills", "")),
            "Duration": str(bm.get("duration") or bm.get("estimated_time") or ""),
            "Why": str(bm.get("why", "")),
            "Research Expansion": str(bm.get("research_expansion", "")),
            "Source": str(bm.get("source", "")),
        })

    txt_lines = []
    for i, r in enumerate(rows, start=1):
        txt_lines.append(f"{i}. {r['Title']}")
        meta = " | ".join(x for x in [r["Domain"], r["Difficulty"], r["Duration"], r["Source"]] if x)
        if meta:
            txt_lines.append(f"   {meta}")
        if r["Description"]:
            txt_lines.append(f"   Description: {r['Description']}")
        if r["Skills"]:
            txt_lines.append(f"   Skills: {r['Skills']}")
        if r["Why"]:
            txt_lines.append(f"   Why: {r['Why']}")
        if r["Research Expansion"]:
            txt_lines.append(f"   Research expansion: {r['Research Expansion']}")
        txt_lines.append("")
    txt_body = "\n".join(txt_lines).strip() + "\n"
    return rows, txt_body

def show_bookmarks_page():
    render_top_bar()
    st.markdown("## ⭐ Bookmarked Ideas")
    bookmarks = get_bookmarks()
    if not bookmarks:
        st.info("No bookmarks yet. Bookmark ideas from the Home panel.")
        return

    rows, txt_body = build_bookmarks_export(bookmarks)
    csv_data = pd.DataFrame(rows).to_csv(index=False).encode("utf-8")

    st.markdown("### ⬇ Download your bookmarks")
    d_txt, d_csv = st.columns(2)
    with d_txt:
        st.download_button(
            "📄 Download as Text (TXT)",
            data=txt_body,
            file_name="bookmarked_projects.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with d_csv:
        st.download_button(
            "📊 Download as CSV",
            data=csv_data,
            file_name="bookmarked_projects.csv",
            mime="text/csv",
            use_container_width=True,
        )
    st.markdown("<hr>", unsafe_allow_html=True)

    cols = st.columns(3)
    for i, bm in enumerate(bookmarks):
        project = dict(bm)
        if not project.get("duration") and bm.get("estimated_time"):
            project["duration"] = bm.get("estimated_time")
        with cols[i % 3]:
            render_project_card(project, i, "bookmark", show_research=False)
            if st.button("🗑 Remove", key=f"rm_bm_{bm.get('id', i)}", use_container_width=True):
                st.session_state["local_bookmarks"] = [
                    b for b in st.session_state.get("local_bookmarks", [])
                    if str(b.get("id")) != str(bm.get("id"))
                ]
                save_local_state()
                st.rerun()

# ======================================================
# PAGE: WORKSPACE
# ======================================================
def _proof_line(project_id, step_no):
    proof = st.session_state.get("local_step_proofs", {}).get(_proof_key(project_id, step_no))
    if not proof:
        return ""
    name = str(proof.get("name", "")).strip()
    detail = f" — 📎 {name}" if name else " — 📎 proof submitted"
    return f"<small style='color:#34d399;'>Proof verified{detail}</small>"

def render_timeline(steps, project_id=None):
    """Vertical timeline of all roadmap steps including student-added idea steps."""
    st.markdown("### 📍 Project Timeline")
    if not steps:
        st.info("Timeline will appear once the project roadmap is generated.")
        return
    current = first_pending_step(steps)
    current_no = int(current.get("step_no", 0)) if current else None
    for step in sorted(steps, key=lambda s: int(s.get("step_no", 0))):
        no = int(step.get("step_no", 0))
        status = step.get("status", "pending")
        origin = step.get("origin", "")
        if status == "completed":
            dot_cls, dot_txt = "dot-done", "✓"
        elif origin == "chat_idea":
            dot_cls, dot_txt = "dot-idea", "💡"
        elif current_no is not None and no == current_no:
            dot_cls, dot_txt = "dot-current", str(no)
        else:
            dot_cls, dot_txt = "dot-locked", str(no)
        label = step.get("title", "")
        sub = step.get("verdict", "")
        sub_html = f"<br><small style='color:#a4b0be;'>AI verdict: {sub}</small>" if sub else ""
        proof_html = _proof_line(project_id, no) if (project_id and status == "completed") else ""
        st.markdown(
            f"""
            <div class='timeline-item'>
                <div class='timeline-dot {dot_cls}'>{dot_txt}</div>
                <div style='color:#d3dae3; font-size:0.92rem;'>
                    <b>Step {no}:</b> {label}{sub_html}{proof_html}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

def render_gated_roadmap(steps, project_id):
    if st.session_state.get("roadmap_notice"):
        st.success(st.session_state.pop("roadmap_notice"))

    if not steps:
        st.warning("No roadmap found. Start this project again.")
        return

    completed = [s for s in steps if s.get("status") == "completed"]
    current = first_pending_step(steps)
    future = []
    if current:
        current_no = int(current.get("step_no", 0))
        future = [s for s in steps if s.get("status") != "completed" and int(s.get("step_no", 0)) > current_no]

    if completed:
        with st.expander(f"✅ Completed steps ({len(completed)})", expanded=False):
            for step in completed:
                st.success(f"Step {step.get('step_no')}: {step.get('title')}")

    if current:
        with st.container(border=True):
            st.markdown(f"### 🔵 Current Step {current.get('step_no')}: {current.get('title')}")
            st.write(current.get("description", ""))
            tasks = get_tasks_list(current)
            saved_checks = get_saved_step_checks(project_id, current)

            st.markdown("**Complete this checklist to unlock the next step:**")
            new_checks = []
            for idx, task in enumerate(tasks):
                cb_key = f"taskcheck_{project_id}_{current.get('step_no')}_{idx}"
                new_checks.append(st.checkbox(task, value=bool(saved_checks[idx]), key=cb_key))
            save_step_checks(project_id, current, new_checks)

            all_done = bool(tasks) and all(new_checks)
            if not all_done:
                st.info("Tick every checklist item to enable step completion.")

            proof_rec = st.session_state.get("local_step_proofs", {}).get(_proof_key(project_id, current.get("step_no")))
            st.markdown("**📎 Submit proof of work (required):**")
            st.caption("Upload a screenshot or short file showing this step is done — it unlocks the next step.")
            uploaded_proof = st.file_uploader(
                "Proof",
                type=["png", "jpg", "jpeg", "webp", "pdf", "txt", "md", "csv", "ipynb", "zip"],
                key=f"proof_upload_{project_id}_{current.get('step_no')}",
                label_visibility="collapsed",
            )
            proof_ready = uploaded_proof is not None
            if uploaded_proof:
                st.success(f"✅ Proof ready: {uploaded_proof.name} ({uploaded_proof.size // 1024} KB)")
            elif proof_rec:
                st.caption(f"Previously submitted: {proof_rec.get('name', 'proof')}")

            if not proof_ready:
                st.warning("Attach a proof file to enable step completion.")
            if st.button("✅ Submit proof & complete step", key=f"complete_{project_id}_{current.get('step_no')}",
                         use_container_width=True, disabled=not (all_done and proof_ready)):
                complete_step(current, project_id, proof={
                    "kind": (uploaded_proof.type if uploaded_proof else "screenshot"),
                    "name": uploaded_proof.name if uploaded_proof else "",
                    "size": uploaded_proof.size if uploaded_proof else 0,
                })
    else:
        st.success("All roadmap steps are completed. Generate the Final Pack now! 🎉")

    if future:
        st.markdown("### 🔒 Locked upcoming steps")
        for step in future[:3]:
            st.markdown(
                f"<div class='locked-step'>Step {step.get('step_no')}: {step.get('title')}<br>"
                f"<small>Complete the current step's checklist to unlock this.</small></div>",
                unsafe_allow_html=True,
            )
        if len(future) > 3:
            st.caption(f"+ {len(future) - 3} more steps locked")

def render_mentor_chat(project, steps, project_id):
    st.markdown("## 💬 Mentor Chat")
    st.caption("Ask doubts anytime. Have a new idea mid-project? Tick 'Rate as new idea' — the AI rates it and can add it to your roadmap.")

    idea_mode = st.checkbox("💡 Rate as new idea (instead of asking a question)", key="idea_mode_cb")

    chat_rows = get_chat(project_id)
    if not chat_rows:
        st.info("No chat yet. Ask your first question below.")
    for msg in chat_rows[-20:]:
        with st.chat_message("user" if msg.get("role") == "user" else "assistant"):
            st.write(msg.get("message"))
            meta_raw = msg.get("meta") or ""
            if meta_raw:
                try:
                    meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
                except Exception:
                    meta = None
                if isinstance(meta, dict) and meta.get("type") == "idea_rating":
                    verdict = meta.get("rating", "")
                    color = {"Good": "🟢", "Bad": "🔴"}.get(verdict, "🟡")
                    st.markdown(f"{color} **Verdict: {verdict}**")
                    if meta.get("reason"):
                        st.caption(meta["reason"])
                    if meta.get("suggestion"):
                        st.caption(f"💡 {meta['suggestion']}")
                    if verdict != "Bad" and not meta.get("added"):
                        if st.button("➕ Add this idea to my roadmap & timeline",
                                     key=f"add_idea_{abs(hash(str(meta))) % 1000000}"):
                            new_step = add_idea_step_to_roadmap(project_id, meta)
                            if new_step:
                                for r in chat_rows:
                                    try:
                                        m = json.loads(r.get("meta") or "{}") if isinstance(r.get("meta"), str) else (r.get("meta") or {})
                                    except Exception:
                                        m = {}
                                    if isinstance(m, dict) and m.get("type") == "idea_rating":
                                        m["added"] = True
                                        r["meta"] = json.dumps(m)
                                save_local_state()
                                st.success(f"Added to roadmap as Step {new_step.get('step_no')}!")
                                st.rerun()

    user_msg = st.chat_input("Ask about your project, or pitch a new idea...")
    if user_msg:
        if idea_mode:
            save_chat(project_id, "user", f"💡 IDEA: {user_msg}")
            with st.spinner("The mentor is evaluating your idea..."):
                verdict_data = evaluate_student_idea(project, steps, user_msg)
            rating = verdict_data.get("rating", "Doable with changes")
            reply_text = (
                f"**Idea verdict: {rating}**\n\n{verdict_data.get('reason', '')}\n\n"
                f"💡 {verdict_data.get('suggestion', '')}"
                + ("" if rating == "Bad" else "\n\n*If you're happy with this, click the button above to add it to your roadmap & timeline.*")
            )
            save_chat(project_id, "assistant", reply_text, meta={
                "type": "idea_rating",
                "rating": rating,
                "reason": verdict_data.get("reason", ""),
                "suggestion": verdict_data.get("suggestion", ""),
                "step_title": verdict_data.get("step_title", ""),
                "step_description": verdict_data.get("step_description", ""),
                "step_tasks": verdict_data.get("step_tasks", []),
                "added": False,
            })
        else:
            save_chat(project_id, "user", user_msg)
            with st.spinner("The mentor is thinking..."):
                reply = mentor_reply(project, steps, user_msg, chat_rows)
            save_chat(project_id, "assistant", reply)
        st.rerun()

def sync_reminders_with_steps(project_id, steps):
    """Keep reminders aligned 1:1 with the current timeline."""
    pid = str(project_id)
    reminders = st.session_state.get("local_reminders", {}).get(pid, [])
    if not reminders or not steps:
        return
    plan_map = st.session_state.get("local_reminder_plan", {}).get(pid, {})
    step_nos = {str(int(s.get("step_no", 0))) for s in steps}
    completed_nos = {str(int(s.get("step_no", 0))) for s in steps if s.get("status") == "completed"}
    changed = False
    for r in reminders:
        if r.get("kind") == "idea" or r.get("status") == "info":
            continue
        m = re.match(r"Step (\d+)", str(r.get("title", "")))
        if not m:
            continue
        no = int(m.group(1))
        if str(no) not in step_nos:
            later = sorted(int(s.get("step_no", 0)) for s in steps if int(s.get("step_no", 0)) >= no)
            if not later:
                continue
            no = later[0]
        step = next(s for s in steps if int(s.get("step_no", 0)) == no)
        new_title = f"Step {no} target: {step.get('title', 'Project task')}"
        if str(r.get("title", "")) != new_title:
            r["title"] = new_title
            changed = True
        due = plan_map.get(str(no))
        if due and str(r.get("due_date", ""))[:10] != str(due)[:10]:
            r["due_date"] = due
            changed = True
        if str(no) in completed_nos and r.get("status") == "pending":
            r["status"] = "completed"
            r["message"] = f"Completed: {step.get('title', '')}"
            changed = True
    if changed:
        save_local_state()

def render_reminders_tab(project_id):
    st.markdown("## 🔔 Reminders")
    reminders = st.session_state.get("local_reminders", {}).get(str(project_id), [])
    pending = [r for r in reminders if r.get("status") == "pending"]
    completed = [r for r in reminders if r.get("status") == "completed"]
    updates = [r for r in reminders if r.get("status") == "info"]

    if st.session_state.get("last_email_status"):
        st.caption(st.session_state["last_email_status"])

    if not reminders:
        st.info("No reminders yet.")
        return

    m1, m2 = st.columns(2)
    m1.metric("Pending", len(pending))
    m2.metric("Completed", len(completed))

    if updates:
        st.markdown("#### 📌 Recent updates")
        for r in list(reversed(updates))[:3]:
            cls = "reminder-box info" if r.get("kind") != "idea" else "reminder-box idea"
            st.markdown(
                f"<div class='{cls}'><div class='reminder-title'>{r.get('title')}</div>"
                f"<div class='reminder-meta'>{r.get('message', '')}<br>Logged: {format_due_date(r.get('due_date'))}</div></div>",
                unsafe_allow_html=True,
            )

    if pending:
        st.markdown("#### ⏳ Step reminders (aligned with the 📍 Timeline)")
        for r in sorted(pending, key=lambda x: str(x.get("due_date", "")))[:6]:
            m = re.match(r"Step (\d+)", str(r.get("title", "")))
            no = int(m.group(1)) if m else None
            dot = f"<div class='timeline-dot dot-current'>{no}</div>" if no else "<div class='timeline-dot dot-locked'>⏰</div>"
            st.markdown(
                f"""
                <div class='timeline-item'>
                    {dot}
                    <div style='flex:1;'>
                        <div class='reminder-box' style='margin-bottom:0;'>
                            <div class='reminder-title'>{r.get('title')}</div>
                            <div class='reminder-meta'>{str(r.get('message', ''))[:140]}<br>Due: {format_due_date(r.get('due_date'))}</div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.success("All step reminders are completed. Great pace! 🎉")

def render_final_pack_tab(project, steps, project_id):
    st.markdown("## 🏆 Final Project Pack")
    st.caption("Unlocks after the whole roadmap is finished: report, viva questions, and ready-to-paste posts for GitHub, LinkedIn, Devpost and more.")

    packs = st.session_state.setdefault("local_final_packs", {})
    existing = packs.get(str(project_id))

    all_done = bool(steps) and all(s.get("status") == "completed" for s in steps)
    if not all_done:
        done = sum(1 for s in steps if s.get("status") == "completed")
        total = len(steps)
        st.warning(
            f"🔒 The Final Pack unlocks after you finish all roadmap steps — you're at {done}/{total}. "
            "Complete the current step in the 🧭 Roadmap tab (with proof) to keep going!"
        )
        return

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🎁 Generate / Refresh Final Pack", type="primary", use_container_width=True):
            with st.spinner("Building your final pack..."):
                packs[str(project_id)] = generate_final_pack(project, steps)
                save_local_state()
            existing = packs.get(str(project_id))
    with c2:
        if existing:
            report_text = "\n\n".join(str(existing.get(k, "")) for k in ["report", "viva", "github_lines", "linkedin_lines", "devpost_lines"])
            st.download_button(
                "⬇ Download Full Pack (txt)",
                data=report_text,
                file_name=f"final_pack_{str(project.get('title', 'project'))[:30].replace(' ', '_')}.txt",
                mime="text/plain",
                use_container_width=True,
            )

    if not existing:
        st.info("🎉 All steps done! Click 'Generate Final Pack' to build your report, viva prep, and share posts.")
        return

    st.markdown("### 📄 Project Report")
    st.markdown(existing.get("report", "No report generated."))

    st.markdown("### ❓ Viva Questions")
    st.markdown(existing.get("viva", "No viva questions generated."))

    st.markdown("### 🐙 GitHub README (ready to paste)")
    st.code(existing.get("github_lines", ""), language="markdown")

    st.markdown("### 💼 LinkedIn Post (ready to paste)")
    st.code(existing.get("linkedin_lines", ""), language="markdown")

    st.markdown("### 🏆 Devpost / Hackathon Description (ready to paste)")
    st.code(existing.get("devpost_lines", ""), language="markdown")

def show_workspace_page():
    project_id = st.session_state.get("active_project_id")
    project = st.session_state.get("active_project")
    if not project_id or not project:
        st.session_state["page"] = "projects"
        st.rerun()

    render_top_bar()

    st.markdown(f"<div class='workspace-title'>{project.get('title')}</div>", unsafe_allow_html=True)
    badges = (
        difficulty_badge_html(project.get("difficulty", "Intermediate"))
        + f'<span class="time-badge">⏱ {project.get("estimated_time") or project.get("duration") or ""}</span>'
        + f'<span class="domain-badge">{project.get("domain", "General")}</span>'
    )
    st.markdown(badges, unsafe_allow_html=True)

    steps = get_project_steps(project_id)
    try:
        sync_reminders_with_steps(project_id, steps)
    except Exception:
        pass
    done = sum(1 for s in steps if s.get("status") == "completed")
    progress = int((done / len(steps)) * 100) if steps else 0
    st.progress(progress)
    st.caption(f"Progress: {done}/{len(steps)} stages completed")

    tab_overview, tab_timeline, tab_roadmap, tab_chat, tab_reminders, tab_final = st.tabs(
        ["📌 Overview", "📍 Timeline", "🧭 Roadmap", "💬 Mentor Chat", "🔔 Reminders", "🏆 Final Pack"]
    )

    with tab_overview:
        st.markdown("### Project Overview")
        st.write(f"**Title:** {project.get('title', 'N/A')}")
        st.write(f"**Description:** {project.get('description', 'N/A')}")
        st.write(f"**Domain:** {project.get('domain', 'N/A')}")
        st.write(f"**Difficulty:** {project.get('difficulty', 'N/A')}")
        st.write(f"**Estimated duration:** {project.get('estimated_time') or project.get('duration') or 'N/A'}")
        st.write(f"**Skills:** {project.get('skills', 'N/A')}")
        idea_steps = [s for s in steps if s.get("origin") == "chat_idea"]
        if idea_steps:
            st.markdown("### 💡 Your mid-project ideas (added to roadmap)")
            for s in idea_steps:
                st.markdown(f"- **{s.get('title', '')}** — *AI verdict: {s.get('verdict', '')}*")

    with tab_timeline:
        render_timeline(steps, project_id)

    with tab_roadmap:
        st.caption("Gated roadmap: complete each checklist to unlock the next stage.")
        render_gated_roadmap(steps, project_id)

    with tab_chat:
        render_mentor_chat(project, steps, project_id)

    with tab_reminders:
        render_reminders_tab(project_id)

    with tab_final:
        render_final_pack_tab(project, steps, project_id)

# ======================================================
# ROUTING
# ======================================================
if not st.session_state["user"]:
    show_login_page()
elif st.session_state.get("page") == "projects":
    show_projects_page()
elif st.session_state.get("page") == "bookmarks":
    show_bookmarks_page()
elif st.session_state.get("page") == "workspace":
    show_workspace_page()
else:
    show_home_page()