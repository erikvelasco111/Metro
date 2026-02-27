import streamlit as st
import os
import requests
import logging
import base64
import random
import googlemaps
import urllib.parse
import streamlit.components.v1 as components
import speech_recognition as sr
import io
from datetime import datetime 
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from streamlit_mic_recorder import mic_recorder

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Metro CDMX - Módulo Virtual", layout="wide", page_icon=None)

# --- 2. CONFIGURACIÓN DE ARCHIVOS Y RUTAS ---
LOGO_PATH = "Logo_STC_METRO.svg" 
VIDEOS_DIR = "videos"
PLACEHOLDER_PATH = "espera.jpeg"

def get_image_src(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            b64_data = base64.b64encode(img_file.read()).decode()
            mime = "image/svg+xml" if image_path.endswith(".svg") else "image/png"
            return f"data:{mime};base64,{b64_data}"
    return ""

logo_src = get_image_src(LOGO_PATH) or "https://upload.wikimedia.org/wikipedia/commons/thumb/1/13/Metro_de_la_Ciudad_de_M%C3%A9xico_logo.svg/1200px-Metro_de_la_Ciudad_de_M%C3%A9xico_logo.svg.png"

# --- 3. ESTILOS CSS ---
st.markdown(f"""
<style>
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}
    .stApp {{ background-color: #f0f0f0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }}
    .metro-navbar {{ background-color: #000000; height: 80px; width: 100%; display: flex; align-items: center; padding: 0 20px; border-bottom: 6px solid #F7931E; box-shadow: 0 4px 6px rgba(0,0,0,0.1); position: fixed; top: 0; left: 0; z-index: 99999; }}
    .metro-logo-img {{ height: 50px; margin-right: 15px; }}
    .metro-title {{ color: white; font-size: 24px; font-weight: bold; letter-spacing: 1px; }}
    .block-container {{ padding-top: 6rem !important; }}
    .stChatInput {{ border-color: #F7931E !important; }}
</style>
<div class="metro-navbar">
    <img src="{logo_src}" class="metro-logo-img">
    <div class="metro-title">MÓDULO DE ATENCIÓN VIRTUAL</div>
</div>
""", unsafe_allow_html=True)

# --- 4. LOGS & KEYS ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GOOGLE_API_KEY = st.secrets.get("GOOGLE_API_KEY")
try:
    gmaps = googlemaps.Client(key=GOOGLE_API_KEY)
except Exception:
    gmaps = None

MODOS = {
    "rutas": {"icon": "🗺️", "video": f"{VIDEOS_DIR}/bienvenida_rutas.mp4"},
    "mundial": {"icon": "⚽", "video": f"{VIDEOS_DIR}/bienvenida_mundial.mp4"},
    "turismo": {"icon": "🌮", "video": f"{VIDEOS_DIR}/bienvenida_turismo.mp4"},
    "seguridad": {"icon": "🛡️", "video": f"{VIDEOS_DIR}/bienvenida_seguridad.mp4"}
}

# --- 5. GPS Y SIMULADOR DE CÁMARAS ---
def obtener_info_gps_silent():
    lat, lon, estacion = 19.4326018, -99.1328416, "Metro Zócalo"
    nivel = random.randint(10, 95) 
    semaforo = "🔴 Alta" if nivel >= 75 else ("🟡 Media" if nivel >= 40 else "🟢 Ágil")
    return f"{lat},{lon} (Cerca de {estacion} | Semáforo: {semaforo})"

location_context = obtener_info_gps_silent()

# --- 6. MOTOR "MAGO DE OZ" ---
class DemoAgent:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY, temperature=0)

    def transcribe_audio(self, audio_bytes: bytes) -> str:
        r = sr.Recognizer()
        try:
            audio_file = io.BytesIO(audio_bytes)
            with sr.AudioFile(audio_file) as source:
                return r.recognize_google(r.record(source), language="es-MX")
        except: return ""

    def clasificar_intencion(self, query: str) -> dict:
        prompt = ChatPromptTemplate.from_template(
            "Clasifica esta pregunta del usuario: '{query}'. "
            "Responde ÚNICAMENTE con una de estas 4 claves: "
            "1. 'azteca' (Si menciona estadio azteca o banorte). "
            "2. 'sudafrica' (Si menciona México, Sudáfrica o partido inaugural). "
            "3. 'restaurante' (Si busca comer, comida o restaurante). "
            "4. 'perdido' (Si menciona reporte, objeto perdido o robo). "
            "Si no es ninguna, responde 'otro'."
        )
        try:
            intencion = (prompt | self.llm).invoke({"query": query}).content.strip().lower()
            
            if "azteca" in intencion:
                return {"video": f"{VIDEOS_DIR}/resp_azteca.mp4", "destino": "Estadio Azteca", "texto": "Ruta al Estadio Azteca confirmada. Desde Zócalo, toma la Línea 2 hasta Tasqueña y ahí transborda al Tren Ligero hasta la estación Estadio Azteca. Ten en cuenta que hay saturación alta en esta estación, toma precauciones. Tu mapa está en pantalla."}
            elif "sudafrica" in intencion:
                return {"video": f"{VIDEOS_DIR}/resp_sudafrica.mp4", "destino": "Estadio Azteca", "texto": "¡El histórico partido inaugural! México contra Sudáfrica, juego uno del Grupo A. La cita es el jueves 11 de junio a las 15:00 horas en el imponente Estadio Azteca. Te dejo la ruta exacta aquí abajo."}
            elif "restaurante" in intencion:
                return {"video": f"{VIDEOS_DIR}/resp_restaurante.mp4", "destino": "Restaurante Balcón del Zócalo, Centro Histórico, CDMX", "texto": "¡Qué rico! El Centro Histórico tiene opciones increíbles como el Balcón del Zócalo. Te muestro en el mapa cómo llegar paso a paso para que disfrutes tu comida."}
            elif "perdido" in intencion:
                return {"video": f"{VIDEOS_DIR}/resp_perdido.mp4", "destino": None, "texto": "Lamento escuchar eso, entiendo la frustración. He registrado el reporte. Por favor, para contactar a la oficina de objetos extraviados dirígete a la jefatura y estación, ahí te apoyarán. Estamos para apoyarte."}
            else:
                return {"video": f"{VIDEOS_DIR}/idle.mp4", "destino": None, "texto": "No entendí bien, ¿puedes repetirlo?"}
        except:
            return {"video": f"{VIDEOS_DIR}/idle.mp4", "destino": None, "texto": "Error de conexión."}

    def traduccion_inteligente(self, texto: str, query: str) -> str:
        prompt = ChatPromptTemplate.from_template("Traduce sin explicaciones extras: '{texto}' al idioma de '{query}'.")
        try: return (prompt | self.llm).invoke({"texto": texto, "query": query}).content.strip()
        except: return texto

# --- INICIALIZACIÓN ---
if "demo_agent" not in st.session_state: st.session_state.demo_agent = DemoAgent()
if "active_mode" not in st.session_state: st.session_state.active_mode = None
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "current_video" not in st.session_state: st.session_state.current_video = f"{VIDEOS_DIR}/idle.mp4"


# --- LAYOUT PRINCIPAL (Menú Izquierda [2], Avatar Derecha [1]) ---
col1, col2 = st.columns([2, 1], gap="large")

with col1:
    st.markdown("")

    if st.session_state.active_mode is None:
        # MENÚ PRINCIPAL MASIVO
        st.markdown("""
        <style>
            div[data-testid="stButton"] button { width: 100% !important; aspect-ratio: 1 / 1 !important; height: auto !important; border-radius: 30px !important; border: 4px solid #F7931E !important; background-color: #ffffff !important; transition: transform 0.2s !important; }
            div[data-testid="stButton"] button:hover { transform: scale(1.05) !important; border: 4px solid #000000 !important; box-shadow: 0 15px 30px rgba(0,0,0,0.15) !important; }
            div[data-testid="stButton"] button p, div[data-testid="stButton"] button div { font-size: 102px !important; margin: 0 !important; line-height: 1 !important; display: flex !important; align-items: center !important; justify-content: center !important; }
        </style>
        """, unsafe_allow_html=True)

        st.markdown("<h2 style='text-align: center; color: #333; margin-bottom: 30px;'>👆 Toca una opción para comenzar:</h2>", unsafe_allow_html=True)
        
        col_rutas, col_turismo, col_mundial, col_seguridad = st.columns(4, gap="medium")
        
        with col_rutas:
            if st.button(MODOS["rutas"]["icon"], use_container_width=True): 
                st.session_state.active_mode = "rutas"
                st.session_state.current_video = MODOS["rutas"]["video"]
                st.rerun()
            st.markdown("<h3 style='text-align: center; margin-top: 10px; color: #555;'>Mapas y rutas</h3>", unsafe_allow_html=True)
                
        with col_turismo:
            if st.button(MODOS["turismo"]["icon"], use_container_width=True): 
                st.session_state.active_mode = "turismo"
                st.session_state.current_video = MODOS["turismo"]["video"]
                st.rerun()
            st.markdown("<h3 style='text-align: center; margin-top: 10px; color: #555;'>Puntos de interés</h3>", unsafe_allow_html=True)
                
        with col_mundial:
            if st.button(MODOS["mundial"]["icon"], use_container_width=True): 
                st.session_state.active_mode = "mundial"
                st.session_state.current_video = MODOS["mundial"]["video"]
                st.rerun()
            st.markdown("<h3 style='text-align: center; margin-top: 10px; color: #555;'>Horarios y sedes</h3>", unsafe_allow_html=True)
                
        with col_seguridad:
            if st.button(MODOS["seguridad"]["icon"], use_container_width=True): 
                st.session_state.active_mode = "seguridad"
                st.session_state.current_video = MODOS["seguridad"]["video"]
                st.rerun()
            st.markdown("<h3 style='text-align: center; margin-top: 10px; color: #555;'>Seguridad</h3>", unsafe_allow_html=True)

    else:
        modo_actual = MODOS[st.session_state.active_mode]
        c_back, c_icon, c_void = st.columns([1, 1, 3])
        with c_back:
            # CSS para hacer grande el botón de regresar
            st.markdown("""
            <style>
            div[data-testid="column"]:first-child button { height: 70px !important; border-radius: 15px !important; font-size: 24px !important; font-weight: bold !important; border: 2px solid #ccc !important; }
            </style>
            """, unsafe_allow_html=True)
            
            if st.button("🔙 Regresar", key="btn_back", use_container_width=True):
                st.session_state.active_mode = None
                st.session_state.chat_history = []
                st.session_state.current_video = f"{VIDEOS_DIR}/idle.mp4"
                st.rerun()
        with c_icon:
            st.markdown(f"<h1 style='margin-top: -10px; font-size: 60px;'>{modo_actual['icon']}</h1>", unsafe_allow_html=True)
            
        st.divider()

        with st.container(height=280, border=False):
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.write(msg["content"])
                    if msg.get("map_url"):
                        st.components.v1.iframe(msg["map_url"], height=300, scrolling=True)
                        if msg.get("qr_url"):
                            c_qr, c_texto = st.columns([1, 3])
                            with c_qr: st.image(msg["qr_url"], width=120)
                            with c_texto: st.info("📱 **Escanea este código** para llevarte la ruta a tu celular.")

        with st.container(border=True):
            c_mic, c_txt = st.columns([1, 4])
            with c_mic: audio_data = mic_recorder(start_prompt="🎤 Hablar", stop_prompt="⏹️ Detener", key='recorder', format="wav", use_container_width=True)
            with c_txt: text_input = st.chat_input("Escribe tu duda aquí...")

        final_query = None
        if audio_data and ("last_audio_id" not in st.session_state or st.session_state.last_audio_id != audio_data['id']):
            st.session_state.last_audio_id = audio_data['id']
            with st.spinner("⏳"):
                texto = st.session_state.demo_agent.transcribe_audio(audio_data['bytes'])
                if texto: final_query = texto
        elif text_input:
            final_query = text_input

        if final_query:
            st.session_state.chat_history.append({"role": "user", "content": final_query})
            with st.spinner("⏳"):
                analisis = st.session_state.demo_agent.clasificar_intencion(final_query)
                st.session_state.current_video = analisis["video"]
                
                texto_resp = analisis["texto"]
                map_url = None
                qr_url = None

                if analisis["destino"]:
                    origen_raw = "Zócalo, CDMX" 
                    origen, destino = urllib.parse.quote(origen_raw), urllib.parse.quote(analisis["destino"])
                    map_url = f"https://www.google.com/maps/embed/v1/directions?key={GOOGLE_API_KEY}&origin={origen}&destination={destino}&mode=transit"
                    mobile_url = f"https://www.google.com/maps/dir/?api=1&origin={origen}&destination={destino}&travelmode=transit"
                    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(mobile_url)}"
                    
                    texto_preparado = ("Precaución, saturación alta. " if "🔴 Alta" in location_context else "") + texto_resp
                    texto_resp = st.session_state.demo_agent.traduccion_inteligente(texto_preparado, final_query)

                st.session_state.chat_history.append({"role": "assistant", "content": texto_resp, "map_url": map_url, "qr_url": qr_url})
            st.rerun()

with col2:
    st.markdown("")
    video_path = st.session_state.current_video
    idle_path = f"{VIDEOS_DIR}/idle.mp4"
    
    if os.path.exists(video_path) and os.path.exists(idle_path):
        with open(video_path, "rb") as f:
            b64_current = base64.b64encode(f.read()).decode()
        with open(idle_path, "rb") as f:
            b64_idle = base64.b64encode(f.read()).decode()

        is_idle = "idle" in video_path

        if is_idle:
            html_code = f"""
            <style>body {{ margin: 0; background: transparent; display: flex; justify-content: center; }}</style>
            <video autoplay loop muted playsinline style="width: 100%; max-width: 450px; aspect-ratio: 1/1; border-radius: 30px; border: 4px solid #F7931E; box-shadow: 0 10px 25px rgba(0,0,0,0.3); background-color: #000; object-fit: cover; pointer-events: none;">
                <source src="data:video/mp4;base64,{b64_idle}" type="video/mp4">
            </video>
            """
        else:
            html_code = f"""
            <style>body {{ margin: 0; background: transparent; display: flex; justify-content: center; }}</style>
            <div style="position: relative; width: 100%; max-width: 450px; aspect-ratio: 1/1; border-radius: 30px; border: 4px solid #F7931E; box-shadow: 0 10px 25px rgba(0,0,0,0.3); overflow: hidden; background-color: #000; pointer-events: none;">
                
                <video autoplay loop muted playsinline style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; z-index: 1;">
                    <source src="data:video/mp4;base64,{b64_idle}" type="video/mp4">
                </video>
                
                <video id="talk-vid" autoplay playsinline style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; z-index: 2; transition: opacity 0.4s ease-out;">
                    <source src="data:video/mp4;base64,{b64_current}" type="video/mp4">
                </video>
            </div>
            
            <script>
                document.getElementById('talk-vid').onended = function() {{
                    this.style.opacity = '0';
                }};
            </script>
            """
        
        components.html(html_code, height=480)
        
    else:
        if os.path.exists(PLACEHOLDER_PATH):
            st.image(PLACEHOLDER_PATH, use_container_width=True)
        st.warning(f"⚠️ Faltan videos. Verifica que existan en la carpeta '{VIDEOS_DIR}'")
