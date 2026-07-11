"""
logistica.py — Estimación de costos de envío. Usa la Tarifa Simple REAL de Starken
como ancla (única tabla pública completa) y calibra los otros couriers según su
posición de mercado 2026. Determinista: sin IA, instantáneo y consistente.
Para el precio exacto de cualquier courier, el cotizador oficial manda (links abajo).
"""
import unicodedata

# Tarifa Simple Starken — envío a DOMICILIO (IVA incl., valor declarado hasta
# $50.000). Fuente: somospartner.cl/tarifa-simple (ref. mar-2026, sujeta a cambios).
# Tramos: XS <=0,5kg | S <=3kg | M <=6kg | L <=10kg.
_STARKEN = {
    "misma_ciudad":    {"XS": 2820, "S": 3820, "M": 4510,  "L": 5180},
    "regional":        {"XS": 3910, "S": 5100, "M": 6880,  "L": 8830},
    "extremo_norte":   {"XS": 4740, "S": 8650, "M": 13640, "L": 16340},
    "extremo_austral": {"XS": 5000, "S": 9100, "M": 14010, "L": 17230},
}

# Multiplicadores por courier vs Starken (calibrados con rangos de mercado 2026):
# Starken $2.500-7.500 · Correos $3.000-8.000 (barato a zonas apartadas, lento) ·
# Blue Express $4.000-10.000 (punto más barato) · Chilexpress $5.000-12.000 (caro, rápido).
_MULT = {
    "Blue Express":     (1.00, 1.25),
    "Chilexpress":      (1.20, 1.50),
    "Correos de Chile": (0.95, 1.15),   # se ajusta más barato a zonas extremas
}

_ZONA_NORTE = {"arica", "iquique", "alto hospicio", "antofagasta", "calama",
               "tocopilla", "mejillones", "pozo almonte", "huara"}
_ZONA_AUSTRAL = {"coyhaique", "punta arenas", "puerto natales", "puerto aysen",
                 "puerto aisen", "puerto williams", "cochrane"}

_COTIZADORES = [
    {"nombre": "Starken", "url": "https://www.starken.cl/newCotizador"},
    {"nombre": "Chilexpress", "url": "https://www.chilexpress.cl/cotizar-tarifas-envios-chile-extranjero"},
    {"nombre": "Blue Express", "url": "https://www.blue.cl/"},
    {"nombre": "Correos de Chile", "url": "https://www.correos.cl/cotizador"},
]


def _norm(txt):
    t = (txt or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


def _zona(ciudad):
    c = _norm(ciudad)
    if any(n in c for n in _ZONA_NORTE):
        return "norte"
    if any(a in c for a in _ZONA_AUSTRAL):
        return "austral"
    return "centro"


def _tramo_peso(kg):
    if kg <= 0.5:
        return "XS"
    if kg <= 3:
        return "S"
    if kg <= 6:
        return "M"
    if kg <= 10:
        return "L"
    return None


def _ruta(origen, destino):
    co, cd = _norm(origen), _norm(destino)
    if co and cd and co == cd:
        return "misma_ciudad"
    zo, zd = _zona(origen), _zona(destino)
    if zo == zd:
        return "regional"
    if "austral" in (zo, zd):
        return "extremo_austral"
    if "norte" in (zo, zd):
        return "extremo_norte"
    return "regional"


def _clp(n):
    return f"${int(round(n / 10.0) * 10):,}".replace(",", ".")


def _rango(lo, hi):
    return f"{_clp(lo)} - {_clp(hi)}"


def estimar_envio(origen, destino, peso_kg, largo_cm=0, ancho_cm=0, alto_cm=0):
    """Estima el costo de envío de cada courier anclado a la Tarifa Simple de Starken."""
    if not origen or not destino:
        return {"error": "Falta origen o destino."}
    if not peso_kg or peso_kg <= 0:
        return {"error": "Falta el peso del paquete."}

    peso_vol = 0.0
    if largo_cm and ancho_cm and alto_cm:
        peso_vol = (largo_cm * ancho_cm * alto_cm) / 4000.0
    peso_facturable = max(float(peso_kg), peso_vol)

    ruta = _ruta(origen, destino)
    tramo = _tramo_peso(peso_facturable)
    es_extremo = ruta in ("extremo_norte", "extremo_austral")

    nombres_ruta = {
        "misma_ciudad": "dentro de la misma ciudad",
        "regional": "dentro de la misma zona (regional)",
        "extremo_norte": "cruzando hacia/desde el extremo norte",
        "extremo_austral": "cruzando hacia/desde el extremo austral",
    }
    detalle_peso = (f"{peso_facturable:.1f} kg facturables"
                    + (f", el volumétrico ({peso_vol:.1f} kg) manda"
                       if peso_vol > float(peso_kg) else ""))

    if tramo is None:
        couriers = [{"nombre": n, "costo_estimado": "Cotizar (>10 kg)",
                     "tiempo_estimado": t, "nota": nota}
                    for n, t, nota in [
                        ("Starken", "2-4 días hábiles",
                         "Sobre 10 kg queda fuera de la Tarifa Simple. Cotiza el peso exacto."),
                        ("Chilexpress", "1-3 días hábiles", ""),
                        ("Blue Express", "2-4 días hábiles",
                         "Blue Express solo despacha hasta talla L (10 kg / 60 cm)."),
                        ("Correos de Chile", "3-6 días hábiles", "")]]
        return {
            "couriers": couriers, "mas_economico": "Starken", "mas_rapido": "Chilexpress",
            "recomendacion": (f"Paquete de {detalle_peso}: supera los 10 kg de la Tarifa "
                              f"Simple. Cotiza el peso exacto en los links de abajo."),
            "consejo": "Sobre 10 kg cada courier cobra distinto; compara en sus cotizadores.",
            "cotizadores": _COTIZADORES, "_modelo": "tabla-starken",
        }

    base = _STARKEN[ruta][tramo]

    if ruta == "misma_ciudad":
        t_std, t_lento, t_rapido = "1 día hábil", "1-2 días hábiles", "mismo día o 1 día"
    elif ruta == "regional":
        t_std, t_lento, t_rapido = "1-2 días hábiles", "2-3 días hábiles", "1 día hábil"
    else:
        t_std, t_lento, t_rapido = "2-4 días hábiles", "3-5 días hábiles", "1-2 días hábiles"

    # Starken (ancla real): a sucursal ~8% más barato que a domicilio
    starken = {"nombre": "Starken", "costo_estimado": _rango(base * 0.92, base),
               "tiempo_estimado": t_std,
               "nota": "Tarifa Simple real de Starken (IVA incl.). A sucursal es más barato."}

    # Correos: más barato a zonas apartadas, pero el más lento
    if es_extremo:
        co_lo, co_hi = base * 0.70, base * 0.95
        co_nota = "Suele ser el más barato a zonas apartadas, pero el más lento."
    else:
        co_lo, co_hi = _MULT["Correos de Chile"]
        co_lo, co_hi = base * co_lo, base * co_hi
        co_nota = "Tarifas bajas, pero es el más lento. Estimación referencial."
    correos = {"nombre": "Correos de Chile", "costo_estimado": _rango(co_lo, co_hi),
               "tiempo_estimado": t_lento, "nota": co_nota}

    bl_lo, bl_hi = _MULT["Blue Express"]
    blue = {"nombre": "Blue Express", "costo_estimado": _rango(base * bl_lo, base * bl_hi),
            "tiempo_estimado": t_std,
            "nota": "En Punto Blue baja; a domicilio sube. Estimación referencial."}

    cx_lo, cx_hi = _MULT["Chilexpress"]
    chilex = {"nombre": "Chilexpress", "costo_estimado": _rango(base * cx_lo, base * cx_hi),
              "tiempo_estimado": t_rapido,
              "nota": "El más caro, pero de los más rápidos. Estimación referencial."}

    couriers = [starken, correos, blue, chilex]
    mas_eco = "Correos de Chile" if es_extremo else "Starken"

    reco = (f"Envío {nombres_ruta.get(ruta, ruta)}, tramo {tramo} ({detalle_peso}). "
            + ("A zonas apartadas, Correos suele ser lo más barato (pero lento); "
               "si necesitas rapidez, Chilexpress. "
               if es_extremo else
               f"Para lo tuyo, Starken es lo más barato y directo (~{_rango(base * 0.92, base)}). ")
            + "Solo Starken tiene tarifa pública fija; el resto es estimación calibrada.")
    consejo = ("Estos valores son referenciales (ancla: Tarifa Simple Starken, mar-2026). "
               "Para el precio EXACTO de cada courier, usa su cotizador oficial (abajo). "
               "Tip: despachar a sucursal/punto en vez de a domicilio siempre sale más barato.")

    return {
        "couriers": couriers, "mas_economico": mas_eco, "mas_rapido": "Chilexpress",
        "recomendacion": reco, "consejo": consejo,
        "cotizadores": _COTIZADORES, "_modelo": "tabla-starken",
    }
