"""
busqueda.py — Búsqueda de precios (Serper/Google Shopping), scoring, filtros de
precio (cluster/mediana) y el orquestador buscar_producto.
"""
import os
import re
import statistics

import requests

from utils import (STOPWORDS, normalizar_texto_match, normalizar_consulta_usuario,
                   tokenizar_producto, limpiar_url)
from ia import filtrar_resultados_con_ia


def filtrar_precios_outliers(lista):
    """
    Detecta el cluster de precios del producto real, descartando accesorios baratos
    y precios absurdos. Universal: funciona por estadística, sin nombres de productos.
    """
    lista = sorted([float(x) for x in lista if x and x > 0])
    if len(lista) <= 3:
        return lista
    # Ancla: la mediana (precio típico del producto). Los precios abismales son
    # minoría y NO mueven la mediana, así que no pueden inflar la referencia.
    med = statistics.median(lista)
    # Aceptar precios entre el 55% y 160% de la mediana. Sin abismos.
    lo = med * 0.55
    hi = med * 1.60
    filtrados = [x for x in lista if lo <= x <= hi]
    return filtrados if len(filtrados) >= 2 else lista[:]


def score_coincidencia_producto(query: str, titulo: str) -> float:
    tq = set(tokenizar_producto(query))
    tt = set(tokenizar_producto(titulo))
    if not tq or not tt:
        return 0.0
    inter = len(tq.intersection(tt))
    base = inter / max(len(tq), 1)
    q_norm = normalizar_texto_match(query)
    t_norm = normalizar_texto_match(titulo)
    if q_norm and t_norm and q_norm[:20] in t_norm:
        base += 0.18
    for token in tq:
        if token in tt and re.match(r'^[a-z]{0,3}\d{1,4}[a-z]?$', token):
            base += 0.20
            break
    tokens_largos = [t for t in tq if t in tt and len(t) >= 4]
    if tokens_largos:
        base += min(len(tokens_largos) * 0.08, 0.24)
    if len(tt) < 3:
        base -= 0.15
    if (inter / max(len(tq), 1)) < 0.20 and len(tq) >= 3:
        base -= 0.20
    return max(0.0, min(base, 1.0))


def score_contexto_visual(query: str, titulo: str, contexto=None) -> float:
    contexto = contexto or {}
    t = normalizar_texto_match(titulo or "")
    score = score_coincidencia_producto(query, titulo)

    marca = normalizar_texto_match(contexto.get("marca_probable") or "")
    modelo = normalizar_texto_match(contexto.get("modelo_probable") or "")
    categoria = normalizar_texto_match(contexto.get("categoria") or "")
    conf_marca = contexto.get("confianza_marca", "Baja")
    conf_modelo = contexto.get("confianza_modelo", "Baja")

    marca_invalida = not marca or marca in {"generica", "sin", "especificar", "null", "none", ""}
    if not marca_invalida:
        if marca in t:
            score += {"Alta": 0.35, "Media": 0.22, "Baja": 0.10}.get(conf_marca, 0.10)
        else:
            if conf_marca == "Alta":
                score -= 0.30
            elif conf_marca == "Media":
                score -= 0.15

    modelo_invalido = not modelo or modelo in {"sin especificar", "modelo desconocido", "null", "none", ""}
    if not modelo_invalido:
        modelo_tokens = [x for x in tokenizar_producto(modelo) if len(x) >= 3]
        inter = sum(1 for x in modelo_tokens if x in t)
        cobertura = inter / max(len(modelo_tokens), 1)
        if conf_modelo == "Alta":
            if cobertura >= 0.8:
                score += 0.35
            elif cobertura >= 0.5:
                score += 0.18
            else:
                score -= 0.25
        elif conf_modelo == "Media":
            if cobertura >= 0.5:
                score += 0.18
            elif cobertura == 0:
                score -= 0.10

    if categoria:
        cat_tokens = [x for x in tokenizar_producto(categoria) if len(x) >= 4]
        if any(x in t for x in cat_tokens):
            score += 0.08

    return max(0.0, min(score, 1.0))


def deduplicar_detalles(detalles):
    depurados = []
    vistos = set()
    for d in detalles:
        link = d.get("link", "")
        # Los links de Google Shopping son todos google.com/search; deduplicar por
        # catalogid si existe, si no por combinación tienda+precio+titulo.
        clave = None
        m = re.search(r"catalogid:(\d+)", link)
        if m:
            clave = "cat:" + m.group(1)
        else:
            link_base = limpiar_url(link).split("?")[0].split("#")[0].rstrip("/")
            if "google.com/search" in link_base:
                # Link genérico de Google: usar tienda+precio+inicio del título
                clave = f"{d.get('fuente','')}|{d.get('precio','')}|{normalizar_texto_match(d.get('titulo',''))[:30]}"
            else:
                clave = link_base
        if clave in vistos:
            continue
        vistos.add(clave)
        depurados.append(d)
    return depurados


# Tiendas/fuentes que NO queremos mostrar (marketplaces internacionales, revendedores
# de usados, o negocios que no son retail de productos nuevos).
FUENTES_BLOQUEADAS = {
    "ebay", "amazon", "aliexpress", "alibaba", "wish", "temu", "shein",
    "walmart", "mercadolivre", "americanas", "shopee", "etsy", "wallapop",
    "facebook", "instagram", "craigslist", "olx",
}

# Tiendas de retail chileno explícitamente reconocidas (se aceptan aunque no terminen en .cl).
TIENDAS_CONFIABLES_CL = {
    # Multitiendas / grandes retailers
    "falabella", "paris", "ripley", "hites", "lapolar", "la polar", "abcdin",
    "abc din", "tricot", "corona",
    # Mejoramiento del hogar
    "sodimac", "easy", "construmart", "imperial",
    # Supermercados con electro
    "lider", "líder", "jumbo", "tottus", "santa isabel", "unimarc",
    # Marketplace y tecnología confiable
    "mercadolibre", "mercado libre", "pcfactory", "pc factory", "spdigital",
    "sp digital", "maconline", "mac online", "casaroyal", "casa royal",
    "mci electronics", "gsmpro", "blustore", "winpy", "sistemax", "netnow",
    "reifschneider", "reif", "ictienda", "linio",
    # Telecom con venta de dispositivos
    "entel", "movistar", "wom", "claro",
    # Tiendas oficiales de marca
    "samsung", "sony", "xiaomi", "huawei", "apple", "lenovo", "hp store",
    "dell", "philips", "lg electronics",
}


def _es_tienda_confiable(fuente: str) -> bool:
    """
    True si la fuente es retail chileno confiable.
    Lógica: rechaza marketplaces internacionales/usados; acepta dominios .cl
    y tiendas chilenas reconocidas. Así captura tiendas nuevas sin lista infinita.
    """
    if not fuente:
        return False
    f = fuente.lower().strip()
    # 1) Rechazar fuentes bloqueadas (eBay, Amazon, etc.)
    for bloqueada in FUENTES_BLOQUEADAS:
        if bloqueada in f:
            return False
    # 2) Aceptar tiendas chilenas reconocidas
    for tienda in TIENDAS_CONFIABLES_CL:
        if tienda in f:
            return True
    # 3) Aceptar cualquier dominio chileno (.cl) que no haya sido bloqueado
    if ".cl" in f:
        return True
    return False


# Orden de prioridad del retail (para la selección de precios).
# Las primeras tienen preferencia al armar el listado de tiendas.
RETAIL_PRIORIDAD = [
    "falabella", "ripley", "paris", "sodimac", "hites",
    "la polar", "lapolar", "easy", "lider", "líder",
    "abc din", "abcdin", "jumbo", "tottus", "pc factory", "pcfactory",
    "maconline", "casa royal", "casaroyal", "mci electronics",
]


def _es_mercadolibre(fuente: str) -> bool:
    """True si la fuente es Mercado Libre."""
    if not fuente:
        return False
    f = fuente.lower()
    return "mercadolibre" in f or "mercado libre" in f


def _prioridad_retail(fuente: str) -> int:
    """
    Devuelve el índice de prioridad de una tienda de retail (menor = más prioritaria).
    Las que no están en la lista van al final.
    """
    if not fuente:
        return 999
    f = fuente.lower().strip()
    for idx, tienda in enumerate(RETAIL_PRIORIDAD):
        if tienda in f:
            return idx
    return 999


def generar_link_tienda(titulo: str, tienda: str) -> str:
    """
    Genera un link que busca el producto en la tienda específica vía Google.
    Google suele llevar directo a la ficha del producto en esa tienda.
    Universal: funciona para cualquier tienda sin mantener URLs internas.
    """
    from urllib.parse import quote_plus
    # Limpiar el nombre de la tienda (quitar .com, .cl, etc. para la búsqueda)
    tienda_limpia = tienda
    for suf in [".com", ".cl", ".net", "www."]:
        tienda_limpia = tienda_limpia.replace(suf, "")
    tienda_limpia = tienda_limpia.strip()
    consulta = f"{titulo} {tienda_limpia}".strip()
    return "https://www.google.com/search?q=" + quote_plus(consulta)


def _serper_precio_a_int(precio_str):
    """Convierte '$29.990' o '$24.990 ahora' a entero 29990."""
    if not precio_str:
        return None
    import re
    # Quitar todo menos digitos y separadores, tomar el primer numero
    m = re.search(r"[\d][\d.,]*", str(precio_str))
    if not m:
        return None
    limpio = m.group(0).replace(".", "").replace(",", "")
    try:
        v = int(limpio)
        return v if 300 <= v <= 10_000_000 else None
    except Exception:
        return None


def buscar_ml(consulta: str, contexto: dict, limite=40) -> list:
    """
    Busca precios de productos en Google Shopping (Chile) via Serper.dev.
    Devuelve precios de multiples tiendas chilenas (Falabella, Paris, ML, Sodimac, etc.).
    Mantiene el nombre 'buscar_ml' por compatibilidad con el resto de la app.
    """
    import json as _json
    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        return []
    try:
        resp = requests.post(
            "https://google.serper.dev/shopping",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            data=_json.dumps({"q": consulta, "gl": "cl", "hl": "es", "location": "Chile"}),
            timeout=20)
        if resp.status_code != 200:
            return []
        data = resp.json()
        items = data.get("shopping", [])
        resultados = []
        for item in items[:limite]:
            titulo = item.get("title", "")
            precio = _serper_precio_a_int(item.get("price"))
            link = item.get("link", "")
            imagen = item.get("imageUrl", "")
            tienda = item.get("source", "Google Shopping")
            if not precio or not titulo:
                continue
            # Solo tiendas de retail chileno confiable (evita eBay, Amazon internacional, usados)
            if not _es_tienda_confiable(tienda):
                continue
            score = min(score_contexto_visual(consulta, titulo, contexto=contexto) + 0.10, 1.0)
            if score >= 0.20:
                resultados.append({
                    "titulo": titulo[:140],
                    "precio": precio,
                    "imagen": imagen,
                    "link": link,
                    "score_match": score,
                    "fuente": tienda,
                })
        return resultados
    except Exception:
        return []


def construir_consultas(nombre_base, contexto):
    """Genera consultas en cascada para ML."""
    marca = (contexto.get("marca_probable") or "").strip()
    modelo = (contexto.get("modelo_probable") or "").strip()
    base = normalizar_consulta_usuario(nombre_base)

    consultas = [base]
    if marca and modelo:
        consultas.append(normalizar_texto_match(f"{marca} {modelo}"))
    # limitar a 5 tokens
    tokens = base.split()
    if len(tokens) > 5:
        consultas.append(" ".join(tokens[:5]))

    vistas = set()
    final = []
    for q in consultas:
        q = q.strip()
        if q and q not in vistas and len(q) >= 3:
            vistas.add(q)
            final.append(q)
    return final[:4]


def _extraer_generacion(texto):
    """
    Extrae el número de generación de un texto, en cualquier formato:
    '5ta', '5th', '5a', 'quinta', 'generacion 5', '(5.a gen)', etc.
    Devuelve el número (int) o None si no encuentra generación.
    Universal: no depende de ningún producto específico.
    """
    if not texto:
        return None
    t = normalizar_texto_match(texto)
    ordinales = {"primera": 1, "segunda": 2, "tercera": 3, "cuarta": 4, "quinta": 5,
                 "sexta": 6, "septima": 7, "octava": 8, "novena": 9, "decima": 10,
                 "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
    for palabra, num in ordinales.items():
        if palabra in t:
            return num
    # Patrones tipo "5ta", "5th", "5a", "5.a", "4ra", cerca de "gen" o solos
    # Buscar número seguido de sufijo ordinal
    m = re.search(r'\b(\d+)\s*(ta|va|ra|da|to|vo|ro|do|th|nd|st|rd|a|ª|\.a)\b', t)
    if m:
        return int(m.group(1))
    # Buscar "generacion N" o "gen N"
    m = re.search(r'(?:generacion|gen)\s*(\d+)', t)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d+)\s*(?:generacion|gen)', t)
    if m:
        return int(m.group(1))
    return None


def _filtrar_generacion(detalles, consulta):
    """
    Descarta resultados cuya generación difiere de la buscada.
    Solo actúa si la consulta especifica una generación clara.
    """
    gen_buscada = _extraer_generacion(consulta)
    if gen_buscada is None:
        return detalles  # la consulta no especifica generación, no filtrar
    filtrados = []
    for d in detalles:
        gen_item = _extraer_generacion(d.get("titulo", ""))
        # Mantener si: no tiene generación detectable (ambiguo, damos beneficio de la duda)
        # o si coincide con la buscada. Descartar solo si tiene generación DISTINTA.
        if gen_item is None or gen_item == gen_buscada:
            filtrados.append(d)
    # Seguridad: si el filtro deja muy pocos, devolver original (evita quedar sin datos)
    return filtrados if len(filtrados) >= 2 else detalles


def separar_ml_retail(detalles, max_resultados=5):
    """
    Selecciona los mejores candidatos con precios consistentes (sin variaciones
    abismales). Devuelve dict con top/todos. Se prioriza: producto correcto (precio
    dentro del cluster real) + mejor precio + variedad de tiendas.
    """
    if not detalles:
        return {"top": [], "todos": [], "ml_top": [], "retail_top": []}

    # 1) Filtro de precios estricto: quedarse con el cluster del producto real,
    #    descartando accesorios baratos Y precios muy por encima del grueso.
    precios = sorted(d["precio"] for d in detalles if d.get("precio"))
    if len(precios) >= 4:
        # Ancla: la mediana (precio típico). Es robusta: los precios abismales son
        # minoría y no la mueven, así que no pueden inflar la referencia ni colarse.
        med_ref = statistics.median(precios)
        # Rango aceptado: 55% a 160% de la mediana (estricto, sin abismos)
        lo = med_ref * 0.55
        hi = med_ref * 1.60
        candidatos = [d for d in detalles if lo <= d.get("precio", 0) <= hi]
        # Si quedan muy pocos, relajar SOLO el piso (para precios bajos legítimos).
        # El techo NUNCA se ensancha: un precio abismalmente alto siempre se corta,
        # aunque eso signifique mostrar menos de 5 resultados. La confiabilidad primero.
        if len(candidatos) < 2:
            lo2 = med_ref * 0.40
            candidatos = [d for d in detalles if lo2 <= d.get("precio", 0) <= hi]
        # Último recurso (datos degenerados): si aún no hay nada, mostrar todo.
        if len(candidatos) < 1:
            candidatos = list(detalles)
    else:
        candidatos = list(detalles)

    # 2) Ordenar por precio ascendente (mejores precios primero)
    candidatos = sorted(candidatos, key=lambda x: x.get("precio", 999999))

    # 3) Seleccionar priorizando variedad de tiendas (una por tienda primero)
    seleccion = []
    tiendas_vistas = set()
    for d in candidatos:
        tienda = (d.get("fuente", "") or "").lower().strip()
        if tienda not in tiendas_vistas:
            tiendas_vistas.add(tienda)
            seleccion.append(d)
        if len(seleccion) >= max_resultados:
            break
    # Completar si faltan (permitiendo repetir tienda con precio distinto)
    if len(seleccion) < max_resultados:
        vistos = {(d.get("fuente", "").lower().strip(), d.get("precio")) for d in seleccion}
        for d in candidatos:
            clave = (d.get("fuente", "").lower().strip(), d.get("precio"))
            if d not in seleccion and clave not in vistos:
                seleccion.append(d)
                vistos.add(clave)
            if len(seleccion) >= max_resultados:
                break

    seleccion = seleccion[:max_resultados]

    # Para compatibilidad con el render: separar los seleccionados en ml/retail
    ml_top = [d for d in seleccion if _es_mercadolibre(d.get("fuente", ""))]
    retail_top = [d for d in seleccion if not _es_mercadolibre(d.get("fuente", ""))]

    return {"top": seleccion, "todos": seleccion,
            "ml_top": ml_top, "retail_top": retail_top}


def buscar_producto(nombre_base, contexto=None, max_resultados=5):
    """Busca precios y devuelve top resultados: 5 de Mercado Libre + 5 de retail."""
    contexto = contexto or {}
    consultas = construir_consultas(nombre_base, contexto)
    if not consultas:
        return {"top": [], "todos": []}

    tiene_marca = bool(contexto.get("marca_probable") and contexto.get("confianza_marca") in ("Alta", "Media"))
    tiene_modelo = bool(contexto.get("modelo_probable") and contexto.get("confianza_modelo") in ("Alta", "Media"))
    es_imagen = contexto.get("_es_busqueda_imagen", False)

    todos = []
    vistos_links = set()
    for consulta in consultas:
        items = buscar_ml(consulta, contexto)
        for it in items:
            clave = it.get("link", "") or it.get("titulo", "")
            if clave not in vistos_links:
                vistos_links.add(clave)
                todos.append(it)
        if len(todos) >= 40:
            break

    # Filtro de términos de modelo: flexible. Solo se aplica cuando el modelo es un
    # código alfanumérico claro (ej "q30", "520", "a52"), no cuando el número es
    # descriptivo (ej "5ta generación", que se escribe de muchas formas: 5/5ta/5th/quinta).
    tokens_imp = set(normalizar_texto_match(consultas[0]).split()) - STOPWORDS
    # Palabras que indican que el número es descriptivo, no un código de modelo
    _desc_num = {"generacion", "generación", "gen", "ta", "va", "ra", "da",
                 "quinta", "cuarta", "tercera", "segunda", "primera", "th", "nd", "st", "rd"}
    # Un término es "código de modelo" si tiene número Y letras juntas (q30, a52),
    # pero NO si es un número ordinal descriptivo (5ta, 5th, 4ta, quinta, etc.).
    _sufijos_ordinales = ("ta", "va", "ra", "da", "to", "vo", "ro", "do",
                          "th", "nd", "st", "rd", "ma", "mo")
    terminos_modelo = set()
    for t in tokens_imp:
        if re.search(r'\d', t) and re.search(r'[a-z]', t) and len(t) >= 3:
            # Excluir ordinales tipo "5ta", "5th", "4ta" (número + sufijo ordinal corto)
            m = re.match(r'^(\d+)([a-z]+)$', t)
            if m and m.group(2) in _sufijos_ordinales:
                continue  # es ordinal descriptivo, no código de modelo
            terminos_modelo.add(t)

    # Filtrar solo si hay un código de modelo claro (no para números descriptivos)
    candidatos = []
    for item in todos:
        titulo_norm = normalizar_texto_match(item.get("titulo", ""))
        if terminos_modelo:
            if all(t in titulo_norm for t in terminos_modelo):
                candidatos.append(item)
        else:
            candidatos.append(item)

    # Si el filtro de modelo dejó muy pocos, usar todos (Google ya ordenó por relevancia)
    if len(candidatos) < 3:
        candidatos = todos

    # Dedup + quitar sin precio
    detalles = deduplicar_detalles(candidatos)
    detalles = [d for d in detalles if d.get("precio")]

    # Pre-filtrar por cluster de precios POR GRUPO (ML y retail) antes de la IA.
    # Esto quita los accesorios baratos por estadística y deja a Gemini una lista
    # corta y limpia, donde acierta mucho mejor que con 40 items mezclados.
    ml_pre = [d for d in detalles if _es_mercadolibre(d.get("fuente", ""))]
    retail_pre = [d for d in detalles if not _es_mercadolibre(d.get("fuente", ""))]

    def _prefiltro_precio(items):
        if len(items) < 4:
            return items
        precios = [d["precio"] for d in items]
        pf = filtrar_precios_outliers(precios)
        if pf:
            lo, hi = min(pf), max(pf)
            fil = [d for d in items if lo <= d["precio"] <= hi]
            return fil if len(fil) >= 2 else items
        return items

    ml_pre = _prefiltro_precio(ml_pre)
    retail_pre = _prefiltro_precio(retail_pre)
    detalles = ml_pre + retail_pre

    # Ordenar por precio ascendente
    detalles = sorted(detalles, key=lambda x: x.get("precio", 999999))

    # --- Filtro de generación (determinista): descarta generaciones distintas
    #     a la buscada (ej: 4ta o 3ra cuando se busca 5ta). ---
    detalles = _filtrar_generacion(detalles, nombre_base)

    # --- Filtro con IA (Gemini) como refinamiento: ya recibe lista limpia ---
    if detalles and (tiene_marca or tiene_modelo or nombre_base):
        try:
            detalles = filtrar_resultados_con_ia(nombre_base, contexto, detalles)
        except Exception:
            pass  # Si la IA falla, se mantienen los resultados sin filtrar

        # ===== Selección final: 5 de Mercado Libre + 5 de retail prioritario =====
    return separar_ml_retail(detalles, max_resultados)
