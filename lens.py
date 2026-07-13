"""
lens.py — MÓDULO LENS (búsqueda visual del producto EXACTO)
-----------------------------------------------------------
Complementa la detección por imagen de vision.py. Mientras vision.py convierte
la imagen en texto y busca "productos similares", este módulo usa Google Lens
(vía SerpApi) para encontrar el MISMO producto en tiendas reales, con precio.

Flujo: imagen -> se sube a ImgBB (URL pública) -> Google Lens apuntando a Chile
-> se filtran tiendas chilenas, se ordenan por precio y se descartan outliers.

Entrada principal:
    buscar_por_imagen_lens(image_bytes) -> dict con "productos" y "resumen_precios"
"""

import re
import base64
from io import BytesIO
from urllib.parse import urlparse

import requests
from PIL import Image

from ia import _gemini_generate
from utils import extraer_json_respuesta

# Llaves: se toman de config (que funciona en local vía .env y en la nube vía
# Streamlit Secrets). Fallback a variables de entorno por si config aún no las
# expone, para no romper pruebas locales.
try:
    from config import SERPAPI_KEY, IMGBB_API_KEY, GEMINI_API_KEY
except Exception:
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
    IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


# Interruptor del filtro de similitud con Gemini: en False, buscar_por_imagen_lens
# funciona exactamente igual que antes (solo orden por precio). Poner en False
# para revertir rápido si el filtro da problemas.
USAR_FILTRO_GEMINI = True


# ==============================================================================
# LLAMADAS A LOS SERVICIOS (probadas en test_lens.py)
# ==============================================================================

def subir_a_imgbb(api_key: str, imagen_bytes: bytes, expiracion: int = 600) -> str:
    """Sube la imagen a ImgBB y devuelve una URL pública temporal."""
    b64 = base64.b64encode(imagen_bytes).decode("utf-8")
    resp = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": api_key, "image": b64, "expiration": expiracion},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"ImgBB no aceptó la imagen: {data}")
    return data["data"]["url"]


def buscar_en_lens(api_key: str, imagen_url: str, pais: str = "cl",
                   idioma: str = "es") -> dict:
    """Llama a Google Lens (vía SerpApi) con la URL de la imagen."""
    resp = requests.get(
        "https://serpapi.com/search",
        params={
            "engine": "google_lens",
            "url": imagen_url,
            "country": pais,
            "hl": idioma,
            "api_key": api_key,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


# ==============================================================================
# LÓGICA (filtro chileno, precio, orden, outliers)
# ==============================================================================

# Tiendas chilenas conocidas cuyo dominio no siempre termina en .cl
TIENDAS_CL = (
    "falabella", "ripley", "paris", "sodimac", "lider", "hites", "abcdin",
    "corona", "easy", "pcfactory", "spdigital", "linio", "dafiti", "casaideas",
)


def _es_chileno(link: str, fuente: str) -> bool:
    link = (link or "").lower()
    fuente = (fuente or "").lower()
    try:
        dominio = urlparse(link).netloc.lower()
    except Exception:
        dominio = ""
    if dominio.endswith(".cl"):
        return True
    if "mercadolibre.cl" in link:  # ML Chile (no confundir con .com.ar)
        return True
    return any(t in dominio or t in fuente for t in TIENDAS_CL)


def _precio_a_numero(precio_raw):
    """SerpApi manda el precio como dict {value, extracted_value, currency}
    (a veces como texto). Devuelve (texto_legible, numero_o_None)."""
    if isinstance(precio_raw, dict):
        texto = (precio_raw.get("value") or "").replace("*", "").strip()
        num = precio_raw.get("extracted_value")
        try:
            num = float(num) if num is not None else None
        except (TypeError, ValueError):
            num = None
        return texto, num
    if isinstance(precio_raw, str) and precio_raw.strip():
        digitos = re.sub(r"[^\d]", "", precio_raw)
        return precio_raw.strip(), (float(digitos) if digitos else None)
    return "", None


def _extraer_items(data: dict, solo_chile: bool = True) -> list:
    """Junta exact_matches + visual_matches, deduplica por link y filtra Chile."""
    items = []
    vistos = set()
    for seccion in ("exact_matches", "visual_matches"):
        for m in data.get(seccion, []):
            link = m.get("link", "") or ""
            if not link or link in vistos:
                continue
            es_cl = _es_chileno(link, m.get("source", ""))
            if solo_chile and not es_cl:
                continue
            texto_precio, num = _precio_a_numero(m.get("price"))
            vistos.add(link)
            items.append({
                "titulo": m.get("title", "") or "",
                "tienda": m.get("source", "") or "",
                "precio_texto": texto_precio,
                "precio_num": num,
                "link": link,
                "imagen": m.get("thumbnail", "") or "",
                "es_chileno": es_cl,
            })
    return items


def _cuantil(datos_ordenados: list, q: float) -> float:
    pos = (len(datos_ordenados) - 1) * q
    base = int(pos)
    resto = pos - base
    if base + 1 < len(datos_ordenados):
        return datos_ordenados[base] + resto * (datos_ordenados[base + 1] - datos_ordenados[base])
    return datos_ordenados[base]


def _filtrar_outliers(items: list) -> list:
    """Descarta precios atípicos con el método IQR (universal, sin valores
    casados a ningún producto). Los ítems sin precio siempre se conservan."""
    precios = sorted(x["precio_num"] for x in items if x["precio_num"] is not None)
    if len(precios) < 4:
        return items  # muy pocos datos para hablar de outliers
    q1 = _cuantil(precios, 0.25)
    q3 = _cuantil(precios, 0.75)
    iqr = q3 - q1
    tope = q3 + 1.5 * iqr
    piso = max(0, q1 - 1.5 * iqr)
    return [x for x in items
            if x["precio_num"] is None or (piso <= x["precio_num"] <= tope)]


def _resumen_precios(items: list) -> dict:
    """Min, máx y mediana de los precios encontrados (solo los que tienen precio)."""
    precios = sorted(x["precio_num"] for x in items if x["precio_num"] is not None)
    if not precios:
        return {}
    n = len(precios)
    mediana = precios[n // 2] if n % 2 else (precios[n // 2 - 1] + precios[n // 2]) / 2
    return {"min": round(precios[0]), "max": round(precios[-1]),
            "mediana": round(mediana), "cantidad": n}


# ==============================================================================
# FILTRO OPCIONAL DE SIMILITUD (Gemini compara la foto vs. los títulos)
# ==============================================================================

def filtrar_por_similitud_gemini(image_bytes: bytes, productos: list) -> list:
    """
    Usa Gemini para comparar la foto original con los TÍTULOS de los candidatos
    de Lens, y devuelve la MISMA lista reordenada de más a menos parecido.
    Nunca descarta candidatos, solo cambia su orden.

    Si no hay GEMINI_API_KEY, hay menos de 2 candidatos, o Gemini falla por
    cualquier motivo, devuelve la lista ORIGINAL sin cambios: este filtro nunca
    debe romper la búsqueda.
    """
    if not GEMINI_API_KEY or not productos or len(productos) < 2:
        return productos

    lineas = []
    for idx, p in enumerate(productos):
        precio_txt = f" — {p.get('precio_texto')}" if p.get("precio_texto") else ""
        lineas.append(f"{idx}: {p.get('titulo', '')}{precio_txt}")
    lista_titulos = "\n".join(lineas)

    prompt = f"""Eres un experto en identificación visual de productos para ecommerce. La imagen adjunta es la foto de referencia del producto que el usuario quiere encontrar.

A continuación hay una lista de candidatos encontrados en tiendas (solo se conoce su título e índice, no su imagen):
{lista_titulos}

Tu tarea: comparar lo que se ve en la foto de referencia con cada título y ordenar TODOS los candidatos de más a menos parecido al producto de la foto (misma marca, modelo y generación primero; variantes, accesorios u otras categorías al final). Debes incluir todos los índices, sin excluir ninguno.

Responde SOLO con JSON válido, sin markdown, con esta estructura exacta:
{{"orden": [TODOS los índices ordenados de MÁS parecido a MENOS parecido]}}

Ejemplo: {{"orden": [2, 0, 1, 3]}}"""

    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        respuesta, _ = _gemini_generate(prompt, imagen_pil=img)
        data = extraer_json_respuesta(respuesta)
        if not data or not isinstance(data, dict):
            return productos
        orden = data.get("orden")
        if not isinstance(orden, list) or not orden:
            return productos

        reordenados = [productos[i] for i in orden
                       if isinstance(i, int) and 0 <= i < len(productos)]
        if not reordenados:
            return productos

        # Candidatos que Gemini no mencionó en "orden": se agregan al final
        # (nunca se descartan) por si el JSON viene incompleto.
        mencionados = set(orden)
        faltantes = [p for i, p in enumerate(productos) if i not in mencionados]
        return reordenados + faltantes
    except Exception:
        return productos


# ==============================================================================
# ENTRADA PRINCIPAL
# ==============================================================================

def buscar_por_imagen_lens(image_bytes: bytes, solo_chile: bool = True,
                           max_resultados: int = 10) -> dict:
    """
    Busca el producto EXACTO a partir de la imagen usando Google Lens.

    Devuelve un dict:
      ok               -> True si la búsqueda se completó
      error            -> mensaje si algo falló (None si todo bien)
      productos        -> lista de {titulo, tienda, precio_texto, precio_num, link,
                          imagen, es_chileno}. Ordenada por precio (más barato
                          primero); si USAR_FILTRO_GEMINI está activo y Gemini
                          responde bien, queda ordenada por similitud visual
                          con la foto en su lugar.
      resumen_precios  -> {min, max, mediana, cantidad} en pesos
      url_imagen       -> URL temporal de la foto subida (para depurar)
    """
    out = {"ok": False, "error": None, "productos": [],
           "resumen_precios": {}, "url_imagen": ""}

    if not (SERPAPI_KEY and IMGBB_API_KEY):
        out["error"] = "Faltan las llaves SERPAPI_KEY o IMGBB_API_KEY."
        return out

    try:
        out["url_imagen"] = subir_a_imgbb(IMGBB_API_KEY, image_bytes)
    except Exception as e:
        out["error"] = f"No se pudo subir la imagen a ImgBB: {e}"
        return out

    try:
        data = buscar_en_lens(SERPAPI_KEY, out["url_imagen"])
    except Exception as e:
        out["error"] = f"No se pudo consultar Google Lens: {e}"
        return out

    if data.get("error"):
        out["error"] = f"SerpApi: {data['error']}"
        return out

    items = _extraer_items(data, solo_chile=solo_chile)
    items = _filtrar_outliers(items)
    # Orden: más barato primero; los sin precio quedan al final
    items.sort(key=lambda x: x["precio_num"] if x["precio_num"] is not None else float("inf"))

    if USAR_FILTRO_GEMINI:
        items = filtrar_por_similitud_gemini(image_bytes, items)

    out["productos"] = items[:max_resultados]
    out["resumen_precios"] = _resumen_precios(items)
    out["ok"] = True
    return out
