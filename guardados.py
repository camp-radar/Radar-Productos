"""
guardados.py — Persistencia de productos guardados en Google Sheets.

Antes se guardaba en un archivo local (guardados.json), pero en Streamlit
Cloud el disco se borra al reiniciar la app. Ahora se usa una planilla de
Google Sheets, autenticada con la misma cuenta de servicio que usa Vision
(GOOGLE_VISION_JSON en config.py).

Los nombres y firmas de las funciones públicas se mantienen exactamente
iguales a los de la versión anterior para no romper app.py ni ui.py.
"""
import time as _t

import streamlit as st
import gspread
from google.oauth2 import service_account

from config import GOOGLE_VISION_JSON, GOOGLE_SHEET_ID

_COLUMNAS = ["titulo", "fuente", "precio", "link", "imagen", "categoria", "_guardado_en"]
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


@st.cache_resource(show_spinner=False)
def _obtener_hoja():
    """Abre la planilla (cuenta de servicio de Vision + GOOGLE_SHEET_ID) y
    devuelve la primera hoja. La conexión queda cacheada entre llamadas."""
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_VISION_JSON, scopes=_SCOPES)
    cliente = gspread.authorize(creds)
    hoja = cliente.open_by_key(GOOGLE_SHEET_ID).sheet1
    if not hoja.get_all_values():
        hoja.append_row(_COLUMNAS)
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
    item["precio"] = _a_numero(item.get("precio"))
    return item


def cargar_guardados() -> list:
    """Lee la lista de productos guardados desde Google Sheets (más reciente primero)."""
    try:
        hoja = _obtener_hoja()
        filas = hoja.get_all_records()
        return [_fila_a_dict(f) for f in filas]
    except Exception as e:
        st.error(f"No se pudo leer Google Sheets: {e}")
        return []


def _escribir_guardados(lista: list) -> bool:
    """Reescribe toda la hoja con la lista dada (borra todo y vuelve a
    escribir encabezado + filas, en el mismo orden que trae la lista)."""
    try:
        hoja = _obtener_hoja()
        hoja.clear()
        hoja.append_row(_COLUMNAS)
        if lista:
            filas = [[item.get(c, "") if item.get(c) is not None else ""
                      for c in _COLUMNAS] for item in lista]
            hoja.append_rows(filas)
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
