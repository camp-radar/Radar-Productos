"""
config.py — Claves de API, constantes y configuración inicial.
Lee las claves desde el archivo .env (en tu PC) o desde los Secrets de
Streamlit Cloud (cuando la app está en internet). Funciona en ambos lados.
No depende de ningún otro módulo del proyecto.
"""
import os

from dotenv import load_dotenv

# SSL / certificados (fix para Windows + Vertex/Gemini)
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("GRPC_DEFAULT_SSL_ROOTS_FILE_PATH", certifi.where())
    os.environ.setdefault("GOOGLE_API_USE_CLIENT_CERTIFICATE", "false")
except Exception:
    pass

import google.generativeai as genai

load_dotenv()


def _secreto(nombre, default=""):
    """Lee una clave desde variables de entorno (.env local) o desde los
    Secrets de Streamlit Cloud (nube). Devuelve default si no la encuentra."""
    val = os.getenv(nombre, "")
    if val:
        return val.strip()
    try:
        import streamlit as st
        if nombre in st.secrets:
            return str(st.secrets[nombre]).strip()
    except Exception:
        pass
    return default


# Puente: dejar las claves también como variables de entorno, para que los
# módulos que usan os.getenv (ia.py con GROQ, busqueda.py con SERPER) las
# encuentren igual cuando la app corre en la nube.
for _k in ["GEMINI_API_KEY", "GROQ_API_KEY", "SERPER_API_KEY", "GOOGLE_VISION_API_KEY"]:
    _v = _secreto(_k)
    if _v and not os.getenv(_k):
        os.environ[_k] = _v


GEMINI_API_KEY = _secreto("GEMINI_API_KEY")
GOOGLE_VISION_API_KEY = _secreto("GOOGLE_VISION_API_KEY")
SERPAPI_KEY = _secreto("SERPAPI_KEY")
IMGBB_API_KEY = _secreto("IMGBB_API_KEY")
GOOGLE_SHEET_ID = _secreto("GOOGLE_SHEET_ID", "1CtbBE7H1EGgTTDnYNZxHoWKGTxTrcGyXASyCIcPDxIE")

# --- Credenciales JSON de Google Vision (cuenta de servicio) ---
# En tu PC: busca el archivo .json en la carpeta.
# En la nube: lo reconstruye desde el secret GOOGLE_VISION_JSON_CONTENT
#             a un archivo temporal (nunca queda en GitHub).
_VISION_JSON_NAMES = [
    "radar-productos-1f389bcdec32.json",
    "service_account.json",
    "vision_credentials.json",
]
GOOGLE_VISION_JSON = ""
for _jname in _VISION_JSON_NAMES:
    _candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), _jname)
    if os.path.exists(_candidate):
        GOOGLE_VISION_JSON = _candidate
        break

if not GOOGLE_VISION_JSON:
    _json_content = _secreto("GOOGLE_VISION_JSON_CONTENT")
    if _json_content:
        import tempfile
        _tmp = os.path.join(tempfile.gettempdir(), "vision_creds.json")
        try:
            with open(_tmp, "w", encoding="utf-8") as _f:
                _f.write(_json_content)
            GOOGLE_VISION_JSON = _tmp
        except Exception:
            GOOGLE_VISION_JSON = ""

if not GOOGLE_VISION_JSON:
    GOOGLE_VISION_JSON = _secreto("GOOGLE_APPLICATION_CREDENTIALS")

VISION_DISPONIBLE = bool(GOOGLE_VISION_JSON or GOOGLE_VISION_API_KEY)

# Vertex desactivado por defecto (problema SSL gRPC en Windows con timeout de 600s)
VERTEX_HABILITADO = _secreto("VERTEX_HABILITADO", "false").lower() == "true"

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

GEMINI_MODELOS_FALLBACK = [
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-flash-lite-latest",
]
GROQ_MODELOS_FALLBACK = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "llama-3.1-8b-instant",
]


ZONAS_CHILE = {
    "Zona Norte": {
        "Arica y Parinacota": ["Arica"],
        "Tarapacá": ["Iquique", "Alto Hospicio"],
        "Antofagasta": ["Antofagasta", "Calama", "Tocopilla"],
        "Atacama": ["Copiapó", "Vallenar"],
        "Coquimbo": ["La Serena", "Coquimbo", "Ovalle"],
    },
    "Zona Centro": {
        "Región Metropolitana (Santiago)": ["Santiago"],
    },
}

# Objetivos de campaña de Meta Ads (el orden pone Ventas primero = por defecto).
OBJETIVOS_META = {
    "Ventas / Conversiones": "que las personas COMPREN el producto. Optimiza para conversiones de compra. Es el objetivo ideal para e-commerce que quiere cerrar ventas directas.",
    "Tráfico al sitio web": "llevar personas desde el anuncio hasta el sitio web o ficha del producto. Optimiza por clics en el enlace. Útil para dar a conocer un producto o alimentar retargeting.",
    "Interacción": "conseguir likes, comentarios, compartidos y engagement en la publicación. Útil para calentar audiencia y ganar prueba social, no para vender directo.",
    "Reconocimiento de marca": "que la mayor cantidad de personas vea y recuerde la marca. Optimiza por alcance/impresiones. Para dar a conocer un negocio nuevo.",
    "Clientes potenciales (Leads)": "capturar datos de contacto (formularios) de personas interesadas. Útil para servicios o productos de venta consultiva.",
}
