"""
Radar Inteligente de Productos — app.py (entrada principal).
Navegación, estilos y las 4 secciones (Radar, Guardados, Logística, Campañas).
La lógica vive en los módulos: config, utils, ia, busqueda, vision, guardados,
logistica, campanas, ui.
Correr con:  streamlit run app.py
"""
import hashlib

import streamlit as st

from config import ZONAS_CHILE, OBJETIVOS_META
from guardados import (cargar_guardados, _escribir_guardados, eliminar_guardado,
                       guardar_producto, selector_guardado)
from busqueda import buscar_producto
from vision import (image_input_pipeline, detectar_identidad_imagen,
                    verificar_y_enriquecer)
import lens
from logistica import estimar_envio
from campanas import generar_campana, _regiones_seleccionadas_a_texto
from ui import (_card_producto_html, render_grid_ml, render_identidad, _esc,
                _render_campana, render_producto_exacto)


st.set_page_config(
    page_title="Radar Inteligente de Productos",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==============================================================================
# BLOQUEO DE ACCESO CON CONTRASEÑA
# ==============================================================================
def _pedir_password():
    """Pide contraseña para entrar. La contraseña se define en el secret
    APP_PASSWORD (nube) o en el .env (local). Si no hay ninguna, no bloquea
    (cómodo para probar en tu PC)."""
    pwd = ""
    try:
        if "APP_PASSWORD" in st.secrets:
            pwd = str(st.secrets["APP_PASSWORD"])
    except Exception:
        pwd = ""
    if not pwd:
        import os as _os
        pwd = _os.getenv("APP_PASSWORD", "")
    if not pwd:
        return  # sin contraseña configurada -> no bloquea
    if st.session_state.get("_auth_ok"):
        return
    st.markdown("## 🔒 Radar de Productos")
    st.caption("Ingresa la contraseña para acceder.")
    intento = st.text_input("Contraseña", type="password", label_visibility="collapsed")
    if intento:
        if intento == pwd:
            st.session_state["_auth_ok"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    st.stop()


_pedir_password()

# ==============================================================================
# SESSION STATE
# ==============================================================================
_DEFAULTS = {
    "seccion_activa": "radar",
    "radar_resultado": None,
    "radar_query": "",
    "radar_deteccion": None,
    "radar_hash_img": None,
    "radar_modulo4": None,
    "radar_lens": None,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==============================================================================
# ESTILOS — SaaS Premium
# ==============================================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; }

    .main .block-container { padding-top: 2rem; padding-bottom: 3.5rem; max-width: 1200px; }

    .stApp { background: #f8fafc; }

    /* ============ SIDEBAR ============ */
    section[data-testid="stSidebar"] {
        background: #0f172a;
        border-right: 1px solid rgba(148,163,184,0.1);
    }
    section[data-testid="stSidebar"] * { color: #cbd5e1; }
    .sidebar-brand {
        padding: 0.6rem 0.5rem 1.4rem; border-bottom: 1px solid rgba(148,163,184,0.12);
        margin-bottom: 1.2rem;
    }
    .sidebar-brand h2 {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 1.2rem; font-weight: 800; margin: 0; color: #fff; letter-spacing: -0.5px;
    }
    .sidebar-brand span { font-size: 0.76rem; color: #64748b; font-weight: 500; }

    section[data-testid="stSidebar"] .stButton > button {
        width: 100%; background: transparent; border: 0; border-radius: 10px;
        padding: 0.72rem 0.9rem; font-weight: 500; font-size: 0.94rem; color: #94a3b8;
        box-shadow: none; justify-content: flex-start !important; text-align: left !important;
        transition: all 0.18s ease;
    }
    section[data-testid="stSidebar"] .stButton > button > div,
    section[data-testid="stSidebar"] .stButton > button > div > p,
    section[data-testid="stSidebar"] .stButton > button p {
        text-align: left !important; justify-content: flex-start !important;
        width: 100% !important; margin: 0 !important;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(148,163,184,0.08); color: #f1f5f9; transform: none; box-shadow: none;
    }
    section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: rgba(99,102,241,0.15); color: #fff; box-shadow: inset 3px 0 0 #6366f1;
        font-weight: 600;
    }

    /* ============ HERO ============ */
    .hero {
        background: #fff;
        border: 1px solid #eef1f6; border-radius: 20px;
        padding: 1.6rem 2rem; margin-bottom: 1.5rem;
        box-shadow: 0 1px 3px rgba(15,23,42,0.04);
    }
    .hero h1 {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 1.6rem; font-weight: 800; letter-spacing: -0.8px; margin: 0 0 0.3rem 0;
        color: #0f172a;
    }
    .hero p { color: #64748b; font-size: 0.95rem; margin: 0; line-height: 1.5; }

    /* ============ PANEL ============ */
    .panel {
        background: #fff; border: 1px solid #eef1f6;
        border-radius: 18px; padding: 1.5rem 1.7rem;
        box-shadow: 0 1px 3px rgba(15,23,42,0.04);
        margin-bottom: 1.3rem;
    }
    .sec-title {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 1.05rem; font-weight: 700; color: #0f172a; margin-bottom: 0.25rem; letter-spacing: -0.3px;
    }
    .sec-sub { color: #64748b; font-size: 0.88rem; margin-bottom: 0; line-height: 1.5; }

    /* ============ INPUTS ============ */
    .stTextInput input, .stNumberInput input,
    .stSelectbox div[data-baseweb="select"] > div,
    .stTextArea textarea {
        border-radius: 10px !important; border: 1px solid #e2e8f0 !important;
        background: #fff !important; transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus,
    .stTextArea textarea:focus {
        border-color: #6366f1 !important; box-shadow: 0 0 0 3px rgba(99,102,241,0.1) !important;
    }
    .stTextInput label, .stNumberInput label, .stSelectbox label, .stTextArea label {
        font-weight: 600 !important; font-size: 0.86rem !important; color: #334155 !important;
    }

    /* ============ BOTONES PRINCIPALES ============ */
    .main .stButton > button {
        width: 100%; border-radius: 10px; padding: 0.62rem 1rem; font-weight: 600; border: 0;
        background: #4f46e5; color: white; font-size: 0.92rem;
        box-shadow: 0 1px 2px rgba(79,70,229,0.2);
        transition: all 0.16s ease;
    }
    .main .stButton > button:hover {
        background: #4338ca; transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(79,70,229,0.25);
    }

    /* ============ IDENTIDAD DETECTADA ============ */
    .ident-card {
        background: #fafbff;
        border: 1px solid #e8eaf6; border-radius: 14px;
        padding: 1.2rem 1.4rem; margin-bottom: 1.1rem;
    }
    .ident-row { font-size: 0.92rem; color: #475569; margin-bottom: 0.3rem; }
    .ident-row b { color: #1e293b; font-weight: 600; }
    .ident-desc { font-size: 0.9rem; color: #64748b; margin-top: 0.6rem; line-height: 1.55; }

    /* ============ GRID DE PRODUCTOS ============ */
    .ml-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.8rem; margin-top: 0.4rem; }
    .ml-card {
        background: #fff; border: 1px solid #eef1f6; border-radius: 14px;
        overflow: hidden; transition: all 0.18s ease; display: flex; flex-direction: column;
        box-shadow: 0 1px 2px rgba(15,23,42,0.03);
    }
    .ml-card:hover { box-shadow: 0 8px 24px rgba(15,23,42,0.10); transform: translateY(-3px); border-color: #e0e3ee; }
    .ml-card-img { width: 100%; height: 140px; background: #f8fafc; display: flex; align-items: center; justify-content: center; overflow: hidden; border-bottom: 1px solid #f1f5f9; }
    .ml-card-img img { width: 100%; height: 100%; object-fit: contain; padding: 10px; }
    .ml-card-body { padding: 0.8rem 0.9rem 0.9rem; display: flex; flex-direction: column; flex: 1; }
    .ml-card-price {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 1.15rem; font-weight: 800; color: #0f172a; letter-spacing: -0.5px; margin-bottom: 0.3rem;
    }
    .ml-card-store { font-size: 0.68rem; font-weight: 700; color: #6366f1; text-transform: uppercase; letter-spacing: 0.4px; margin-bottom: 0.4rem; height: 1.5rem; line-height: 0.78rem; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .ml-card-title { font-size: 0.78rem; color: #64748b; line-height: 1.4; margin-bottom: 0.7rem; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; height: 2.2rem; }
    .ml-card-btn {
        display: block; text-align: center; font-size: 0.76rem; font-weight: 600; color: #fff;
        background: #4f46e5; border-radius: 8px;
        padding: 0.45rem 0.5rem; text-decoration: none; margin-top: auto;
        transition: background 0.15s ease;
    }
    .ml-card-btn:hover { background: #4338ca; }
    .grid-title {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 1rem; font-weight: 700; color: #0f172a; margin: 0.6rem 0 0.7rem; letter-spacing: -0.3px;
        display: flex; align-items: center; gap: 0.5rem;
    }

    @media (max-width: 1200px) { .ml-grid { grid-template-columns: repeat(3, 1fr); } }
    @media (max-width: 700px) { .ml-grid { grid-template-columns: repeat(2, 1fr); } }

    .empty-hint { text-align: center; padding: 2.4rem 1rem 0.8rem; color: #94a3b8; }
    .empty-hint .icon { font-size: 2.6rem; margin-bottom: 0.7rem; opacity: 0.7; }
    .empty-hint b { color: #475569; font-weight: 600; }

    /* ============ CAMPAÑAS ============ */
    .camp-block {
        background: #fff; border: 1px solid #eef1f6; border-radius: 14px;
        padding: 1.2rem 1.4rem; margin-bottom: 1rem;
        box-shadow: 0 1px 2px rgba(15,23,42,0.03);
    }
    .camp-h {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 0.9rem; font-weight: 700; color: #4f46e5;
        margin-bottom: 0.6rem; letter-spacing: -0.2px; text-transform: uppercase; font-size: 0.8rem;
    }
    .camp-text { font-size: 0.92rem; color: #475569; line-height: 1.55; }
    .camp-big { font-size: 1.05rem; font-weight: 600; color: #1e293b; }
    .camp-pre { white-space: pre-wrap; }
    .camp-copy {
        background: #f8fafc; border-left: 3px solid #6366f1;
        padding: 0.75rem 0.95rem; border-radius: 8px; margin-top: 0.3rem;
    }
    .camp-meta { display: flex; gap: 1.3rem; margin: 0.7rem 0; font-size: 0.85rem; color: #64748b; }
    .camp-chips { display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 0.55rem; }
    .camp-chip {
        background: #eef2ff; color: #4338ca; font-size: 0.77rem; font-weight: 600;
        padding: 0.24rem 0.75rem; border-radius: 999px; border: 1px solid #e0e7ff;
    }
    .camp-pain { border-left: 4px solid #f43f5e; }
    .camp-desire { border-left: 4px solid #10b981; }
    .camp-value {
        background: #fafbff;
        border: 1px solid #e8eaf6;
    }
    .camp-offer { background: #fffdf7; border: 1px solid #fdefd0; }
    .camp-list { margin: 0; padding-left: 1.2rem; }
    .camp-list li { font-size: 0.92rem; color: #475569; line-height: 1.65; margin-bottom: 0.25rem; }
    .camp-hook {
        background: #f8fafc; border-radius: 9px; padding: 0.6rem 0.85rem;
        margin-bottom: 0.5rem; font-size: 0.9rem; color: #475569; display: flex; align-items: center; gap: 0.65rem;
    }
    .camp-num {
        background: #4f46e5; color: #fff; font-weight: 700;
        font-size: 0.76rem; min-width: 1.5rem; height: 1.5rem; border-radius: 50%;
        display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
    }
    .camp-angle {
        background: #f8fafc; border-radius: 9px; padding: 0.65rem 0.9rem;
        margin-bottom: 0.55rem; font-size: 0.9rem; color: #475569; line-height: 1.5;
    }
    .camp-meta-header {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 1.1rem; font-weight: 800; color: #0f172a;
        margin: 1.7rem 0 1rem; padding-bottom: 0.55rem;
        border-bottom: 2px solid #eef2ff; letter-spacing: -0.4px;
    }
    .camp-segment { border-left: 4px solid #6366f1; }
    .camp-seg-grid {
        display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-top: 0.65rem;
    }
    .camp-seg-item {
        background: #f8fafc; border-radius: 9px; padding: 0.65rem 0.85rem;
        font-size: 0.9rem; color: #1e293b; border: 1px solid #f1f5f9;
    }
    .camp-seg-label {
        display: block; font-size: 0.7rem; font-weight: 700; color: #6366f1;
        text-transform: uppercase; letter-spacing: 0.4px; margin-bottom: 0.25rem;
    }
    .camp-chip-alt { background: #eff6ff; color: #1d4ed8; border-color: #dbeafe; }

    /* ============ LOGÍSTICA ============ */
    .log-courier {
        background: #fff; border: 1px solid #eef1f6; border-radius: 14px;
        padding: 1.1rem 1.3rem; margin-bottom: 0.85rem;
        box-shadow: 0 1px 2px rgba(15,23,42,0.03);
        transition: box-shadow 0.16s ease;
    }
    .log-courier:hover { box-shadow: 0 6px 18px rgba(15,23,42,0.08); }
    .log-courier-head {
        display: flex; align-items: center; gap: 0.7rem; margin-bottom: 0.75rem;
    }
    .log-courier-name {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 1.02rem; font-weight: 700; color: #0f172a;
    }
    .log-badge {
        font-size: 0.7rem; font-weight: 700; padding: 0.22rem 0.65rem; border-radius: 999px;
    }
    .log-badge-eco { background: #ecfdf5; color: #059669; border: 1px solid #d1fae5; }
    .log-badge-fast { background: #fffbeb; color: #d97706; border: 1px solid #fef3c7; }
    .log-courier-body { display: flex; gap: 2.2rem; }
    .log-stat { display: flex; flex-direction: column; }
    .log-stat-label {
        font-size: 0.7rem; font-weight: 600; color: #94a3b8;
        text-transform: uppercase; letter-spacing: 0.4px; margin-bottom: 0.2rem;
    }
    .log-stat-val {
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 1rem; font-weight: 700; color: #4f46e5;
    }
    .log-note {
        margin-top: 0.65rem; font-size: 0.83rem; color: #64748b;
        background: #f8fafc; padding: 0.55rem 0.75rem; border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# SIDEBAR
# ==============================================================================
SECCIONES = [
    ("radar", "🔎  Radar"),
    ("logistica", "🚚  Logística"),
    ("campanas", "🎯  Laboratorio de Campañas"),
]

with st.sidebar:
    st.markdown("""
        <div class="sidebar-brand">
            <h2>🚀 Radar IA</h2>
            <span>Investigación de productos</span>
        </div>
    """, unsafe_allow_html=True)
    for clave, etiqueta in SECCIONES:
        activo = st.session_state["seccion_activa"] == clave
        if st.button(etiqueta, key=f"nav_{clave}", use_container_width=True,
                     type="primary" if activo else "secondary"):
            st.session_state["seccion_activa"] = clave
            st.rerun()

seccion = st.session_state["seccion_activa"]


if seccion == "radar":
    st.markdown("""
    <div class="hero">
        <h1>🔎 Radar de productos</h1>
        <p>Busca por nombre o sube una imagen para identificar el producto y ver precios en el mercado chileno.</p>
    </div>
    """, unsafe_allow_html=True)

    # --- Aviso de fuente de precios ---
    st.caption("💡 Los precios se obtienen de Google Shopping (múltiples tiendas chilenas: Falabella, Paris, Mercado Libre, Sodimac y más).")

    col_texto, col_imagen = st.columns([1.4, 1], gap="large")

    with col_texto:
        with st.container(border=True):
            st.markdown('<div class="sec-title">Buscar por nombre</div>', unsafe_allow_html=True)
            st.markdown('<div class="sec-sub">Escribe el nombre del producto y presiona buscar.</div>', unsafe_allow_html=True)
            query = st.text_input("Nombre del producto", key="input_radar_texto",
                                  placeholder="Ej: Audífonos JBL, Aspiradora inalámbrica, Lámpara solar",
                                  label_visibility="collapsed")
            buscar = st.button("🔍 Buscar producto", key="btn_radar_buscar")

    with col_imagen:
        with st.container(border=True):
            st.markdown('<div class="sec-title">Buscar por imagen</div>', unsafe_allow_html=True)
            st.markdown('<div class="sec-sub">Sube una foto del producto.</div>', unsafe_allow_html=True)
            imagen_subida = st.file_uploader("Imagen", type=["jpg", "jpeg", "png", "webp"],
                                             key="uploader_radar", label_visibility="collapsed")

    # --- Lógica búsqueda por texto ---
    if buscar and query and len(query.strip()) >= 3:
        st.session_state["radar_deteccion"] = None
        st.session_state["radar_modulo4"] = None
        st.session_state["radar_lens"] = None
        with st.spinner("Buscando precios en el mercado..."):
            resultado = buscar_producto(query.strip(), contexto={}, max_resultados=5)
        st.session_state["radar_resultado"] = resultado
        st.session_state["radar_query"] = query.strip()

    # --- Lógica búsqueda por imagen ---
    if imagen_subida is not None:
        img_bytes = imagen_subida.getvalue()
        img_hash = hashlib.md5(img_bytes).hexdigest()
        if img_hash != st.session_state.get("radar_hash_img"):
            st.session_state["radar_hash_img"] = img_hash
            st.session_state["radar_resultado"] = None
            st.session_state["radar_lens"] = None
            with st.spinner("Detectando producto y buscando precios..."):
                pipeline = image_input_pipeline(imagen_subida)
                if pipeline["ok"]:
                    try:
                        with st.spinner("Buscando el producto exacto en tiendas chilenas..."):
                            resultado_lens = lens.buscar_por_imagen_lens(
                                pipeline["image_bytes_clean"])
                        st.session_state["radar_lens"] = resultado_lens
                    except Exception:
                        st.session_state["radar_lens"] = None

                    det = detectar_identidad_imagen(pipeline["image_bytes_clean"], pipeline["image_clean"])
                    if "error" not in det:
                        st.session_state["radar_deteccion"] = det
                        contexto = {
                            "categoria": det.get("categoria"),
                            "marca_probable": det.get("marca_probable", ""),
                            "modelo_probable": det.get("modelo_probable", ""),
                            "confianza_marca": det.get("confianza_marca", "Baja"),
                            "confianza_modelo": det.get("confianza_modelo", "Baja"),
                            "_es_busqueda_imagen": True,
                            "_img_usuario": pipeline.get("image_clean"),
                        }
                        nombre_base = det.get("nombre_detectado", "")
                        # No truncar: construir_consultas ya genera variantes cortas y
                        # largas internamente. Truncar aquí generaba consultas raras
                        # (ej "5.a" partido en "5 a") que perdían resultados de ML.
                        resultado = buscar_producto(nombre_base, contexto=contexto, max_resultados=5)
                        st.session_state["radar_resultado"] = resultado

                        # Módulo 4: verificación visual + enriquecimiento
                        if resultado["todos"] and pipeline.get("image_clean"):
                            with st.spinner("Refinando con verificación visual..."):
                                m4 = verificar_y_enriquecer(
                                    pipeline["image_clean"], resultado["todos"],
                                    {"nombre_base": det.get("nombre_detectado", "")})
                            st.session_state["radar_modulo4"] = m4
                            if m4.get("ok"):
                                if m4.get("nombre_comercial_sugerido"):
                                    det["nombre_detectado"] = m4["nombre_comercial_sugerido"]
                                if m4.get("descripcion_comercial_final"):
                                    det["descripcion_comercial_final"] = m4["descripcion_comercial_final"]
                                if m4.get("marca_detectada"):
                                    det["marca_probable"] = m4["marca_detectada"]
                                if m4.get("modelo_detectado"):
                                    det["modelo_probable"] = m4["modelo_detectado"]
                                if m4.get("categoria_refinada"):
                                    det["categoria"] = m4["categoria_refinada"]
                                # El resultado (5 ML + 5 retail) ya está bien calculado
                                # en buscar_producto. El Módulo 4 solo enriquece textos,
                                # no re-filtra ni re-separa (para no perder precios de ML).
                                st.session_state["radar_deteccion"] = det
                    else:
                        st.error(f"No se pudo detectar el producto: {det.get('error')}")
                else:
                    st.error("No se pudo procesar la imagen.")

    # --- Mostrar resultados ---
    det = st.session_state.get("radar_deteccion")
    resultado = st.session_state.get("radar_resultado")

    if det or resultado:
        if det:
            render_identidad(det)
        render_producto_exacto(st.session_state.get("radar_lens"))
        if resultado:
            render_grid_ml(resultado.get("top", []), resultado)

# ==============================================================================
# SECCIÓN: GUARDADOS
# ==============================================================================
elif seccion == "guardados":
    st.markdown("""
    <div class="hero">
        <h1>💾 Productos guardados</h1>
        <p>Aquí quedan los productos que guardaste para revisar más tarde.</p>
    </div>
    """, unsafe_allow_html=True)

    guardados = cargar_guardados()

    if not guardados:
        st.info("Aún no tienes productos guardados. Cuando busques en el Radar, "
                "usa el botón \"💾 Guardar\" en cada precio para tenerlos aquí.")
    else:
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown(f'<div class="sec-sub">{len(guardados)} '
                        f'producto{"s" if len(guardados) != 1 else ""} guardado'
                        f'{"s" if len(guardados) != 1 else ""}</div>',
                        unsafe_allow_html=True)
        with c2:
            if st.button("🗑️ Vaciar todo", use_container_width=True):
                _escribir_guardados([])
                st.rerun()

        por_fila = 4
        for inicio in range(0, len(guardados), por_fila):
            fila = guardados[inicio:inicio + por_fila]
            cols = st.columns(por_fila, gap="small")
            for idx, item in enumerate(fila):
                with cols[idx]:
                    st.markdown(_card_producto_html(item), unsafe_allow_html=True)
                    fecha = item.get("_guardado_en", "")
                    if fecha:
                        st.markdown(f'<div style="font-size:0.7rem;color:#9ca3af;'
                                    f'text-align:center;margin:-0.3rem 0 0.3rem;">Guardado {fecha}</div>',
                                    unsafe_allow_html=True)
                    item_idx = inicio + idx
                    if st.button("🗑️ Eliminar", key=f"del_{item_idx}", use_container_width=True):
                        eliminar_guardado(item.get("link", ""), item.get("precio"))
                        st.rerun()

# ==============================================================================
# SECCIÓN: LOGÍSTICA
# ==============================================================================
elif seccion == "logistica":
    st.markdown("""
    <div class="hero">
        <h1>🚚 Logística</h1>
        <p>Estima el costo de envío con los principales couriers de Chile según peso y destino.</p>
    </div>
    """, unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown('<div class="sec-title">Datos del envío</div>', unsafe_allow_html=True)

        # Selector de producto guardado (opcional)
        prod_log = selector_guardado("log", "📦 Analizar envío de un producto guardado (opcional):")
        if prod_log:
            pc1, pc2 = st.columns([1, 4])
            with pc1:
                img = prod_log.get("imagen", "")
                if img:
                    st.markdown(f'<img src="{img}" style="width:100%;border-radius:10px;'
                                f'border:1px solid #eee;">', unsafe_allow_html=True)
            with pc2:
                st.markdown(f"**{prod_log.get('titulo','')}**")
                st.markdown(f"<span style='color:#6366f1;font-weight:600;'>{prod_log.get('fuente','')}</span> · "
                            f"${prod_log.get('precio',0):,}".replace(",", ".") +
                            f" · Guardado {prod_log.get('_guardado_en','')}", unsafe_allow_html=True)
            st.markdown('<div style="height:0.6rem;"></div>', unsafe_allow_html=True)

        lc1, lc2 = st.columns(2, gap="medium")
        with lc1:
            log_origen = st.text_input("Origen (comuna o ciudad)", key="log_origen",
                                       placeholder="Ej: Santiago Centro")
        with lc2:
            log_destino = st.text_input("Destino (comuna o ciudad)", key="log_destino",
                                        placeholder="Ej: Concepción")

        log_peso = st.number_input("Peso del paquete (kg)", min_value=0.0, max_value=100.0,
                                   value=1.0, step=0.5, key="log_peso")

        st.markdown('<div class="sec-sub" style="margin-top:0.6rem;">Dimensiones (opcional, mejora la estimación)</div>',
                    unsafe_allow_html=True)
        dc1, dc2, dc3 = st.columns(3, gap="small")
        with dc1:
            log_largo = st.number_input("Largo (cm)", min_value=0.0, max_value=300.0,
                                        value=0.0, step=5.0, key="log_largo")
        with dc2:
            log_ancho = st.number_input("Ancho (cm)", min_value=0.0, max_value=300.0,
                                        value=0.0, step=5.0, key="log_ancho")
        with dc3:
            log_alto = st.number_input("Alto (cm)", min_value=0.0, max_value=300.0,
                                       value=0.0, step=5.0, key="log_alto")

        estimar = st.button("📦 Estimar costo de envío", key="btn_estimar_envio")

    if estimar:
        if not log_origen or not log_destino:
            st.warning("Ingresa origen y destino para estimar el envío.")
        elif log_peso <= 0:
            st.warning("Ingresa el peso del paquete.")
        else:
            with st.spinner("Estimando costos de envío con IA..."):
                est = estimar_envio(log_origen.strip(), log_destino.strip(), log_peso,
                                    log_largo, log_ancho, log_alto)
            st.session_state["envio_resultado"] = est

    est = st.session_state.get("envio_resultado")
    if est:
        if est.get("error"):
            st.error(est["error"])
        else:
            st.caption("⚠️ Estimaciones aproximadas basadas en tarifas generales del mercado, no precios oficiales. "
                       "Para cotizar exacto, consulta directamente con cada courier.")
            # Tarjetas de couriers
            couriers = est.get("couriers", [])
            mas_eco = est.get("mas_economico", "")
            mas_rap = est.get("mas_rapido", "")
            cards_html = ""
            for c in couriers:
                if not isinstance(c, dict):
                    continue
                nombre = c.get("nombre", "")
                badges = ""
                if nombre == mas_eco:
                    badges += '<span class="log-badge log-badge-eco">💰 Más económico</span>'
                if nombre == mas_rap:
                    badges += '<span class="log-badge log-badge-fast">⚡ Más rápido</span>'
                nota = c.get("nota")
                nota_html = f'<div class="log-note">{_esc(nota)}</div>' if nota else ''
                cards_html += (
                    f'<div class="log-courier">'
                    f'<div class="log-courier-head"><span class="log-courier-name">{_esc(nombre)}</span>{badges}</div>'
                    f'<div class="log-courier-body">'
                    f'<div class="log-stat"><span class="log-stat-label">Costo estimado</span><span class="log-stat-val">{_esc(c.get("costo_estimado", "-"))}</span></div>'
                    f'<div class="log-stat"><span class="log-stat-label">Tiempo</span><span class="log-stat-val">{_esc(c.get("tiempo_estimado", "-"))}</span></div>'
                    f'</div>{nota_html}</div>'
                )
            st.markdown(cards_html, unsafe_allow_html=True)

            # Recomendación y consejo
            st.markdown(f"""
<div class="camp-block camp-value">
<div class="camp-h">✅ Recomendación</div>
<div class="camp-text">{_esc(est.get('recomendacion', '-'))}</div>
</div>
<div class="camp-block camp-offer">
<div class="camp-h">💡 Consejo para ahorrar</div>
<div class="camp-text">{_esc(est.get('consejo', '-'))}</div>
</div>
""", unsafe_allow_html=True)

            cotz = est.get("cotizadores", [])
            if cotz:
                links = " &nbsp;·&nbsp; ".join(
                    f'<a href="{u.get("url", "#")}" target="_blank" '
                    f'style="color:#4f46e5;font-weight:600;text-decoration:none;">'
                    f'{_esc(u.get("nombre", ""))} ↗</a>' for u in cotz)
                st.markdown(f"""
<div class="camp-block">
<div class="camp-h">🔗 Cotizadores oficiales (precio exacto)</div>
<div class="camp-text">{links}</div>
</div>
""", unsafe_allow_html=True)

if "envio_resultado" not in st.session_state:
    st.session_state["envio_resultado"] = None

# ==============================================================================
# SECCIÓN: CAMPAÑAS
# ==============================================================================
elif seccion == "campanas":
    st.markdown("""
    <div class="hero">
        <h1>🎯 Laboratorio de Campañas</h1>
        <p>Genera el modelo de campaña completo con IA: avatar, hooks, copys, oferta y plan de testeo.</p>
    </div>
    """, unsafe_allow_html=True)

    # Autocompletar desde la detección del Radar (si existe)
    det_radar = st.session_state.get("radar_deteccion") or {}
    nombre_pre = det_radar.get("nombre_detectado", "")
    categoria_pre = det_radar.get("categoria", "")
    desc_pre = det_radar.get("descripcion_comercial_final", "") or det_radar.get("resumen_visual", "")

    with st.container(border=True):
        st.markdown('<div class="sec-title">Datos del producto</div>', unsafe_allow_html=True)

        # Selector de producto guardado (opcional) — al elegir uno, rellena los campos
        prod_camp = selector_guardado("camp", "📦 Usar un producto guardado (opcional):")
        # Detectar si cambió la selección para actualizar los campos una vez
        sel_actual = st.session_state.get("camp_sel_guardado", "— Ninguno —")
        sel_previa = st.session_state.get("_camp_sel_previa", None)
        if prod_camp and sel_actual != sel_previa:
            st.session_state["_camp_sel_previa"] = sel_actual
            st.session_state["camp_nombre"] = prod_camp.get("titulo", "")
            precio_val = prod_camp.get("precio")
            st.session_state["camp_precio"] = (f"${precio_val:,}".replace(",", ".")
                                               if precio_val else "")
            if prod_camp.get("categoria"):
                st.session_state["camp_categoria"] = prod_camp.get("categoria", "")

        if prod_camp:
            # Mostrar la foto del producto seleccionado
            pcc1, pcc2 = st.columns([1, 4])
            with pcc1:
                img = prod_camp.get("imagen", "")
                if img:
                    st.markdown(f'<img src="{img}" style="width:100%;border-radius:10px;'
                                f'border:1px solid #eee;">', unsafe_allow_html=True)
            with pcc2:
                st.markdown(f"**{prod_camp.get('titulo','')}**")
                precio_val = prod_camp.get("precio")
                precio_txt = f"${precio_val:,}".replace(",", ".") if precio_val else ""
                st.markdown(f"<span style='color:#6366f1;font-weight:600;'>{prod_camp.get('fuente','')}</span> · "
                            f"{precio_txt}", unsafe_allow_html=True)
            st.markdown('<div style="height:0.6rem;"></div>', unsafe_allow_html=True)

        if nombre_pre or prod_camp:
            st.markdown('<div class="sec-sub">Autocompletado. Puedes editarlo.</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="sec-sub">Escribe el producto, elígelo de guardados, '
                        'o detéctalo primero en el Radar.</div>', unsafe_allow_html=True)

        # Inicializar los campos en session_state la primera vez (con datos del Radar)
        if "camp_nombre" not in st.session_state:
            st.session_state["camp_nombre"] = nombre_pre
        if "camp_categoria" not in st.session_state:
            st.session_state["camp_categoria"] = categoria_pre
        if "camp_precio" not in st.session_state:
            st.session_state["camp_precio"] = ""

        # Si llegó una detección NUEVA del Radar, actualizar los campos
        hash_det = det_radar.get("nombre_detectado", "")
        if hash_det and hash_det != st.session_state.get("_camp_ultimo_radar", "") and not prod_camp:
            st.session_state["_camp_ultimo_radar"] = hash_det
            st.session_state["camp_nombre"] = nombre_pre
            st.session_state["camp_categoria"] = categoria_pre

        camp_nombre = st.text_input("Nombre del producto",
                                    key="camp_nombre", placeholder="Ej: Audífonos JBL Tune 520")
        cc1, cc2 = st.columns(2, gap="medium")
        with cc1:
            camp_categoria = st.text_input("Categoría (opcional)",
                                           key="camp_categoria", placeholder="Ej: Audio / Auriculares")
        with cc2:
            camp_precio = st.text_input("Precio de referencia (opcional)",
                                        key="camp_precio", placeholder="Ej: $45.990")
        camp_desc = st.text_area("Descripción (opcional)", value=desc_pre, key="camp_desc",
                                 placeholder="Breve descripción del producto", height=80)

        # --- Selector de objetivo de campaña (Ventas por defecto) ---
        st.markdown('<div style="height:0.5rem;"></div>', unsafe_allow_html=True)
        st.markdown('<div class="sec-title" style="font-size:0.95rem;">🎯 Objetivo de la campaña</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="sec-sub">Qué quieres lograr. Para vender, deja "Ventas" '
                    '(recomendado para e-commerce).</div>', unsafe_allow_html=True)
        camp_objetivo = st.selectbox("Objetivo", list(OBJETIVOS_META.keys()),
                                     index=0, key="camp_objetivo", label_visibility="collapsed")

        # --- Selector de zonas de venta (segmentación geográfica) ---
        st.markdown('<div style="height:0.5rem;"></div>', unsafe_allow_html=True)
        st.markdown('<div class="sec-title" style="font-size:0.95rem;">📍 Zonas donde vendes</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="sec-sub">Marca las regiones que cubres. La segmentación se '
                    'ajustará solo a estas zonas (útil si tu envío es competitivo en ciertas áreas).</div>',
                    unsafe_allow_html=True)

        regiones_marcadas = []
        for zona, regiones in ZONAS_CHILE.items():
            st.markdown(f'<div style="font-weight:700;color:#4f46e5;font-size:0.82rem;'
                        f'margin:0.6rem 0 0.3rem;text-transform:uppercase;letter-spacing:0.3px;">{zona}</div>',
                        unsafe_allow_html=True)
            cols_z = st.columns(len(regiones) if len(regiones) <= 3 else 3)
            for idx_r, region in enumerate(regiones.keys()):
                with cols_z[idx_r % len(cols_z)]:
                    # Zona Norte marcada por defecto (período de prueba del usuario)
                    default = (zona == "Zona Norte")
                    if st.checkbox(region, value=default, key=f"zona_{region}"):
                        regiones_marcadas.append(region)

        generar = st.button("✨ Generar campaña completa", key="btn_generar_campana")

    if generar:
        if not camp_nombre or len(camp_nombre.strip()) < 2:
            st.warning("Escribe el nombre del producto para generar la campaña.")
        else:
            zonas_texto = _regiones_seleccionadas_a_texto(regiones_marcadas)
            with st.spinner("Generando campaña con IA... (puede tardar unos segundos)"):
                camp = generar_campana(camp_nombre.strip(), camp_categoria.strip(),
                                       camp_desc.strip(), camp_precio.strip(),
                                       zonas_venta=zonas_texto, objetivo=camp_objetivo)
            st.session_state["campana_resultado"] = camp

    camp = st.session_state.get("campana_resultado")
    if camp:
        if camp.get("error"):
            st.error(camp["error"])
        else:
            _render_campana(camp)

# Asegurar key en session
if "campana_resultado" not in st.session_state:
    st.session_state["campana_resultado"] = None
