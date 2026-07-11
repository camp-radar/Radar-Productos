"""
vision.py — Detección por imagen: Vision API + identidad (Gemini) + pipeline +
verificación/enriquecimiento (Módulo 4).
"""
import re
import base64
import hashlib
from io import BytesIO

import requests
from PIL import Image

from config import GOOGLE_VISION_JSON, GOOGLE_VISION_API_KEY, GEMINI_API_KEY
from ia import _gemini_generate
from utils import extraer_json_respuesta, tokenizar_producto


def _get_vision_token():
    try:
        import google.auth.transport.requests
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_VISION_JSON, scopes=["https://www.googleapis.com/auth/cloud-vision"])
        creds.refresh(google.auth.transport.requests.Request())
        return creds.token
    except Exception:
        return ""


def vision_detection_engine(image_bytes: bytes) -> dict:
    r_out = {"object_main": "", "ocr_lines": [], "ocr_text_full": "", "brand_visible": "",
             "model_visible": "", "labels": [], "web_entities": [], "best_guess": [],
             "visual_traits": [], "confidence": 0.0, "ok": False, "error": None}
    try:
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")
        payload = {"requests": [{"image": {"content": img_b64}, "features": [
            {"type": "TEXT_DETECTION", "maxResults": 30},
            {"type": "LOGO_DETECTION", "maxResults": 5},
            {"type": "LABEL_DETECTION", "maxResults": 15},
            {"type": "WEB_DETECTION", "maxResults": 10},
            {"type": "OBJECT_LOCALIZATION", "maxResults": 5}]}]}

        # Llamada a Vision con reintentos automáticos (evita timeouts esporádicos)
        def _vision_post(url, headers=None):
            ultimo_error = None
            for intento in range(3):  # hasta 3 intentos
                try:
                    return requests.post(url, json=payload, headers=headers, timeout=30)
                except requests.exceptions.RequestException as e:
                    ultimo_error = e
                    continue
            raise ultimo_error if ultimo_error else Exception("Vision sin respuesta")

        resp = None
        try:
            if GOOGLE_VISION_JSON:
                token = _get_vision_token()
                if token:
                    resp = _vision_post("https://vision.googleapis.com/v1/images:annotate",
                                        headers={"Authorization": f"Bearer {token}"})
            if (resp is None or resp.status_code != 200) and GOOGLE_VISION_API_KEY:
                resp = _vision_post(
                    f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}")
        except requests.exceptions.RequestException:
            r_out["error"] = ("No se pudo conectar con el servicio de detección "
                              "(la conexión tardó demasiado). Intenta de nuevo en unos segundos.")
            return r_out

        if resp is None or resp.status_code != 200:
            r_out["error"] = f"Vision HTTP {resp.status_code if resp else 'sin respuesta'}"
            return r_out

        r = resp.json().get("responses", [{}])[0]

        ocr_full = ""
        anotaciones = r.get("textAnnotations", [])
        if anotaciones:
            ocr_full = anotaciones[0].get("description", "").strip()
        ocr_lines = []
        for linea in ocr_full.splitlines():
            linea = linea.strip()
            if len(linea) < 2:
                continue
            if re.match(r"^\d+[\.,]?\d*\s*(ml|g|oz|fl|kg|lb|%|mah|v|w)?$", linea, re.IGNORECASE):
                continue
            ocr_lines.append(linea)
        r_out["ocr_text_full"] = ocr_full
        r_out["ocr_lines"] = ocr_lines[:15]

        logos = [l["description"] for l in r.get("logoAnnotations", []) if l.get("score", 0) >= 0.60]
        r_out["brand_visible"] = logos[0] if logos else ""

        labels = [l["description"] for l in r.get("labelAnnotations", []) if l.get("score", 0) >= 0.65]
        r_out["labels"] = labels[:10]
        r_out["object_main"] = labels[0] if labels else ""

        web = r.get("webDetection", {})
        r_out["web_entities"] = [e["description"] for e in web.get("webEntities", [])
                                 if e.get("score", 0) >= 0.45 and e.get("description")][:8]
        r_out["best_guess"] = [g["label"] for g in web.get("bestGuessLabels", [])][:3]
        r_out["visual_traits"] = [o["name"] for o in r.get("localizedObjectAnnotations", [])
                                  if o.get("score", 0) >= 0.55][:6]

        modelo_detectado = ""
        for linea in ocr_lines:
            m = re.search(r'\b([A-Za-z]{1,4}\d{1,4}[A-Za-z]?|[A-Za-z]{2,5})\b', linea)
            if m:
                cand = m.group(1).upper()
                comunes = {"THE", "AND", "FOR", "NEW", "PRO", "MAX", "LED", "USB", "TWS", "ANC", "ENC"}
                if cand not in comunes and len(cand) >= 2:
                    modelo_detectado = cand
                    break
        if "TWS" in ocr_full.upper():
            modelo_detectado = (f"{modelo_detectado} TWS" if modelo_detectado and modelo_detectado != "TWS" else "TWS")
        r_out["model_visible"] = modelo_detectado

        conf = 0.0
        if r_out["brand_visible"]: conf += 0.30
        if r_out["model_visible"]: conf += 0.30
        if r_out["ocr_lines"]: conf += 0.20
        if r_out["best_guess"]: conf += 0.15
        if r_out["web_entities"]: conf += 0.05
        r_out["confidence"] = round(min(conf, 1.0), 2)
        r_out["ok"] = True
    except Exception as e:
        r_out["error"] = repr(e)
    return r_out


# ==============================================================================
# MÓDULO 3 — IDENTIDAD DE PRODUCTO (Gemini + fallback)
# ==============================================================================
_BASURA_VISION = {
    "product", "item", "object", "thing", "device", "electronic", "technology",
    "font", "text", "label", "design", "packaging", "container", "liquid",
    "glass", "plastic", "material", "null", "none", "unknown", "electronics",
    "hardware", "gadget", "home appliance",
}


def _limpiar_token(token: str) -> bool:
    t = token.strip().lower()
    if len(t) < 2 or t in _BASURA_VISION:
        return False
    if re.match(r"^\d+[\.,]?\d*\s*(ml|g|oz|fl|kg|lb|%|mah|v|w|cm|mm)?$", t, re.IGNORECASE):
        return False
    return True


def construir_identidad(vd: dict, image_pil=None) -> dict:
    """Módulo 3 — Gemini interpreta señales de Vision → identidad comercial."""
    modelo_ocr = (vd.get("model_visible") or "").strip()
    if modelo_ocr and not re.search(r'\d', modelo_ocr):
        modelo_ocr = ""
    marca_logo = (vd.get("brand_visible") or "").strip()
    ocr_lines = [l for l in vd.get("ocr_lines", []) if _limpiar_token(l)]
    labels = [l for l in vd.get("labels", []) if _limpiar_token(l)]
    entities = [e for e in vd.get("web_entities", []) if _limpiar_token(e) and len(e) <= 50]
    best_guess = [g for g in vd.get("best_guess", []) if _limpiar_token(g)]
    visual_traits = [r for r in vd.get("visual_traits", []) if _limpiar_token(r)]
    ocr_util = " ".join(ocr_lines[:3]).strip()

    identidad = None
    if GEMINI_API_KEY:
        try:
            prompt = f"""Eres un sistema experto en identificación de productos para ecommerce.

SEÑALES VISUALES (mayor número = mayor confianza):
- modelo_ocr   [0.90]: "{modelo_ocr}"
- marca_logo   [0.80]: "{marca_logo}"
- ocr_util     [0.65]: "{ocr_util}"
- web_entities [0.50]: {entities[:4]}
- best_guess   [0.35]: {best_guess}
- labels       [0.20]: {labels[:6]}

REGLAS:
1. Usa las señales de MAYOR confianza disponibles.
2. web_entities son descripciones web reales — muy confiables.
3. NUNCA inventes marca o modelo que no esté en las señales.
4. nombre_base debe ser específico y buscable, evita términos genéricos.
5. El producto puede ser cualquier cosa — no asumas categoría sin evidencia.

Responde SOLO JSON válido, sin markdown:
{{
  "nombre_base": "nombre comercial específico y buscable",
  "categoria": "categoría específica",
  "marca": "marca o vacío",
  "modelo": "modelo o vacío",
  "keywords_fuertes": ["kw1", "kw2", "kw3"],
  "rasgos_distintivos": ["rasgo1", "rasgo2"],
  "confidence_identity": 0.0
}}"""
            if image_pil is not None:
                respuesta, modelo_usado = _gemini_generate(prompt, imagen_pil=image_pil)
            else:
                respuesta, modelo_usado = _gemini_generate(prompt)
            parsed = extraer_json_respuesta(respuesta)
            if parsed and isinstance(parsed, dict) and parsed.get("nombre_base"):
                parsed["fuente_identidad"] = f"gemini ({modelo_usado})"
                identidad = parsed
        except Exception:
            pass

    if identidad is None:
        partes = []
        if marca_logo:
            partes.append(marca_logo)
        if modelo_ocr:
            partes.append(modelo_ocr)
        if not partes and ocr_util:
            partes.extend([t for t in tokenizar_producto(ocr_util)][:4])
        if not partes and best_guess:
            partes.extend(best_guess[:2])
        if not partes and entities:
            partes.extend(entities[:2])
        if not partes and labels:
            partes.append(labels[0])
        nombre_base = " ".join(partes).strip() or "Producto sin identificar"
        identidad = {
            "nombre_base": nombre_base,
            "categoria": labels[0] if labels else "Producto",
            "marca": marca_logo,
            "modelo": modelo_ocr,
            "keywords_fuertes": ([marca_logo] if marca_logo else []) + ([modelo_ocr] if modelo_ocr else []),
            "rasgos_distintivos": visual_traits[:4],
            "confidence_identity": 0.4 if (marca_logo or modelo_ocr) else 0.2,
            "fuente_identidad": "fallback_determinista",
        }
    return identidad


def detectar_identidad_imagen(image_bytes: bytes, image_pil=None) -> dict:
    """Vision + Módulo 3 → identidad del producto."""
    vd = vision_detection_engine(image_bytes)
    if not vd["ok"]:
        return {"error": vd.get("error", "Vision API no disponible")}
    ident = construir_identidad(vd, image_pil=image_pil)
    return {
        "nombre_detectado": ident["nombre_base"],
        "categoria": ident.get("categoria", ""),
        "marca_probable": ident.get("marca", ""),
        "modelo_probable": ident.get("modelo", ""),
        "caracteristicas_clave": ident.get("keywords_fuertes", [])[:4],
        "rasgos_distintivos": ident.get("rasgos_distintivos", []),
        "confianza_marca": "Alta" if ident.get("marca") else "Baja",
        "confianza_modelo": "Alta" if ident.get("modelo") else "Baja",
        "confidence_identity": ident.get("confidence_identity", 0),
        "resumen_visual": f"Detectado: {ident['nombre_base']}",
        "texto_ocr": vd.get("ocr_text_full", "")[:300],
    }


# ==============================================================================
# MÓDULO 1 — PIPELINE DE IMAGEN
# ==============================================================================
def image_input_pipeline(imagen_obj) -> dict:
    out = {"image_hash": None, "image_clean": None, "image_bytes_clean": None,
           "quality_score": 0.0, "warnings": [], "ok": False}
    try:
        image_bytes = imagen_obj.getvalue()
        if not image_bytes or len(image_bytes) < 1000:
            out["warnings"].append("Imagen demasiado pequeña.")
            return out
        out["image_hash"] = hashlib.md5(image_bytes).hexdigest()

        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        try:
            import PIL.ExifTags
            exif = img._getexif()
            if exif:
                for tag, value in exif.items():
                    if PIL.ExifTags.TAGS.get(tag) == "Orientation":
                        if value == 3: img = img.rotate(180, expand=True)
                        elif value == 6: img = img.rotate(270, expand=True)
                        elif value == 8: img = img.rotate(90, expand=True)
                        break
        except Exception:
            pass

        MAX_DIM = 1200
        w, h = img.size
        if max(w, h) > MAX_DIM:
            ratio = MAX_DIM / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        out["image_clean"] = img

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=88)
        out["image_bytes_clean"] = buf.getvalue()

        pixeles = img.size[0] * img.size[1]
        out["quality_score"] = (0.90 if pixeles >= 500_000 else 0.75 if pixeles >= 200_000
                                else 0.55 if pixeles >= 50_000 else 0.30)
        out["ok"] = True
    except Exception as e:
        out["warnings"].append(f"Error procesando imagen: {repr(e)}")
    return out


# ==============================================================================
# MÓDULO 4 — VERIFICACIÓN VISUAL + ENRIQUECIMIENTO
# ==============================================================================
def verificar_y_enriquecer(image_pil, candidatos: list, identidad_previa: dict) -> dict:
    resultado = {"candidatos_confirmados": [], "candidatos_descartados": [],
                 "nombre_comercial_sugerido": "", "descripcion_comercial_final": "",
                 "confianza_verificacion": 0.0, "ok": False}
    if not image_pil or not candidatos:
        return resultado

    # Fase B: DESACTIVADA. La verificación visual por histograma resultó poco
    # confiable (imágenes de tiendas muy variadas dan scores engañosos y descartan
    # productos válidos). El filtrado real ya lo hacen el filtro de precios + Gemini
    # en buscar_producto. Aquí confirmamos todos los candidatos sin re-filtrar.
    confirmados = list(candidatos)
    descartados = []
    resultado["candidatos_confirmados"] = confirmados
    resultado["candidatos_descartados"] = descartados
    resultado["confianza_verificacion"] = 1.0

    # Fase C: enriquecimiento con Gemini
    if GEMINI_API_KEY and confirmados:
        try:
            titulos = [c.get("titulo", "") for c in confirmados[:5] if c.get("titulo")]
            prompt = f"""Eres experto en ecommerce. Identidad previa: "{identidad_previa.get('nombre_base', '')}".

Títulos de candidatos en Mercado Libre:
{chr(10).join(f'{i}. "{t}"' for i, t in enumerate(titulos))}

Genera nombre comercial específico y descripción. Identifica índices de accesorios (fundas, soportes, repuestos).
Responde SOLO JSON:
{{
  "nombre_comercial_sugerido": "nombre específico",
  "descripcion_comercial_final": "descripción comercial breve en español",
  "marca_detectada": "marca o vacío",
  "modelo_detectado": "modelo o vacío",
  "categoria_refinada": "categoría",
  "indices_accesorios": []
}}"""
            respuesta, _ = _gemini_generate(prompt, imagen_pil=image_pil)
            parsed = extraer_json_respuesta(respuesta)
            if parsed and parsed.get("nombre_comercial_sugerido"):
                idx_acc = parsed.get("indices_accesorios", [])
                if idx_acc:
                    principales, accesorios = [], []
                    for i, c in enumerate(confirmados[:len(titulos)]):
                        (accesorios if i in idx_acc else principales).append(c)
                    resultado["candidatos_confirmados"] = principales + confirmados[len(titulos):]
                    resultado["candidatos_descartados"] += accesorios
                resultado["nombre_comercial_sugerido"] = parsed.get("nombre_comercial_sugerido", "")
                resultado["descripcion_comercial_final"] = parsed.get("descripcion_comercial_final", "")
                resultado["marca_detectada"] = parsed.get("marca_detectada", "")
                resultado["modelo_detectado"] = parsed.get("modelo_detectado", "")
                resultado["categoria_refinada"] = parsed.get("categoria_refinada", "")
                resultado["ok"] = True
        except Exception:
            pass
    return resultado
