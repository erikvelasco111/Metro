import requests
import json
import base64
import os
import toml

# --- 1. CONFIGURACIÓN ---
# Intentamos leer tus secretos automáticamente
try:
    secrets = toml.load(".streamlit/secrets.toml")
    DID_API_KEY = secrets.get("DID_API_KEY")
except:
    DID_API_KEY = "TU_CLAVE_AQUI_SI_FALLA_LA_LECTURA"

IMAGE_PATH = "agente.png"  # <--- Usaremos la imagen de espera como avatar por ahora
                           # Si tienes una foto de un conductor, cambia esto a "conductor.jpg"

# --- AUTH ---
if not DID_API_KEY:
    print("❌ Error: No se encontró la DID_API_KEY.")
    exit()

if not DID_API_KEY.startswith("Basic"):
    auth = "Basic " + base64.b64encode(DID_API_KEY.encode("utf-8")).decode("utf-8")
else:
    auth = DID_API_KEY

headers = {
    "Authorization": auth,
    "Content-Type": "application/json",
    "accept": "application/json"
}

def upload_image():
    print(f"📤 Subiendo {IMAGE_PATH} a D-ID...")
    url = "https://api.d-id.com/images"
    
    if not os.path.exists(IMAGE_PATH):
        print(f"❌ Error: No encuentro el archivo {IMAGE_PATH}")
        exit()

    with open(IMAGE_PATH, "rb") as img_file:
        files = {"image": (IMAGE_PATH, img_file, "image/png")}
        headers_upload = {"Authorization": auth} 
        response = requests.post(url, headers=headers_upload, files=files)
    
    if response.status_code == 201:
        img_url = response.json().get("url")
        print("✅ Imagen subida exitosamente.")
        return img_url
    else:
        print(f"❌ Error subiendo imagen: {response.text}")
        exit()

def create_agent(img_url):
    print("🤖 Creando el Agente (Configuración Actualizada)...")
    url = "https://api.d-id.com/agents"
    
    payload = {
        "presenter": {
            "type": "talk",
            "source_url": img_url,
            "thumbnail": img_url, # <--- CAMBIO IMPORTANTE: Ahora es obligatorio
            "voice": {
                "type": "microsoft",
                "voice_id": "es-MX-JorgeNeural" # Voz masculina de conductor
            }
        },
        "llm": {
            "type": "openai",
            "model": "gpt-4o-mini", # <--- CAMBIO IMPORTANTE: Modelo válido
            "instructions": "Eres un conductor experto del Metro CDMX."
        },
        "preview_name": "Conductor Metro CDMX"
    }
    
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 201:
        agent_data = response.json()
        agent_id = agent_data.get("id")
        print("\n" + "="*50)
        print("🎉 ¡AGENTE CREADO CON ÉXITO!")
        print("="*50)
        print(f"🆔 SU NUEVO AGENT ID ES: {agent_id}")
        print("="*50)
        print("\n👉 Copia ese ID y actualiza tu .streamlit/secrets.toml")
    else:
        print(f"❌ Error creando agente: {response.text}")

# --- EJECUCIÓN ---
if __name__ == "__main__":
    if not os.path.exists(IMAGE_PATH):
        print(f"⚠️  No encuentro '{IMAGE_PATH}'. Asegúrate de tener una imagen (jpg/png) en la carpeta.")
    else:
        url_imagen = upload_image()
        create_agent(url_imagen)