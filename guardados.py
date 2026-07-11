"""
guardados.py — Persistencia local de productos guardados (guardados.json).
"""
import json
from pathlib import Path as _Path

import streamlit as st

_ARCHIVO_GUARDADOS = _Path(__file__).parent / "guardados.json"


def cargar_guardados() -> list:
    """Lee la lista de productos guardados desde el archivo local."""
    try:
        if _ARCHIVO_GUARDADOS.exists():
            with open(_ARCHIVO_GUARDADOS, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _escribir_guardados(lista: list) -> bool:
    """Escribe la lista de guardados al archivo local."""
    try:
        with open(_ARCHIVO_GUARDADOS, "w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def guardar_producto(item: dict) -> bool:
    """Agrega un producto a los guardados (evita duplicados, máximo 50)."""
    lista = cargar_guardados()
    clave_nueva = (item.get("link", ""), item.get("precio"))
    for g in lista:
        if (g.get("link", ""), g.get("precio")) == clave_nueva:
            return False  # ya estaba guardado
    import time as _t
    item_guardar = dict(item)
    item_guardar["_guardado_en"] = _t.strftime("%Y-%m-%d %H:%M")
    lista.insert(0, item_guardar)  # el más reciente primero
    lista = lista[:50]  # límite de 50 guardados (descarta los más antiguos)
    _escribir_guardados(lista)
    return True


def eliminar_guardado(link: str, precio) -> bool:
    """Elimina un producto guardado por su link y precio."""
    lista = cargar_guardados()
    nueva = [g for g in lista if not (g.get("link", "") == link and g.get("precio") == precio)]
    if len(nueva) != len(lista):
        _escribir_guardados(nueva)
        return True
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
