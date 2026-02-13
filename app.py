import streamlit as st
import os
import requests
import logging
import base64
import json
import googlemaps
import streamlit.components.v1 as components
import speech_recognition as sr
import io
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

# --- 4. ESTILOS CSS (METRO) ---
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
            temperature=0.3
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

        parser = JsonOutputParser(pydantic_object=ResponseStructure)

        prompt = ChatPromptTemplate.from_template(
            """
            Eres un asistente oficial del Metro CDMX.
            UBICACIÓN USUARIO: {location_info}
            CONTEXTO: {context}
            PREGUNTA: {query}
            INSTRUCCIONES:
            - Sé breve, amable y directo (máx 25 palabras).
            - Si sabes dónde está el usuario, indícale la estación más cercana.
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
            
            # --- DEBUGGING: Captura error real de D-ID ---
            if response.status_code >= 400:
                logger.error(f"Error D-ID ({response.status_code}): {response.text}")
                return {"error": True, "details": response.text}
                
            response.raise_for_status()  
            return response.json()
        except Exception as e:
            logger.error(f"Excepción Request: {e}")
            return {"error": True, "details": str(e)}

# --- GPS ---
def obtener_info_gps_silent():
    loc = get_geolocation()
    if loc:
        lat = loc['coords']['latitude']
        lon = loc['coords']['longitude']
        info_basica = f"Coordenadas: {lat}, {lon}."
        if gmaps:
            try:
                lugares = gmaps.places_nearby(location=(lat, lon), radius=1000, type='subway_station')
                if lugares.get('results'):
                    estacion = lugares['results'][0]['name']
                    return f"El usuario está en Lat:{lat}, Lon:{lon}. Estación cercana: {estacion}."
            except:
                pass
        return info_basica
    return "Ubicación desconocida."

# --- JAVASCRIPT WEBRTC (REDIMENSIONADO Y CENTRADO) ---
def get_webrtc_js(stream_data, agent_id, did_api_key, placeholder_img_src):
    # --- VALIDACIÓN DE SEGURIDAD ---
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

    # CAMBIOS CSS: 
    # 1. 'display: flex' y 'justify-content: center' en el body para centrar el div.
    # 2. 'max-width: 450px' y 'height: 450px' para hacer el video cuadrado y no enorme.
    # 3. 'margin: 0 auto' para centrar el bloque.
    return f"""
    <style>
        body {{
            margin: 0;
            display: flex;
            justify-content: center;
            background-color: transparent;
        }}
        .video-container {{ 
            position: relative; 
            width: 100%;
            max-width: 450px; /* Ancho máximo limitado */
            height: 450px;    /* Altura fija cuadrada */
            background: #000; 
            border-radius: 20px; 
            overflow: hidden; 
            box-shadow: 0 10px 25px rgba(0,0,0,0.3);
            margin: 0 auto; /* Centrado horizontal */
        }}
        
        #poster-layer {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
            z-index: 2;
            transition: opacity 0.5s ease-in-out;
            opacity: 1;
            pointer-events: none;
        }}
        
        #talk-video {{
            width: 100%;
            height: 100%;
            object-fit: cover; /* Cubre el cuadro sin deformar */
            object-position: center top; /* Enfoca la cara, no el pecho */
            z-index: 1;
        }}
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
                    videoElem.onloadeddata = () => {{
                        console.log("Stream listo, ocultando poster...");
                        posterElem.style.opacity = '0';
                        videoElem.play();
                    }};
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
if "did_agent" not in st.session_state:
    st.session_state.did_agent = DIDAgent()

location_context = obtener_info_gps_silent()

# --- LAYOUT PRINCIPAL ---
col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.markdown("### Enlace de Video")
    
    # 1. ¿Hay Stream Activo?
    if "stream_data" not in st.session_state:
        if os.path.exists(PLACEHOLDER_PATH):
            col_ph1, col_ph2, col_ph3 = st.columns([1, 2, 1])
            with col_ph2:
                # Modificado para evitar el warning de use_container_width
                st.image(PLACEHOLDER_PATH) 
        else:
            st.info("Iniciando sistema...")
        
        try:
            data = st.session_state.did_agent.create_stream()
            
            # --- VALIDACIÓN DE RESPUESTA ---
            if "error" in data or "id" not in data:
                error_msg = data.get("details", "Error desconocido de D-ID")
                st.error(f"⚠️ Error al crear stream: {error_msg}")
                if st.button("🔄 Reintentar"):
                    st.rerun()
            else:
                st.session_state.stream_data = data
                st.rerun() 
        except Exception as e:
            st.error(f"Error crítico: {e}")
            if st.button("Reintentar"):
                st.rerun()
    
    else:
        # Renderizado del video
        html_code = get_webrtc_js(
            st.session_state.stream_data, 
            DID_AGENT_ID, 
            DID_API_KEY, 
            placeholder_src
        )
        components.html(html_code, height=470)

with col2:
    st.markdown("### Atención al Usuario")
    
    with st.container(border=True):
        c_mic, c_txt = st.columns([1, 4])
        with c_mic:
            audio_data = mic_recorder(
                start_prompt="Hablar",
                stop_prompt="Enviar",
                key='recorder',
                format="wav",
                use_container_width=True
            )
        with c_txt:
             st.write("**Presiona para hablar**")
             st.caption("Suelta para enviar consulta")

        text_input = st.chat_input("Escribe tu duda aquí...")

    final_query = None

    if audio_data:
        if "last_audio_id" not in st.session_state or st.session_state.last_audio_id != audio_data['id']:
            st.session_state.last_audio_id = audio_data['id']
            with st.spinner("Procesando voz..."):
                texto = st.session_state.did_agent.transcribe_audio(audio_data['bytes'])
                if texto:
                    final_query = texto
                    st.success(f"Reconocido: {texto}")
                else:
                    st.warning("No se entendió el audio.")

    elif text_input:
        final_query = text_input

    if final_query:
        if "stream_data" in st.session_state:
            if "last_query" not in st.session_state or st.session_state.last_query != final_query:
                st.session_state.last_query = final_query
                
                with st.chat_message("user"):
                    st.write(final_query)
                
                with st.spinner("Consultando..."):
                    resp = st.session_state.did_agent.generate_response_with_context(
                        final_query, 
                        "El boleto cuesta $5. Horario: 5:00 a 24:00.",
                        user_location_info=location_context
                    )
                    texto_resp = resp.get("responseText", "Error de red")
                    
                    st.session_state.did_agent.send_text_to_stream(
                        st.session_state.stream_data["id"],
                        st.session_state.stream_data["session_id"],
                        texto_resp
                    )
                
                with st.chat_message("assistant"):
                    st.write(texto_resp)
        else:
            st.warning("El agente se está conectando...")