import requests
import toml
import os

# 1. Intentamos leer las claves de tu archivo secrets.toml
try:
    secrets = toml.load(".streamlit/secrets.toml")
    DID_API_KEY = secrets.get("DID_API_KEY")
    DID_AGENT_ID = secrets.get("DID_AGENT_ID")
except Exception:
    print("⚠️ No pude leer .streamlit/secrets.toml automÃ¡ticamente.")
    DID_API_KEY = input("Pega tu DID_API_KEY aquÃ: ").strip()
    DID_AGENT_ID = input("Pega tu DID_AGENT_ID aquÃ: ").strip()

print(f"\n🕵️‍♂️ Probando credenciales para Agente: {DID_AGENT_ID}...")
print("-" * 50)

# Configurar Headers
headers = {
    "Authorization": f"Basic {DID_API_KEY}" if not DID_API_KEY.startswith("Basic") else DID_API_KEY,
    "Content-Type": "application/json"
}

# PRUEBA 1: Verificar si la API Key es válida (Consultando saldo/créditos)
# Nota: D-ID no tiene un endpoint directo de "créditos" público fácil, 
# pero intentaremos listar los agentes para ver si la llave abre la puerta.
url_agents = "https://api.d-id.com/agents"

try:
    response = requests.get(url_agents, headers=headers)
    
    if response.status_code == 200:
        print("✅ API KEY: Válida (Conexión exitosa).")
        agents_list = response.json().get("agents", [])
        
        # PRUEBA 2: Buscar tu Agente específico
        found = False
        print(f"\n📋 Tienes {len(agents_list)} agentes en tu cuenta:")
        for agent in agents_list:
            print(f"   - ID: {agent['id']} | Tipo: {agent.get('type', 'N/A')}")
            if agent['id'] == DID_AGENT_ID:
                found = True
        
        if found:
            print(f"\n✅ AGENT ID: Confirmado. El agente {DID_AGENT_ID} existe.")
        else:
            print(f"\n❌ AGENT ID: ERROR. El ID {DID_AGENT_ID} no aparece en tu lista.")
            print("   -> Solución: Copia uno de los IDs de la lista de arriba y ponlo en secrets.toml")
            
    elif response.status_code == 401:
        print("❌ ERROR 401: No autorizado. Tu API Key está mal o vencida.")
    elif response.status_code == 402:
        print("❌ ERROR 402: Sin créditos. Tu cuenta de prueba se agotó.")
    else:
        print(f"❌ Error desconocido: {response.status_code} - {response.text}")

except Exception as e:
    print(f"❌ Error de conexión: {e}")

print("-" * 50)

# PRUEBA 3: Intentar crear una sesión de Stream (Lo que falló en la app)
if 'found' in locals() and found:
    print("\n🎬 Intentando iniciar sesión de video (Create Stream)...")
    url_stream = f"https://api.d-id.com/agents/{DID_AGENT_ID}/streams"
    try:
        # Petición POST vacía para iniciar handshake
        resp_stream = requests.post(url_stream, headers=headers, json={})
        
        if resp_stream.status_code == 201:
            data = resp_stream.json()
            print("✅ STREAM: ¡Éxito! D-ID creó la sesión de video.")
            print(f"   - Session ID: {data.get('session_id')}")
            print("   -> Conclusión: El problema NO es tu cuenta, es el navegador o el JavaScript.")
        else:
            print(f"❌ STREAM FALLÓ: {resp_stream.status_code}")
            print(f"   - Razón: {resp_stream.text}")
    except Exception as e:
        print(f"❌ Error al crear stream: {e}")