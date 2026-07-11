"""
ia.py — Motor de IA: Gemini con fallback a Groq y Vertex, y filtros con IA.
"""
import os
import json
import base64
from io import BytesIO

import requests
import google.generativeai as genai

from config import (GROQ_MODELOS_FALLBACK, GEMINI_MODELOS_FALLBACK,
                    VERTEX_HABILITADO, GOOGLE_VISION_JSON, GEMINI_API_KEY)
from utils import extraer_json_respuesta, descargar_imagen


def _groq_generate(prompt, imagen_pil=None):
    import time
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_key:
        raise Exception("GROQ_API_KEY no configurada")
    if imagen_pil is not None:
        raise Exception("Groq no soporta imágenes")
    for modelo in GROQ_MODELOS_FALLBACK:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={"model": modelo, "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 4000, "temperature": 0.1},
                timeout=15,
            )
            if resp.status_code == 200:
                texto = resp.json()["choices"][0]["message"]["content"].strip()
                if texto:
                    return texto, f"groq/{modelo}"
            elif resp.status_code == 429:
                time.sleep(1)
                continue
        except Exception:
            continue
    raise Exception("Todos los modelos Groq fallaron")


def _vertex_generate(prompt, imagen_pil=None):
    """Vertex AI vía REST (no gRPC) — con timeout corto. Solo si VERTEX_HABILITADO."""
    if not VERTEX_HABILITADO:
        raise Exception("Vertex deshabilitado")
    if not GOOGLE_VISION_JSON:
        raise Exception("JSON de cuenta de servicio no configurado")
    try:
        import google.auth.transport.requests
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_VISION_JSON, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        creds.refresh(google.auth.transport.requests.Request())
        token = creds.token

        with open(GOOGLE_VISION_JSON) as f:
            project_id = json.load(f).get("project_id", "")
        if not project_id:
            raise Exception("project_id no encontrado")

        modelo = "gemini-1.5-flash"
        url = (f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project_id}"
               f"/locations/us-central1/publishers/google/models/{modelo}:generateContent")

        parts = [{"text": prompt}]
        if imagen_pil is not None:
            buf = BytesIO()
            imagen_pil.save(buf, format="JPEG", quality=85)
            parts.append({"inline_data": {"mime_type": "image/jpeg",
                          "data": base64.b64encode(buf.getvalue()).decode()}})

        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"contents": [{"role": "user", "parts": parts}],
                  "generationConfig": {"maxOutputTokens": 1000, "temperature": 0.1}},
            timeout=20,
        )
        if resp.status_code == 200:
            texto = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if texto:
                return texto, f"vertex/{modelo}"
        raise Exception(f"Vertex HTTP {resp.status_code}")
    except Exception as e:
        raise Exception(f"Vertex error: {repr(e)}")


def _gemini_generate(prompt, imagen_pil=None):
    """Gemini con fallback: Gemini → Groq (texto) → Vertex (si habilitado)."""
    import time
    for nombre_modelo in GEMINI_MODELOS_FALLBACK:
        try:
            modelo = genai.GenerativeModel(nombre_modelo)
            if imagen_pil is not None:
                resp = modelo.generate_content([prompt, imagen_pil])
            else:
                resp = modelo.generate_content(prompt)
            texto = getattr(resp, "text", "").strip()
            if texto:
                return texto, nombre_modelo
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "rate" in err.lower():
                time.sleep(1)
                continue
            raise

    if imagen_pil is None:
        try:
            return _groq_generate(prompt)
        except Exception:
            pass

    if VERTEX_HABILITADO:
        try:
            return _vertex_generate(prompt, imagen_pil=imagen_pil)
        except Exception:
            pass

    raise Exception("Límite de IA alcanzado. Espera unos minutos.")


def filtrar_resultados_con_ia(nombre_producto, contexto, detalles):
    """
    Usa IA (una sola llamada) para clasificar cuáles resultados son realmente el
    mismo producto y cuáles son accesorios, repuestos u otros productos.
    Universal: funciona para cualquier categoría sin nombres hardcodeados.
    Devuelve la lista filtrada (o la original si la IA no responde bien).
    """
    if not detalles or len(detalles) < 2:
        return detalles

    marca = contexto.get("marca_probable", "") if contexto else ""
    modelo = contexto.get("modelo_probable", "") if contexto else ""
    categoria = contexto.get("categoria", "") if contexto else ""

    # Construir lista numerada de títulos con precio para que la IA los evalúe
    lineas = []
    for idx, d in enumerate(detalles):
        precio = d.get("precio")
        precio_txt = f" — ${precio:,}".replace(",", ".") if precio else ""
        lineas.append(f"{idx}: {d.get('titulo', '')}{precio_txt}")
    lista_titulos = "\n".join(lineas)

    desc_producto = nombre_producto
    if marca or modelo:
        desc_producto = f"{nombre_producto} (marca: {marca or 'N/A'}, modelo: {modelo or 'N/A'}, categoría: {categoria or 'N/A'})"

    prompt = f"""Eres un clasificador de productos de e-commerce. El usuario busca este producto:
PRODUCTO BUSCADO: {desc_producto}

A continuación hay una lista de resultados de búsqueda (con su número de índice). Tu tarea es identificar CUÁLES resultados son EXACTAMENTE el mismo producto que el buscado, y cuáles NO lo son.

NO son el mismo producto (debes EXCLUIRLOS):
- Productos de otra categoría totalmente distinta (ej: buscan un parlante y el resultado es una funda, un cable suelto, o un soporte)
- **GENERACIÓN o número de modelo DIFERENTE**: esto es MUY importante. Si el usuario busca la "5ta generación" (o "5th gen", "generación 5"), entonces la 4ta, 3ra, 2da o cualquier otra generación NO sirve y debe excluirse. Lo mismo para números de modelo: si buscan el modelo con un número, otro número es otro producto.
- Variantes nombradas distinto: "Pro", "Mini", "Max", "Plus", "Kids", "Lite" son productos diferentes al modelo base.
- Packs o combos de varios productos diferentes juntos

SÍ son el mismo producto (INCLÚYELOS):
- El producto exacto, aunque tenga distinto color, distinta redacción, distinta tienda o distinto precio
- La MISMA generación/modelo descrita de formas diferentes (ej: "5ta generación" = "5th gen" = "generación 5" = "gen 5")
- Resultados que mencionan el producto aunque el título esté redactado raro, SIEMPRE que sea la misma generación/modelo
- Regla: coincide en categoría Y en generación/número de modelo → incluir. Difiere en generación/número → excluir.

Resultados a clasificar:
{lista_titulos}

Responde SOLO con un JSON válido (sin markdown) con esta estructura exacta:
{{"validos": [lista de números de índice que SÍ son el mismo producto]}}

Ejemplo de respuesta: {{"validos": [0, 2, 3, 5]}}"""

    try:
        respuesta, _ = _gemini_generate(prompt)
        data = extraer_json_respuesta(respuesta)
        if data and isinstance(data, dict) and "validos" in data:
            indices_validos = data["validos"]
            if isinstance(indices_validos, list) and len(indices_validos) >= 1:
                filtrados = [detalles[i] for i in indices_validos
                             if isinstance(i, int) and 0 <= i < len(detalles)]
                # Seguridad: si el filtro deja demasiado pocos (posible error de IA),
                # y había bastantes, conservar los originales para no quedar sin datos
                if len(filtrados) >= 1:
                    return filtrados
    except Exception:
        pass

    return detalles


def comparar_visual_con_ia(img_usuario, detalles, max_imgs=10):
    """
    Compara la foto del usuario contra las imágenes de los resultados usando Gemini,
    en UNA sola llamada (eficiente: 1 solicitud sin importar cuántas imágenes).
    Reordena poniendo primero los visualmente más parecidos y descarta los que
    claramente no son el mismo producto. Universal, sin nombres hardcodeados.
    """
    if img_usuario is None or not detalles or not GEMINI_API_KEY:
        return detalles

    # Descargar imágenes de los candidatos (solo los que tienen imagen)
    candidatos_con_img = []
    imagenes = []
    for d in detalles[:max_imgs]:
        url = d.get("imagen", "")
        if not url:
            continue
        img = descargar_imagen(url)
        if img is not None:
            candidatos_con_img.append(d)
            imagenes.append(img)

    # Si no hay suficientes imágenes para comparar, devolver tal cual
    if len(imagenes) < 2:
        return detalles

    prompt = f"""Eres un experto en identificación visual de productos. La PRIMERA imagen es el producto que busca el usuario (su foto de referencia).

Las siguientes {len(imagenes)} imágenes son resultados de una búsqueda de precios, numeradas del 0 al {len(imagenes)-1} en el mismo orden en que aparecen.

Tu tarea: comparar VISUALMENTE cada imagen numerada con la foto de referencia (la primera) y decidir cuáles muestran EL MISMO PRODUCTO.

Considera el mismo producto aunque:
- Sea de distinto color
- Esté fotografiado desde otro ángulo o con otro fondo
- La foto sea de distinta calidad

NO es el mismo producto si:
- Es un accesorio, repuesto o parte (funda, cable, base, almohadilla)
- Es un modelo claramente diferente (otra forma, otro tamaño, otro diseño)
- Es un producto de otra categoría
- Es una imagen de "qué incluye la caja" o collage de accesorios

Responde SOLO con JSON válido, sin markdown, con esta estructura:
{{"coincidencias": [lista de números de las imágenes que SÍ son el mismo producto, ordenados de MÁS parecido a menos parecido]}}

Ejemplo: {{"coincidencias": [2, 0, 3]}}"""

    try:
        # Armar el contenido: prompt + foto usuario + todas las imágenes candidatas
        contenido = [prompt, img_usuario] + imagenes
        respuesta = None
        for nombre_modelo in GEMINI_MODELOS_FALLBACK:
            try:
                modelo = genai.GenerativeModel(nombre_modelo)
                resp = modelo.generate_content(contenido)
                respuesta = getattr(resp, "text", "").strip()
                if respuesta:
                    break
            except Exception as e:
                err = str(e)
                if "429" in err or "quota" in err.lower() or "rate" in err.lower():
                    continue
                raise

        data = extraer_json_respuesta(respuesta) if respuesta else None
        if data and isinstance(data, dict) and "coincidencias" in data:
            indices = data["coincidencias"]
            if isinstance(indices, list) and len(indices) >= 1:
                # Construir la lista reordenada: primero los que coinciden (en orden de parecido)
                coincidentes = [candidatos_con_img[i] for i in indices
                                if isinstance(i, int) and 0 <= i < len(candidatos_con_img)]
                if len(coincidentes) >= 1:
                    # Agregar al final los detalles que no tenían imagen (no evaluables)
                    sin_img = [d for d in detalles if d not in candidatos_con_img]
                    return coincidentes + sin_img
    except Exception:
        pass

    return detalles
