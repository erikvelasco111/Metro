import streamlit as st
import os
import requests
import logging
import base64
import json
import random # 🚀 NUEVO: Para el simulador de cámaras
import googlemaps
import urllib.parse
import streamlit.components.v1 as components
import speech_recognition as sr
import io
from datetime import datetime 
from typing import Dict, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from streamlit_js_eval import get_geolocation
from streamlit_mic_recorder import mic_recorder

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Metro CDMX - Módulo Virtual", layout="wide", page_icon=None)

# --- 2. CONFIGURACIÓN DE ARCHIVOS ---
LOGO_PATH = "Logo_STC_METRO.svg" 
PLACEHOLDER_PATH = "espera.jpeg" 

# --- 3. HELPER PARA IMÁGENES ---
def get_image_src(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            b64_data = base64.b64encode(img_file.read()).decode()
            mime = "image/svg+xml" if image_path.endswith(".svg") else "image/png"
            return f"data:{mime};base64,{b64_data}"
    return ""

logo_src = get_image_src(LOGO_PATH) or "https://upload.wikimedia.org/wikipedia/commons/thumb/1/13/Metro_de_la_Ciudad_de_M%C3%A9xico_logo.svg/1200px-Metro_de_la_Ciudad_de_M%C3%A9xico_logo.svg.png"
placeholder_src = get_image_src(PLACEHOLDER_PATH)

# --- 4. ESTILOS CSS (METRO + KIOSCO TOUCH) ---
st.markdown(f"""
<style>
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header {{visibility: hidden;}}
    
    .stApp {{
        background-color: #f0f0f0;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    }}

    .metro-navbar {{
        background-color: #000000;
        height: 80px;
        width: 100%;
        display: flex;
        align-items: center;
        padding: 0 20px;
        border-bottom: 6px solid #F7931E; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        position: fixed;
        top: 0;
        left: 0;
        z-index: 99999;
    }}
    
    .metro-logo-img {{
        height: 50px;
        margin-right: 15px;
    }}
    
    .metro-title {{
        color: white;
        font-size: 24px;
        font-weight: bold;
        letter-spacing: 1px;
    }}

    .block-container {{
        padding-top: 6rem !important;
    }}

    .stChatInput {{
        border-color: #F7931E !important;
    }}
    
    /* 🚀 BOTONES DE MENÚ: CUADRADOS Y MASIVOS */
    div[data-testid="stVerticalBlock"] > div:has(button[key^="btn_"]) button {{
        width: 100% !important;
        aspect-ratio: 1 / 1 !important; /* Forza forma cuadrada */
        height: auto !important;
        border-radius: 30px !important;
        border: 4px solid #F7931E !important;
        background-color: #ffffff !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important;
        padding: 0 !important;
    }}
    
    div[data-testid="stVerticalBlock"] > div:has(button[key^="btn_"]) button:hover {{
        transform: translateY(-10px) scale(1.02) !important;
        border: 4px solid #000000 !important;
        box-shadow: 0 15px 30px rgba(0,0,0,0.15) !important;
    }}
    
    div[data-testid="stVerticalBlock"] > div:has(button[key^="btn_"]) button p {{
        font-size: 130px !important; /* Ícono Masivo */
        margin: 0 !important;
        line-height: 1 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }}
    
    /* BOTÓN DE RETROCESO */
    .btn-back div[data-testid="stButton"] button {{
        height: 60px;
        border-radius: 10px;
        border: 1px solid #ccc;
    }}
    .btn-back div[data-testid="stButton"] button p {{
        font-size: 30px !important;
    }}
</style>

<div class="metro-navbar">
    <img src="{logo_src}" class="metro-logo-img">
    <div class="metro-title">MÓDULO DE ATENCIÓN VIRTUAL</div>
</div>
""", unsafe_allow_html=True)

# --- LOGS & KEYS ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GOOGLE_API_KEY = st.secrets.get("GOOGLE_API_KEY")
DID_API_KEY = st.secrets.get("DID_API_KEY")
DID_AGENT_ID = st.secrets.get("DID_AGENT_ID")

try:
    gmaps = googlemaps.Client(key=GOOGLE_API_KEY)
except Exception:
    gmaps = None

MODOS = {
    "rutas": {
        "icon": "🗺️",
        "prompt": "Eres el experto en movilidad del Metro CDMX. Tu objetivo es guiar al usuario. Tienes la capacidad de mostrar mapas interactivos. Si te piden una ruta, DELEGA las indicaciones al mapa en pantalla.",
        "trigger": "Hola, necesito llegar a mi destino."
    },
    "mundial": {
        "icon": "⚽",
        "prompt": "Eres el guía oficial del Mundial 2026 en la CDMX. Proporcionas horarios y sedes. Si el usuario pregunta cómo llegar al estadio, activa el mapa.",
        "trigger": "Hola, busco información sobre los horarios de partidos y las sedes del mundial."
    },
    "turismo": {
        "icon": "🌮",
        "prompt": "Eres un guía turístico experto de la CDMX. Recomiendas lugares y restaurantes. Si el usuario quiere saber cómo llegar a tu recomendación, activa el mapa.",
        "trigger": "Hola, ¿qué restaurantes o lugares turísticos increíbles me recomiendas visitar hoy?"
    },
    "seguridad": {
        "icon": "🛡️",
        "prompt": "Eres el canal directo de participación ciudadana y seguridad del Metro. Ayudas al usuario a reportar incidentes. Transmites seguridad y empatía.",
        "trigger": "Hola, quiero reportar un incidente de seguridad o expresar mi opinión."
    }
}

def obtener_instrucciones_habladas(origen, destino):
    """Consulta la API de Google Maps con hora exacta para extraer una ruta narrada precisa."""
    if not gmaps:
        return "Te muestro la ruta en la pantalla."
    try:
        rutas = gmaps.directions(origen, destino, mode="transit", language="es", region="MX", departure_time=datetime.now())
        
        if not rutas:
            return "Aquí tienes la mejor ruta en el mapa."
        
        tiempo = rutas[0]['legs'][0]['duration']['text']
        pasos = rutas[0]['legs'][0]['steps']
        
        narrativa = f"El viaje tomará unos {tiempo}. "
        pasos_leidos = 0
        
        for paso in pasos:
            if paso['travel_mode'] == 'TRANSIT':
                pasos_leidos += 1
                detalles = paso['transit_details']
                linea = detalles['line'].get('short_name', detalles['line'].get('name', ''))
                vehiculo = detalles['line']['vehicle'].get('name', 'transporte')
                direccion = detalles.get('headsign', '')
                
                texto_paso = f"Toma el {vehiculo} línea {linea}"
                if direccion:
                    texto_paso += f" hacia {direccion}"
                narrativa += texto_paso + ". "
                
                if pasos_leidos >= 2:
                    narrativa += "Sigue los detalles de los transbordos en la pantalla."
                    break
                
        if pasos_leidos == 0:
             narrativa += "Por favor sigue las indicaciones de caminata en la pantalla."
             
        return narrativa
    except Exception as e:
        logger.error(f"Error sacando narrativa: {e}")
        return "Te muestro la ruta detallada en la pantalla."

# --- AGENTE ---
class DIDAgent:
    def __init__(self):
        self.did_api_key = DID_API_KEY
        self.google_api_key = GOOGLE_API_KEY
        self.agent_id = DID_AGENT_ID
        
        if not self.did_api_key or not self.agent_id:
            st.error("Error: Faltan credenciales.")
            st.stop()

        if not self.did_api_key.startswith("Basic"):
             api_key_encoded = base64.b64encode(self.did_api_key.encode("utf-8")).decode("utf-8")
             self.auth_header = f"Basic {api_key_encoded}"
        else:
             self.auth_header = self.did_api_key

        self.headers_did = {"Authorization": self.auth_header, "Content-Type": "application/json"}
        self.did_base_url = "https://api.d-id.com"
        
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", 
            google_api_key=self.google_api_key,
            temperature=0.1 
        )

    def create_stream(self) -> Dict:
        endpoint = f"agents/{self.agent_id}/streams"
        return self._make_did_request(endpoint, "POST")

    def send_text_to_stream(self, stream_id: str, session_id: str, text: str):
        endpoint = f"agents/{self.agent_id}/streams/{stream_id}"
        payload = {
            "script": {
                "type": "text", 
                "input": text, 
                "provider": {"type": "microsoft", "voice_id": "es-MX-JorgeNeural"}
            },
            "session_id": session_id 
        }
        self._make_did_request(endpoint, "POST", json_data=payload)

    def generate_response_with_context(self, query: str, context: str, user_location_info: str = "") -> dict:
        class ResponseStructure(BaseModel):
            responseText: str = Field(description="Respuesta hablada")
            mostrar_mapa: bool = Field(description="True SOLO si el usuario pide explícitamente cómo llegar a un lugar o una ruta.", default=False)
            origen: str = Field(description="Déjalo vacío. No lo extraigas.", default="")
            destino: str = Field(description="Lugar al que quiere ir el usuario.", default="")

        parser = JsonOutputParser(pydantic_object=ResponseStructure)

        prompt = ChatPromptTemplate.from_template(
            """
            {context}
            
            UBICACIÓN USUARIO: {location_info}
            PREGUNTA: {query}
            
            INSTRUCCIONES ESTRICTAS:
            - Sé breve, amable y directo (máx 30 palabras).
            - MULTILENGUAJE: Detecta el idioma en el que está escrita la "PREGUNTA" y responde SIEMPRE en ese mismo idioma de forma nativa.
            - MAPAS: Si la pregunta requiere dar direcciones de cómo llegar, pon 'mostrar_mapa' en true, y llena ÚNICAMENTE el 'destino'. 
            - Si muestras el mapa, tu 'responseText' SOLO debe decir que la ruta está en pantalla. NO des pasos verbales.
            - {format_instructions}
            """
        )
        chain = prompt | self.llm | parser
        try:
            return chain.invoke({
                "context": context, "query": query,
                "location_info": user_location_info,
                "format_instructions": parser.get_format_instructions()
            })
        except Exception:
            return {"responseText": "Lo siento, hay intermitencia en la red."}

    def transcribe_audio(self, audio_bytes: bytes) -> str:
        r = sr.Recognizer()
        try:
            audio_file = io.BytesIO(audio_bytes)
            with sr.AudioFile(audio_file) as source:
                audio_data = r.record(source)
                return r.recognize_google(audio_data, language="es-MX")
        except:
            return ""

    def _make_did_request(self, endpoint: str, method: str, json_data: Optional[Dict] = None) -> Dict:
        url = f"{self.did_base_url}/{endpoint}"
        try:
            response = requests.request(method, url, headers=self.headers_did, json=json_data, timeout=30)
            if response.status_code >= 400:
                logger.error(f"Error D-ID ({response.status_code}): {response.text}")
                return {"error": True, "details": response.text}
            response.raise_for_status()  
            return response.json()
        except Exception as e:
            logger.error(f"Excepción Request: {e}")
            return {"error": True, "details": str(e)}

# --- GPS Y SIMULADOR DE CÁMARAS (PILOTO DE SATURACIÓN) ---
def obtener_info_gps_silent():
    # ==========================================
    # CÓDIGO DEMO (BLOQUEADO EN METRO ZÓCALO)
    # ==========================================
    lat = 19.4326018
    lon = -99.1328416
    estacion = "Metro Zócalo"
    
    nivel_saturacion = random.randint(10, 95) 
    
    if nivel_saturacion >= 75: 
        semaforo = "🔴 Alta"
    elif nivel_saturacion >= 40: 
        semaforo = "🟡 Media"
    else: 
        semaforo = "🟢 Ágil"
        
    logger.info(f"[DEMO MODE] Cámara virtual en {estacion} detecta saturación del {nivel_saturacion}% ({semaforo})")
    return f"{lat},{lon} (Cerca de {estacion} | Semáforo: {semaforo})"

# --- JAVASCRIPT WEBRTC ---
def get_webrtc_js(stream_data, agent_id, did_api_key, placeholder_img_src):
    if not stream_data or "id" not in stream_data:
        return "<div style='color:red; text-align:center;'>Error: No hay señal de video.</div>"

    stream_id = stream_data['id']
    session_id = stream_data['session_id']
    offer = stream_data['offer']
    ice_servers = stream_data['ice_servers']
    
    if not did_api_key.startswith("Basic"):
        auth_val = "Basic " + base64.b64encode(did_api_key.encode("utf-8")).decode("utf-8")
    else:
        auth_val = did_api_key

    return f"""
    <style>
        body {{ margin: 0; display: flex; justify-content: center; background-color: transparent; }}
        .video-container {{ position: relative; width: 100%; max-width: 450px; height: 450px; background: #000; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.3); margin: 0 auto; }}
        #poster-layer {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; z-index: 2; transition: opacity 0.5s ease-in-out; opacity: 1; pointer-events: none; }}
        #talk-video {{ width: 100%; height: 100%; object-fit: cover; object-position: center top; z-index: 1; }}
    </style>
    <div class="video-container">
        <img id="poster-layer" src="{placeholder_img_src}">
        <video id="talk-video" autoplay playsinline></video>
    </div>
    <script>
    (async function() {{
        const videoElem = document.getElementById('talk-video');
        const posterElem = document.getElementById('poster-layer');
        try {{
            const peerConnection = new RTCPeerConnection({{ iceServers: {json.dumps(ice_servers)} }});
            peerConnection.ontrack = (event) => {{
                if (event.streams[0]) {{
                    videoElem.srcObject = event.streams[0];
                    videoElem.onloadeddata = () => {{ posterElem.style.opacity = '0'; videoElem.play(); }};
                }}
            }};
            peerConnection.onicecandidate = (event) => {{
                if (event.candidate) {{
                    fetch(`https://api.d-id.com/agents/{agent_id}/streams/{stream_id}/ice`, {{
                        method: 'POST', headers: {{ 'Authorization': '{auth_val}', 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ candidate: event.candidate.candidate, sdpMid: event.candidate.sdpMid, sdpMLineIndex: event.candidate.sdpMLineIndex, session_id: "{session_id}" }})
                    }});
                }}
            }};
            await peerConnection.setRemoteDescription({json.dumps(offer)});
            const answer = await peerConnection.createAnswer();
            await peerConnection.setLocalDescription(answer);
            await fetch(`https://api.d-id.com/agents/{agent_id}/streams/{stream_id}/sdp`, {{
                method: 'POST', headers: {{ 'Authorization': '{auth_val}', 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ answer: answer, session_id: "{session_id}" }})
            }});
        }} catch(e) {{ console.log(e); }}
    }})();
    </script>
    """

# --- INICIALIZACIÓN ---
if "did_agent" not in st.session_state: st.session_state.did_agent = DIDAgent()
if "active_mode" not in st.session_state: st.session_state.active_mode = None
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "intro_sent" not in st.session_state: st.session_state.intro_sent = False

location_context = obtener_info_gps_silent()

# --- LAYOUT PRINCIPAL ---
col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.markdown("")
    
    if "stream_data" in st.session_state and (not st.session_state.stream_data or "id" not in st.session_state.stream_data):
         del st.session_state.stream_data

    if "stream_data" not in st.session_state:
        if os.path.exists(PLACEHOLDER_PATH):
            c_ph1, c_ph2, c_ph3 = st.columns([1, 2, 1])
            with c_ph2: st.image(PLACEHOLDER_PATH) 
        else:
            st.info("Iniciando sistema...")
        
        try:
            data = st.session_state.did_agent.create_stream()
            if "error" in data or "id" not in data:
                error_msg = data.get("details", "Error desconocido de D-ID")
                st.error(f"⚠️ Error al crear stream: {error_msg}")
                if st.button("🔄 Reintentar"): st.rerun()
            else:
                st.session_state.stream_data = data
                st.rerun() 
        except Exception as e:
            st.error(f"Error crítico: {e}")
            if st.button("Reintentar"): st.rerun()
    else:
        html_code = get_webrtc_js(st.session_state.stream_data, DID_AGENT_ID, DID_API_KEY, placeholder_src)
        components.html(html_code, height=470)

# ==========================================================
# ADAPTACIÓN EN LA COLUMNA 2 (INTERFAZ VISUAL Y MULTILENGUAJE)
# ==========================================================
with col2:
    st.markdown("")
    
    if st.session_state.active_mode is None:
        with st.container():
            c_menu1, c_menu2 = st.columns(2)
            with c_menu1:
                if st.button(MODOS["rutas"]["icon"], use_container_width=True, key="btn_rutas"): st.session_state.active_mode = "rutas"; st.rerun()
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button(MODOS["turismo"]["icon"], use_container_width=True, key="btn_turismo"): st.session_state.active_mode = "turismo"; st.rerun()
            with c_menu2:
                if st.button(MODOS["mundial"]["icon"], use_container_width=True, key="btn_mundial"): st.session_state.active_mode = "mundial"; st.rerun()
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button(MODOS["seguridad"]["icon"], use_container_width=True, key="btn_seguridad"): st.session_state.active_mode = "seguridad"; st.rerun()

    else:
        modo_actual = MODOS[st.session_state.active_mode]
        
        c_back, c_icon, c_void = st.columns([1, 1, 3])
        with c_back:
            if st.button("🔙", key="btn_back"):
                st.session_state.active_mode = None
                st.session_state.intro_sent = False
                st.session_state.chat_history = []
                st.rerun()
        with c_icon:
            st.markdown(f"<h1 style='margin-top: -10px;'>{modo_actual['icon']}</h1>", unsafe_allow_html=True)
            
        st.divider()
        
        if not st.session_state.intro_sent and "stream_data" in st.session_state:
            with st.spinner("⏳"):
                resp = st.session_state.did_agent.generate_response_with_context(modo_actual["trigger"], modo_actual["prompt"], location_context)
                texto_resp = resp.get("responseText", "")
                if texto_resp:
                    st.session_state.did_agent.send_text_to_stream(st.session_state.stream_data["id"], st.session_state.stream_data["session_id"], texto_resp)
                    st.session_state.chat_history.append({"role": "assistant", "content": texto_resp})
                st.session_state.intro_sent = True

        with st.container(height=350, border=False):
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.write(msg["content"])
                    if msg.get("map_url"):
                        st.components.v1.iframe(msg["map_url"], height=300, scrolling=True)

        with st.container(border=True):
            c_mic, c_txt = st.columns([1, 4])
            with c_mic: audio_data = mic_recorder(start_prompt="🎤", stop_prompt="⏹️", key='recorder', format="wav", use_container_width=True)
            with c_txt: text_input = st.chat_input("💬")

        final_query = None

        if audio_data and ("last_audio_id" not in st.session_state or st.session_state.last_audio_id != audio_data['id']):
            st.session_state.last_audio_id = audio_data['id']
            with st.spinner("⏳"):
                texto = st.session_state.did_agent.transcribe_audio(audio_data['bytes'])
                if texto: final_query = texto
        elif text_input:
            final_query = text_input

        if final_query:
            if "stream_data" in st.session_state:
                st.session_state.chat_history.append({"role": "user", "content": final_query})
                
                with st.spinner("⏳ Procesando ruta precisa..."):
                    resp = st.session_state.did_agent.generate_response_with_context(final_query, modo_actual["prompt"], location_context)
                    texto_resp = resp.get("responseText", "Error de red")
                    map_url = None

                    if resp.get("mostrar_mapa") and resp.get("destino"):
                        origen_raw = "Zócalo, CDMX" 
                        destino_raw = resp.get("destino") + ", CDMX"

                        origen = urllib.parse.quote(origen_raw)
                        destino = urllib.parse.quote(destino_raw)
                        
                        map_url = f"https://www.google.com/maps/embed/v1/directions?key={GOOGLE_API_KEY}&origin={origen}&destination={destino}&mode=transit"
                        
                        instrucciones_reales = obtener_instrucciones_habladas(origen_raw, destino_raw)
                        
                        advertencia = ""
                        if "🔴 Alta" in location_context:
                            advertencia = "Precaución, el sistema de cámaras detecta saturación alta en tu estación de origen. "
                        elif "🟢 Ágil" in location_context:
                            advertencia = "El flujo en tu estación actual es ágil. "
                            
                        texto_resp = advertencia + instrucciones_reales

                    st.session_state.did_agent.send_text_to_stream(st.session_state.stream_data["id"], st.session_state.stream_data["session_id"], texto_resp)
                    st.session_state.chat_history.append({"role": "assistant", "content": texto_resp, "map_url": map_url})
                
                st.rerun()
            else:
                st.warning("⏳")
