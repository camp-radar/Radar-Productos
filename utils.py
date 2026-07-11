"""
utils.py — Helpers generales: texto, JSON, precios e imágenes.
No depende de otros módulos del proyecto.
"""
import re
import json
import statistics
from io import BytesIO

import requests
from PIL import Image
import numpy as np


STOPWORDS = {
    "de", "para", "con", "sin", "el", "la", "los", "las", "y", "en", "por",
    "un", "una", "unos", "unas", "a", "al", "del", "the", "and", "or", "of",
}


def formatear_pesos(valor):
    try:
        return f"${float(valor):,.0f}".replace(",", ".")
    except Exception:
        return "$0"


def safe_float(valor, default=0.0):
    try:
        if valor is None:
            return default
        if isinstance(valor, (int, float)):
            return float(valor)
        t = str(valor).strip().replace("$", "").replace("CLP", "").replace(".", "").replace(",", ".")
        return float(t)
    except Exception:
        return default


def resumir_texto(texto, max_chars=220):
    if not texto:
        return "-"
    texto = re.sub(r'([a-záéíóúñ])([A-ZÁÉÍÓÚÑ])', r'\1 \2', str(texto))
    limpio = " ".join(str(texto).split())
    if len(limpio) <= max_chars:
        return limpio
    return limpio[:max_chars].rsplit(" ", 1)[0] + "..."


def extraer_json_respuesta(texto):
    if not texto:
        return None
    # Quitar bloques markdown ```json ... ``` o ``` ... ```
    limpio = texto.strip()
    if limpio.startswith("```"):
        limpio = re.sub(r"^```(?:json)?\s*", "", limpio)
        limpio = re.sub(r"\s*```$", "", limpio)
    # Intento 1: parseo directo del texto limpio
    try:
        return json.loads(limpio)
    except Exception:
        pass
    # Intento 2: parseo del texto original
    try:
        return json.loads(texto)
    except Exception:
        pass
    # Intento 3: extraer el primer {...} con regex (greedy)
    match = re.search(r"\{.*\}", limpio, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return None


def normalizar_texto_match(texto: str) -> str:
    if not texto:
        return ""
    texto = texto.lower().replace("&", " ")
    texto = (texto.replace("á", "a").replace("é", "e").replace("í", "i")
                  .replace("ó", "o").replace("ú", "u").replace("ñ", "n"))
    texto = re.sub(r'([a-z0-9])-([a-z])\b', r'\1\2', texto)
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_consulta_usuario(texto: str) -> str:
    texto = texto.strip()
    texto = re.sub(r'\b(\d{1,4})\s+([a-zA-Z]{1})\b', r'\1\2', texto)
    return normalizar_texto_match(texto)


def tokenizar_producto(texto: str):
    tokens = normalizar_texto_match(texto).split()
    return [t for t in tokens if len(t) >= 2 and t not in STOPWORDS]


def limpiar_url(url: str) -> str:
    if not url:
        return ""
    try:
        from urllib.parse import urlparse, urlunparse
        return urlunparse(urlparse(url)._replace(fragment=""))
    except Exception:
        return url


def mediana_segura(valores):
    return statistics.median(valores) if valores else None


HEADERS_WEB = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
}


def descargar_imagen(url):
    try:
        r = requests.get(url, headers=HEADERS_WEB, timeout=10)
        if r.status_code != 200:
            return None
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:
        return None


def vector_simple_imagen(img, size=32):
    try:
        img = img.resize((size, size))
        return (np.array(img).astype("float32") / 255.0).flatten()
    except Exception:
        return None


def similitud_imagenes(img1, img2):
    v1 = vector_simple_imagen(img1)
    v2 = vector_simple_imagen(img2)
    if v1 is None or v2 is None:
        return 0
    norm = np.linalg.norm(v1) * np.linalg.norm(v2)
    return float(np.dot(v1, v2) / norm) if norm else 0
