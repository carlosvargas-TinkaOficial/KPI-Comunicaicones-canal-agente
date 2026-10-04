import streamlit as st
import os
import requests
import io

# Importación de módulos independientes
import inasistencias
import nps

st.set_page_config(page_title="La Tinka - Portal Canal Agente", layout="wide", initial_sidebar_state="expanded")

# --- INYECCIÓN CSS: IDENTIDAD CORPORATIVA ---
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

# --- PANTALLA DE CONTROL DE ACCESO (FASE 1) ---
PASSWORD_CORRECTA = st.secrets.get("APP_PASSWORD", "Tinka2026*")

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if os.path.exists("logo.png"):
            st.image("logo.png", width=220)
        st.title("🔒 Acceso Restringido")
        st.subheader("Portal Comercial - Canal Agente")
        st.write("Por favor, ingresa la clave de autorización para acceder:")
        
        clave_ingresada = st.text_input("Contraseña de Acceso:", type="password", key="pwd_input")
        if st.button("🚀 Ingresar al Portal", type="primary"):
            if clave_ingresada == PASSWORD_CORRECTA:
                st.session_state["autenticado"] = True
                st.rerun()
            else:
                st.error("🔑 Contraseña incorrecta. Acceso denegado.")
    # Detiene la ejecución aquí: no se descargan datos de Google Drive ni se procesan módulos si no hay autenticación
    st.stop()

# --- AUTENTICACIÓN Y CONFIGURACIÓN ---
api_key = st.secrets.get("GEMINI_API_KEY", None)
url_inas = st.secrets.get("URL_INASISTENCIAS", None)
url_nps = st.secrets.get("URL_NPS", None)

st.sidebar.title("📌 Canal Agente")
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", width=180)

modulo_seleccionado = st.sidebar.radio(
    "Selecciona la herramienta:",
    ["1. Copiloto IA (Inasistencias)", "2. Avance Mensual NPS"]
)

st.sidebar.divider()
st.sidebar.header("⚙️ Configuración")
if not api_key:
    api_key = st.sidebar.text_input("Gemini API Key (AQ...)", type="password")

if st.sidebar.button("🔒 Cerrar Sesión"):
    st.session_state["autenticado"] = False
    st.rerun()

# --- FUNCIÓN DE CARGA BLINDADA ---
@st.cache_data(ttl=300)
def cargar_excel_drive(url):
    if not url:
        return None
    try:
        response = requests.get(url, timeout=(5, 30), allow_redirects=True)
        response.raise_for_status()
        return io.BytesIO(response.content)
    except Exception:
        return None

# --- ENRUTADOR PRINCIPAL ---
if modulo_seleccionado == "1. Copiloto IA (Inasistencias)":
    bytes_m1 = cargar_excel_drive(url_inas)
    inasistencias.mostrar_modulo(api_key, bytes_m1) 

elif modulo_seleccionado == "2. Avance Mensual NPS":
    bytes_m2 = cargar_excel_drive(url_nps)
    nps.mostrar_modulo(api_key, bytes_m2)
