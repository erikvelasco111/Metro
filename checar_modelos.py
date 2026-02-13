import google.generativeai as genai
import os
from dotenv import load_dotenv

# Pon tu API Key directa aquí para probar rápido
API_KEY = "AIzaSyDb_JpMfcvir3PAnl_h30NlJE92QfpuRw8" 

genai.configure(api_key=API_KEY)

print("--- MODELOS DISPONIBLES PARA TI ---")
for m in genai.list_models():
  if 'generateContent' in m.supported_generation_methods:
    print(m.name)