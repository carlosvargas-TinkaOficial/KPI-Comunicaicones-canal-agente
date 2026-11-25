import streamlit as st
import os
import requests
import io
import time
import hmac
import importlib

# Importación de módulos independientes
import inasistencias
import pozos

# Forzar recarga dinámica de submódulos
importlib.reload(inasistencias)
importlib.reload(pozos)

st.set_page_config(page_title="La Tinka - Portal Canal Agente", layout="wide", initial_sidebar_state="expanded")

# --- INYECCIÓN CSS: IDENTIDAD CORPORATIVA Y BOTONES TÁCTILES ---
st.markdown("""
<style>
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] { background-color: #F5F0D4 !important; color: #000000 !important; }
    p, label, span, div { color: #000000 !important; }
    h1, h2, h3, h4, h5, h6 { color: #096045 !important; font-weight: 800 !important; }
    label[data-testid="stWidgetLabel"] p { color: #096045 !important; font-weight: bold !important; font-size: 1.05rem !important; }
    div[data-baseweb="select"] > div { background-color: #FFFFFF !important; border: 2px solid #096045 !important; border-radius: 8px !important; color: #000000 !important; }
    div[data-baseweb="select"] * { color: #000000 !important; background-color: #FFFFFF !important; }
    [data-baseweb="popover"], [data-baseweb="menu"], ul[role="listbox"], li[role="option"] { background-color: #FFFFFF !important; color: #000000 !important; }
    li[role="option"] * { color: #000000 !important; background-color: #FFFFFF !important; }
    li[role="option"]:hover, li[role="option"][aria-selected="true"] { background-color: #F5F0D4 !important; }
    li[role="option"]:hover *, li[role="option"][aria-selected="true"] * { color: #096045 !important; background-color: #F5F0D4 !important; font-weight: bold !important; }
    
    /* Botones de navegación tipo Tarjeta Táctil para Celulares */
    div[data-testid="stRadio"] > label { font-weight: bold !important; color: #096045 !important; font-size: 1.1rem !important; }
    div[data-testid="stRadio"] div[role="radiogroup"] > label {
        background-color: #FFFFFF !important;
        padding: 12px 14px !important;
        border-radius: 10px !important;
        border: 2px solid #096045 !important;
        margin-bottom: 8px !important;
        width: 100% !important;
        box-shadow: 0px 2px 4px rgba(0,0,0,0.06);
    }
    div[data-testid="stRadio"] div[role="radiogroup"] > label:hover {
        background-color: #F5F0D4 !important;
    }

    [data-testid="stMetric"] { background-color: #FFFFFF !important; padding: 12px 16px !important; border-radius: 10px !important; border-left: 6px solid #096045 !important; box-shadow: 0px 2px 6px rgba(0,0,0,0.08); }
    [data-testid="stMetricLabel"] p { color: #096045 !important; font-weight: bold !important; }
    [data-testid="stMetricValue"] div { color: #000000 !important; font-weight: 800 !important; }
    div[data-testid="stExpander"] { background-color: #FFFFFF !important; border: 2px solid #096045 !important; border-radius: 10px !important; }
    div[data-testid="stExpander"] summary p { color: #096045 !important; font-weight: bold !important; font-size: 1.05rem !important; }
    div.stButton > button, div.stDownloadButton > button, div.stButton > button *, div.stDownloadButton > button * { background-color: #096045 !important; color: #FFFFFF !important; border-radius: 8px !important; border: none !important; font-weight: 800 !important; font-size: 1rem !important; margin-bottom: 4px !important; }
    div.stButton > button:hover, div.stDownloadButton > button:hover, div.stButton > button:hover *, div.stDownloadButton > button:hover * { background-color: #FF6700 !important; color: #FFFFFF !important; }
    [data-testid="stDataFrame"] { background-color: #FFFFFF !important; border: 1px solid #096045 !important; border-radius: 8px !important; }
</style>
""", unsafe_allow_html=True)

# --- CONFIGURACIÓN DE SEGURIDAD Y TIEMPOS ---
PASSWORD_CORRECTA = st.secrets.get("APP_PASSWORD", "Tinka123")
MAX_INTENTOS = 3
TIEMPO_BLOQUEO_SEG = 300
TIEMPO_INACTIVIDAD_SEG = 3600

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
if "intentos_fallidos" not in st.session_state:
    st.session_state["intentos_fallidos"] = 0
if "tiempo_bloqueo" not in st.session_state:
    st.session_state["tiempo_bloqueo"] = 0
if "ultimo_acceso" not in st.session_state:
    st.session_state["ultimo_acceso"] = time.time()

# --- CONTROL DE INACTIVIDAD DE SESIÓN ---
if st.session_state["autenticado"]:
    tiempo_transcurrido = time.time() - st.session_state["ultimo_acceso"]
    if tiempo_transcurrido > TIEMPO_INACTIVIDAD_SEG:
        st.session_state["autenticado"] = False
        st.warning("⚠️ Tu sesión ha expirado por inactividad (60 min). Ingresa nuevamente.")
        st.rerun()
    else:
        st.session_state["ultimo_acceso"] = time.time()

# --- PANTALLA DE CONTROL DE ACCESO CON RATE LIMITING ---
if not st.session_state["autenticado"]:
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if os.path.exists("logo.png"):
            st.image("logo.png", width=220)
        st.title("🔒 Acceso Restringido")
        st.subheader("Portal Comercial - Canal Agente")
        st.write("Por favor, ingresa la clave de autorización para acceder:")

        tiempo_restante = st.session_state["tiempo_bloqueo"] - time.time
