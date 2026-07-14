"""
guardados.py — Persistencia de productos guardados en Google Sheets.

Antes se guardaba en un archivo local (guardados.json), pero en Streamlit
Cloud el disco se borra al reiniciar la app. Ahora se usa una planilla de
Google Sheets, autenticada con la misma cuenta de servicio que usa Vision
(GOOGLE_VISION_JSON en config.py).

Los nombres y firmas de las funciones públicas se mantienen exactamente
iguales a los de la versión anterior para no romper app.py ni ui.py.
"""
import json
import os
import time as _t

import streamlit as st
import gspread
from google.oauth2 import service_account

from config import GOOGLE_VISION_JSON, GOOGLE_VISION_JSON_CONTENT, GOOGLE_SHEET_ID

_COLUMNAS_PRODUCTO = ["titulo", "fuente", "precio", "link", "imagen", "categoria", "_guardado_en"]
# Columnas del análisis de rentabilidad (calculadora de la sección Guardados).
# Quedan vacías para los productos que todavía no se analizaron.
_COLUMNAS_ANALISIS = ["precio_compra", "precio_referencia_manual", "iva_pct", "margen_pct",
                      "costo_envio", "precio_sugerido", "ganancia_pesos", "ganancia_pct",
                      "analisis_guardado_en"]
_COLUMNAS = _COLUMNAS_PRODUCTO + _COLUMNAS_ANALISIS

# Columnas numéricas: se convierten con _a_numero al leer (None si vienen vacías).
_COLUMNAS_NUMERICAS = ["precio", "precio_compra", "precio_referencia_manual", "iva_pct",
                       "margen_pct", "costo_envio", "precio_sugerido", "ganancia_pesos",
                       "ganancia_pct"]

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _credenciales_sheets():
    """Construye las credenciales de la cuenta de servicio en memoria (nunca
    le pasa una ruta de archivo a gspread), igual que necesita funcionar tanto
    en local como en Streamlit Cloud:
    - En local: si existe el archivo GOOGLE_VISION_JSON, se lee su contenido.
    - En la nube: no hay archivo en disco, así que se usa directamente el
      contenido del secret GOOGLE_VISION_JSON_CONTENT (mismo secret que usa
      config.py para reconstruir las credenciales de Vision)."""
    info = None
    if GOOGLE_VISION_JSON and os.path.exists(GOOGLE_VISION_JSON):
        with open(GOOGLE_VISION_JSON, "r", encoding="utf-8") as f:
            info = json.load(f)
    elif GOOGLE_VISION_JSON_CONTENT:
        info = json.loads(GOOGLE_VISION_JSON_CONTENT)

    if not info:
        raise RuntimeError(
            "No hay credenciales de Google disponibles (ni archivo local "
            "GOOGLE_VISION_JSON ni secret GOOGLE_VISION_JSON_CONTENT).")
    return service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)


@st.cache_resource(show_spinner=False)
def _obtener_hoja():
    """Abre la planilla (cuenta de servicio de Vision + GOOGLE_SHEET_ID) y
    devuelve la primera hoja. La conexión queda cacheada entre llamadas."""
    creds = _credenciales_sheets()
    cliente = gspread.authorize(creds)
    hoja = cliente.open_by_key(GOOGLE_SHEET_ID).sheet1
    if not hoja.get_all_values():
        hoja.append_row(_COLUMNAS, value_input_option="RAW")
    return hoja


def _a_numero(valor):
    """Convierte el precio a número cuando se pueda (int si es un entero
    exacto, para no romper el formato "$1.234" que usa el resto de la app)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, int):
        return valor
    try:
        num = float(valor)
    except (TypeError, ValueError):
        return None
    return int(num) if num == int(num) else num


def _fila_a_dict(fila: dict) -> dict:
    item = dict(fila)
    for col in _COLUMNAS_NUMERICAS:
        if col in item:
            item[col] = _a_numero(item.get(col))
    return item


def cargar_guardados() -> list:
    """Lee la lista de productos guardados desde Google Sheets (más reciente primero).

    Pide UNFORMATTED_VALUE explícitamente: si una celda quedó con formato de
    Porcentaje o de miles (por ejemplo por un formato de columna heredado de
    antes), FORMATTED_VALUE (el default de gspread) devuelve el número ya
    multiplicado/formateado para mostrar, no el valor real guardado. Con
    UNFORMATTED_VALUE siempre se obtiene el número crudo, sin importar el
    formato de la celda."""
    try:
        hoja = _obtener_hoja()
        filas = hoja.get_all_records(value_render_option="UNFORMATTED_VALUE")
        return [_fila_a_dict(f) for f in filas]
    except Exception as e:
        st.error(f"No se pudo leer Google Sheets: {e}")
        return []


def _escribir_guardados(lista: list) -> bool:
    """Reescribe toda la hoja con la lista dada (borra todo y vuelve a
    escribir encabezado + filas, en el mismo orden que trae la lista).

    Usa value_input_option="RAW" explícitamente: así Sheets guarda los números
    tal cual, sin intentar "interpretarlos" como haría con una entrada de
    usuario (que puede aplicar formato de miles/porcentaje según la columna)."""
    try:
        hoja = _obtener_hoja()
        hoja.clear()
        hoja.append_row(_COLUMNAS, value_input_option="RAW")
        if lista:
            filas = [[item.get(c, "") if item.get(c) is not None else ""
                      for c in _COLUMNAS] for item in lista]
            hoja.append_rows(filas, value_input_option="RAW")
        return True
    except Exception as e:
        st.error(f"No se pudo guardar en Google Sheets: {e}")
        return False


def guardar_producto(item: dict) -> bool:
    """Agrega un producto a los guardados (evita duplicados, máximo 50)."""
    lista = cargar_guardados()
    clave_nueva = (item.get("link", ""), item.get("precio"))
    for g in lista:
        if (g.get("link", ""), g.get("precio")) == clave_nueva:
            return False  # ya estaba guardado
    item_guardar = dict(item)
    item_guardar["_guardado_en"] = _t.strftime("%Y-%m-%d %H:%M")
    lista.insert(0, item_guardar)  # el más reciente primero
    lista = lista[:50]  # límite de 50 guardados (descarta los más antiguos)
    return _escribir_guardados(lista)


def eliminar_guardado(link: str, precio) -> bool:
    """Elimina un producto guardado por su link y precio."""
    lista = cargar_guardados()
    nueva = [g for g in lista if not (g.get("link", "") == link and g.get("precio") == precio)]
    if len(nueva) != len(lista):
        return _escribir_guardados(nueva)
    return False


def guardar_analisis(link: str, precio, datos_analisis: dict) -> bool:
    """Actualiza SOLO las columnas del análisis de rentabilidad (_COLUMNAS_ANALISIS)
    de un producto ya guardado, identificado por link+precio. No crea una fila
    nueva: busca la fila existente y la actualiza. datos_analisis puede traer
    cualquier subconjunto de las columnas de análisis; el resto queda igual."""
    try:
        lista = cargar_guardados()
        encontrado = False
        for g in lista:
            if g.get("link", "") == link and g.get("precio") == precio:
                for col in _COLUMNAS_ANALISIS:
                    if col in datos_analisis:
                        g[col] = datos_analisis[col]
                g["analisis_guardado_en"] = _t.strftime("%Y-%m-%d %H:%M")
                encontrado = True
                break
        if not encontrado:
            return False
        return _escribir_guardados(lista)
    except Exception as e:
        st.error(f"No se pudo guardar el análisis: {e}")
        return False


def selector_guardado(key_prefix, label="O elige un producto guardado:"):
    """
    Muestra un desplegable con los productos guardados. Devuelve el producto
    seleccionado (dict) o None. Reutilizable en Logística y Campañas.
    """
    guardados = cargar_guardados()
    if not guardados:
        return None

    # Construir opciones legibles: "Producto — Tienda — $precio"
    opciones = ["— Ninguno —"]
    for g in guardados:
        titulo = (g.get("titulo", "") or "")[:45]
        tienda = g.get("fuente", "")
        precio = g.get("precio")
        precio_txt = f"${precio:,}".replace(",", ".") if precio else ""
        etiqueta = f"{titulo} — {tienda} — {precio_txt}".strip(" —")
        opciones.append(etiqueta)

    seleccion = st.selectbox(label, opciones, key=f"{key_prefix}_sel_guardado")
    idx = opciones.index(seleccion)
    if idx == 0:
        return None
    return guardados[idx - 1]  # -1 porque el primero es "Ninguno"
