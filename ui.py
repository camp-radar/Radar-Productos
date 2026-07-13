"""
ui.py — Componentes de render: tarjetas de producto, grilla, identidad y campaña.
"""
from io import BytesIO

import streamlit as st

from utils import formatear_pesos, resumir_texto, descargar_imagen
from busqueda import generar_link_tienda
from guardados import cargar_guardados, guardar_producto


def _card_producto_html(item, link_directo=False):
    """Genera el HTML de una tarjeta de producto.

    Si link_directo=True, usa item["link"] tal cual (para resultados de Lens,
    que ya apuntan a la página exacta del producto) en vez de generar_link_tienda.
    """
    link = item.get("link", "")
    imagen = item.get("imagen", "")
    tienda = item.get("fuente", "")
    titulo_full = item.get("titulo", "-")
    titulo = resumir_texto(titulo_full, 70)
    precio = formatear_pesos(item.get("precio"))
    link_tienda = link if link_directo else (generar_link_tienda(titulo_full, tienda) if tienda else link)
    img_html = (f'<div class="ml-card-img"><img src="{imagen}" loading="lazy"/></div>'
                if imagen else '<div class="ml-card-img">🛍️</div>')
    tienda_html = f'<div class="ml-card-store">{_esc(tienda)}</div>' if tienda else ""
    btn = (f'<a href="{link_tienda}" target="_blank" class="ml-card-btn">Ver en tienda →</a>'
           if link_tienda else "")
    return f"""
        <div class="ml-card">
            {img_html}
            <div class="ml-card-body">
                <div class="ml-card-price">{precio}</div>
                {tienda_html}
                <div class="ml-card-title">{titulo}</div>
                {btn}
            </div>
        </div>"""


def _render_fila_productos(items, key_prefix, link_directo=False):
    """Renderiza productos en una fila de 5 columnas, cada uno con botón Guardar."""
    guardados = cargar_guardados()
    claves_guardadas = {(g.get("link", ""), g.get("precio")) for g in guardados}

    por_fila = 5
    for inicio in range(0, len(items), por_fila):
        fila = items[inicio:inicio + por_fila]
        cols = st.columns(por_fila, gap="small")
        for idx, item in enumerate(fila):
            with cols[idx]:
                st.markdown(_card_producto_html(item, link_directo=link_directo), unsafe_allow_html=True)
                clave = (item.get("link", ""), item.get("precio"))
                item_idx = inicio + idx
                if clave in claves_guardadas:
                    st.button("✓ Guardado", key=f"{key_prefix}_g_{item_idx}",
                              disabled=True, use_container_width=True)
                else:
                    if st.button("💾 Guardar", key=f"{key_prefix}_s_{item_idx}",
                                 use_container_width=True):
                        if guardar_producto(item):
                            st.toast("Producto guardado ✓")
                            st.rerun()


def _render_fila_productos_lens(items, key_prefix):
    """Como _render_fila_productos, pero solo para la sección de "producto
    exacto": además del botón Guardar, ofrece "Buscar con esta imagen" para
    relanzar la búsqueda usando la miniatura del candidato (útil cuando la
    foto original es de mala calidad pero un candidato de catálogo sí es el
    producto correcto). No se usa en la grilla de "productos similares"."""
    guardados = cargar_guardados()
    claves_guardadas = {(g.get("link", ""), g.get("precio")) for g in guardados}

    por_fila = 5
    for inicio in range(0, len(items), por_fila):
        fila = items[inicio:inicio + por_fila]
        cols = st.columns(por_fila, gap="small")
        for idx, item in enumerate(fila):
            with cols[idx]:
                st.markdown(_card_producto_html(item, link_directo=True), unsafe_allow_html=True)
                clave = (item.get("link", ""), item.get("precio"))
                item_idx = inicio + idx

                col_guardar, col_buscar, _col_relleno = st.columns([1, 1, 4], gap="small")
                with col_guardar:
                    if clave in claves_guardadas:
                        st.button("✓", key=f"{key_prefix}_g_{item_idx}", disabled=True,
                                  help="Ya guardado")
                    else:
                        if st.button("💾", key=f"{key_prefix}_s_{item_idx}", help="Guardar producto"):
                            if guardar_producto(item):
                                st.toast("Producto guardado ✓")
                                st.rerun()
                with col_buscar:
                    if item.get("imagen"):
                        if st.button("🔍", key=f"{key_prefix}_img_{item_idx}",
                                     help="Buscar con esta imagen"):
                            try:
                                img_pil = descargar_imagen(item["imagen"])
                                if img_pil is None:
                                    raise RuntimeError("no se pudo descargar la imagen del candidato.")
                                buf = BytesIO()
                                img_pil.save(buf, format="JPEG", quality=90)
                                st.session_state["imagen_referente_bytes"] = buf.getvalue()
                                st.rerun()
                            except Exception as e:
                                st.error(f"No se pudo usar esta imagen para buscar: {e}")


def render_grid_ml(items, resultado=None):
    if not items:
        st.info("No se encontraron precios para esta búsqueda. Intenta con otro término.")
        return

    top = resultado.get("top", items) if resultado else items
    st.markdown('<div class="grid-title">🛒 Mejores precios encontrados</div>',
                unsafe_allow_html=True)
    _render_fila_productos(top[:5], "top")
    
    
def render_producto_exacto(resultado_lens):
    """Muestra el producto EXACTO encontrado vía Google Lens (módulo lens.py).

    No dibuja nada si la búsqueda falló o no trajo productos, para que el
    flujo de "productos similares" siga viéndose normal.
    """
    if not resultado_lens or not resultado_lens.get("ok") or not resultado_lens.get("productos"):
        return

    items = [{
        "titulo": p.get("titulo", ""),
        "fuente": p.get("tienda", ""),
        "precio": p.get("precio_num"),
        "imagen": p.get("imagen", ""),
        "link": p.get("link", ""),
    } for p in resultado_lens.get("productos", [])]

    st.markdown('<div class="grid-title">🎯 Producto exacto encontrado en tiendas chilenas</div>',
                unsafe_allow_html=True)

    resumen = resultado_lens.get("resumen_precios") or {}
    if resumen:
        st.markdown(f"""
<div class="camp-block camp-value" style="padding:0.8rem 1.1rem;margin-bottom:0.9rem;">
<div class="camp-text">
<b>Mínimo:</b> {formatear_pesos(resumen.get('min'))} &nbsp;·&nbsp;
<b>Mediana:</b> {formatear_pesos(resumen.get('mediana'))} &nbsp;·&nbsp;
<b>Máximo:</b> {formatear_pesos(resumen.get('max'))}
&nbsp;<span style="color:#94a3b8;">({resumen.get('cantidad', 0)} resultados)</span>
</div>
</div>
""", unsafe_allow_html=True)

    _render_fila_productos_lens(items, "lens")


def render_identidad(det):
    desc = det.get("descripcion_comercial_final") or det.get("resumen_visual", "")
    st.markdown(f"""
<div class="ident-card">
<div class="ident-row"><b>Producto:</b> {det.get('nombre_detectado', '-')}</div>
<div class="ident-row"><b>Marca:</b> {det.get('marca_probable') or '-'} &nbsp;·&nbsp; <b>Modelo:</b> {det.get('modelo_probable') or '-'}</div>
<div class="ident-row"><b>Categoría:</b> {det.get('categoria', '-')}</div>
{f'<div class="ident-desc">{desc}</div>' if desc else ''}
</div>
""", unsafe_allow_html=True)


def _esc(texto):
    """Escapa HTML básico para evitar romper el render."""
    if texto is None:
        return ""
    return (str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _render_campana(c):
    """Renderiza el paquete de campaña ordenado como un brief profesional."""
    av = c.get("avatar", {}) if isinstance(c.get("avatar"), dict) else {}
    seg = c.get("segmentacion", {}) if isinstance(c.get("segmentacion"), dict) else {}
    pres = c.get("presupuesto", {}) if isinstance(c.get("presupuesto"), dict) else {}
    embudo = c.get("estructura_embudo", {}) if isinstance(c.get("estructura_embudo"), dict) else {}

    # ══════════════ RESUMEN DE ESTRATEGIA ══════════════
    if c.get("resumen_estrategia"):
        st.markdown(f"""
<div class="camp-block camp-value">
<div class="camp-h">📋 Resumen de la estrategia</div>
<div class="camp-text">{_esc(c.get('resumen_estrategia'))}</div>
</div>
""", unsafe_allow_html=True)

    # ══════════════ 1. TEXTOS LISTOS PARA PUBLICAR ══════════════
    st.markdown('<div class="camp-meta-header">📋 Textos listos para publicar</div>', unsafe_allow_html=True)
    st.caption("Pasa el mouse sobre cada bloque y usa el ícono de copiar (esquina superior derecha).")

    titulos = c.get("titulos_publicacion", [])
    if titulos:
        st.markdown("**Títulos / encabezados** — elige el que más pare el scroll:")
        st.code("\n".join(f"{i+1}. {t}" for i, t in enumerate(titulos) if t), language=None)

    if c.get("copy_meta_largo"):
        st.markdown("**Copy principal del anuncio (texto largo):**")
        st.code(c.get("copy_meta_largo"), language=None)

    col_cc, col_ct = st.columns(2, gap="medium")
    with col_cc:
        if c.get("copy_meta_corto"):
            st.markdown("**Copy corto (directo):**")
            st.code(c.get("copy_meta_corto"), language=None)
    with col_ct:
        if c.get("copy_tiktok"):
            st.markdown("**Copy TikTok / Reels:**")
            st.code(c.get("copy_tiktok"), language=None)

    if c.get("oferta_recomendada"):
        st.markdown(f"""
<div class="camp-block camp-offer">
<div class="camp-h">🎁 Oferta recomendada</div>
<div class="camp-text">{_esc(c.get('oferta_recomendada'))}</div>
</div>
""", unsafe_allow_html=True)

    # ══════════════ 2. GUION DE VIDEO ══════════════
    guion = c.get("guion_ugc")
    if guion:
        st.markdown('<div class="camp-meta-header">🎬 Guion de video</div>', unsafe_allow_html=True)
        st.caption("Para grabar con tu celular o pegar como prompt en una herramienta de video.")
        if isinstance(guion, list):
            for esc in guion:
                if isinstance(esc, dict):
                    num = esc.get("escena", "")
                    dur = esc.get("duracion", "")
                    vis = esc.get("visual", "")
                    voz = esc.get("voz_o_texto", "")
                    st.markdown(f"""
<div class="camp-block">
<div class="camp-hook"><span class="camp-num">{_esc(num)}</span><div><b>{_esc(dur)}</b><br><b>Visual:</b> {_esc(vis)}<br><b>Voz / texto:</b> {_esc(voz)}</div></div>
</div>
""", unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="camp-block"><div class="camp-text">{_esc(esc)}</div></div>',
                                unsafe_allow_html=True)
        else:
            st.markdown(f"""
<div class="camp-block">
<div class="camp-text camp-pre">{_esc(guion)}</div>
</div>
""", unsafe_allow_html=True)

    # ══════════════ 3. CONFIGURACIÓN META ADS ══════════════
    st.markdown('<div class="camp-meta-header">⚙️ Configuración para Meta Ads</div>', unsafe_allow_html=True)

    if c.get("objetivo_campana"):
        st.markdown(f"""
<div class="camp-block">
<div class="camp-h">🎯 Objetivo de campaña</div>
<div class="camp-text">{_esc(c.get('objetivo_campana'))}</div>
</div>
""", unsafe_allow_html=True)

    if seg:
        filosofia = seg.get("filosofia_2026", "")
        filosofia_html = (f'<div class="camp-text" style="margin-bottom:0.8rem;font-style:italic;'
                          f'color:#6366f1;background:#f8fafc;padding:0.65rem 0.85rem;border-radius:8px;">'
                          f'💡 {_esc(filosofia)}</div>') if filosofia else ""
        st.markdown(f"""
<div class="camp-block camp-segment">
<div class="camp-h">👥 Segmentación del público</div>
{filosofia_html}
<div class="camp-seg-grid">
<div class="camp-seg-item"><span class="camp-seg-label">Género</span>{_esc(seg.get('genero', '-'))}</div>
<div class="camp-seg-item"><span class="camp-seg-label">Edad (rango)</span>{_esc(seg.get('edad_min', '-'))} - {_esc(seg.get('edad_max', '-'))} años</div>
<div class="camp-seg-item"><span class="camp-seg-label">Edad óptima</span>{_esc(seg.get('edad_recomendada', '-'))}</div>
<div class="camp-seg-item"><span class="camp-seg-label">Ubicaciones</span>{_esc(seg.get('ubicaciones', '-'))}</div>
<div class="camp-seg-item"><span class="camp-seg-label">Idioma</span>{_esc(seg.get('idiomas', '-'))}</div>
</div>
</div>
""", unsafe_allow_html=True)

    intereses_meta = c.get("intereses_sugeridos", [])
    comportamientos = c.get("comportamientos_sugeridos", [])
    if intereses_meta or comportamientos:
        chips_int = "".join(f'<span class="camp-chip">{_esc(x)}</span>' for x in intereses_meta)
        chips_comp = "".join(f'<span class="camp-chip camp-chip-alt">{_esc(x)}</span>' for x in comportamientos)
        st.markdown(f"""
<div class="camp-block">
<div class="camp-h">🎯 Intereses sugeridos (Meta)</div>
<div class="camp-chips">{chips_int}</div>
{f'<div class="camp-h" style="margin-top:0.8rem;">📊 Comportamientos</div><div class="camp-chips">{chips_comp}</div>' if comportamientos else ''}
</div>
""", unsafe_allow_html=True)

    if embudo:
        st.markdown(f"""
<div class="camp-block camp-segment">
<div class="camp-h">🔀 Estructura de embudo (audiencias por etapa)</div>
<div class="camp-hook"><span class="camp-num">1</span><div><b>Frío — Captar nuevos:</b> {_esc(embudo.get('frio_prospecting', '-'))}</div></div>
<div class="camp-hook"><span class="camp-num">2</span><div><b>Tibio — Retargeting:</b> {_esc(embudo.get('tibio_retargeting', '-'))}</div></div>
<div class="camp-hook"><span class="camp-num">3</span><div><b>Caliente — Cerrar venta:</b> {_esc(embudo.get('caliente_conversion', '-'))}</div></div>
</div>
""", unsafe_allow_html=True)

    exclusiones = c.get("exclusiones_recomendadas", [])
    datos_propios = c.get("datos_propios", "")
    if exclusiones or datos_propios:
        excl_html = ""
        if exclusiones:
            items = "".join(f'<li>{_esc(x)}</li>' for x in exclusiones)
            excl_html = f'<div class="camp-h">🚫 Exclusiones recomendadas</div><ul class="camp-list">{items}</ul>'
        datos_html = ""
        if datos_propios:
            datos_html = (f'<div class="camp-h" style="margin-top:0.8rem;">💎 Datos propios (lo más potente en 2026)</div>'
                          f'<div class="camp-text">{_esc(datos_propios)}</div>')
        st.markdown(f"""
<div class="camp-block camp-value">
{excl_html}
{datos_html}
</div>
""", unsafe_allow_html=True)

    if pres:
        st.markdown(f"""
<div class="camp-block camp-offer">
<div class="camp-h">💰 Presupuesto recomendado</div>
<div class="camp-text camp-big">{_esc(pres.get('diario_recomendado', '-'))} / día</div>
<div class="camp-text" style="margin-top:0.4rem;">{_esc(pres.get('justificacion', ''))}</div>
<div class="camp-text" style="margin-top:0.4rem;"><b>Distribución:</b> {_esc(pres.get('distribucion', ''))}</div>
</div>
""", unsafe_allow_html=True)

    if c.get("publico_advantage"):
        pubs = c.get("publicos_personalizados", [])
        pubs_html = "".join(f'<li>{_esc(p)}</li>' for p in pubs) if pubs else ""
        st.markdown(f"""
<div class="camp-block">
<div class="camp-h">🤖 Advantage+ y públicos</div>
<div class="camp-text">{_esc(c.get('publico_advantage'))}</div>
{f'<div class="camp-h" style="margin-top:0.7rem;font-size:0.85rem;">Públicos personalizados sugeridos:</div><ul class="camp-list">{pubs_html}</ul>' if pubs else ''}
</div>
""", unsafe_allow_html=True)

    col_u, col_p = st.columns(2, gap="medium")
    with col_u:
        if c.get("ubicaciones_anuncios"):
            st.markdown(f"""
<div class="camp-block">
<div class="camp-h">📱 Ubicaciones de anuncios</div>
<div class="camp-text">{_esc(c.get('ubicaciones_anuncios'))}</div>
</div>
""", unsafe_allow_html=True)
    with col_p:
        if c.get("puja_optimizacion"):
            st.markdown(f"""
<div class="camp-block">
<div class="camp-h">⚡ Puja y optimización</div>
<div class="camp-text">{_esc(c.get('puja_optimizacion'))}</div>
</div>
""", unsafe_allow_html=True)

    # ══════════════ 4. MATERIA PRIMA CREATIVA ══════════════
    st.markdown('<div class="camp-meta-header">✍️ Materia prima creativa</div>', unsafe_allow_html=True)

    intereses = av.get("intereses", [])
    intereses_html = "".join(
        f'<span class="camp-chip">{_esc(i)}</span>' for i in intereses) if intereses else ""
    st.markdown(f"""
<div class="camp-block">
<div class="camp-h">👤 Avatar del comprador</div>
<div class="camp-text">{_esc(av.get('descripcion', '-'))}</div>
<div class="camp-meta">
<span><b>Edad:</b> {_esc(av.get('edad', '-'))}</span>
<span><b>Género:</b> {_esc(av.get('genero', '-'))}</span>
</div>
<div class="camp-chips">{intereses_html}</div>
</div>
""", unsafe_allow_html=True)

    col_a, col_b = st.columns(2, gap="medium")
    with col_a:
        st.markdown(f"""
<div class="camp-block camp-pain">
<div class="camp-h">😣 Dolor principal</div>
<div class="camp-text">{_esc(c.get('dolor_principal', '-'))}</div>
</div>
""", unsafe_allow_html=True)
    with col_b:
        st.markdown(f"""
<div class="camp-block camp-desire">
<div class="camp-h">✨ Deseo principal</div>
<div class="camp-text">{_esc(c.get('deseo_principal', '-'))}</div>
</div>
""", unsafe_allow_html=True)

    st.markdown(f"""
<div class="camp-block camp-value">
<div class="camp-h">💎 Propuesta de valor</div>
<div class="camp-text camp-big">{_esc(c.get('propuesta_valor', '-'))}</div>
</div>
""", unsafe_allow_html=True)

    beneficios = c.get("beneficios", [])
    if beneficios:
        items = "".join(f'<li>{_esc(b)}</li>' for b in beneficios)
        st.markdown(f"""
<div class="camp-block">
<div class="camp-h">✅ Beneficios clave</div>
<ul class="camp-list">{items}</ul>
</div>
""", unsafe_allow_html=True)

    hooks = c.get("hooks", [])
    if hooks:
        items = "".join(f'<div class="camp-hook"><span class="camp-num">{i+1}</span> {_esc(h)}</div>'
                        for i, h in enumerate(hooks))
        st.markdown(f"""
<div class="camp-block">
<div class="camp-h">🎣 10 Hooks (ganchos)</div>
{items}
</div>
""", unsafe_allow_html=True)

    angulos = c.get("angulos_venta", [])
    if angulos:
        items = ""
        for a in angulos:
            if isinstance(a, dict):
                items += f'<div class="camp-angle"><b>{_esc(a.get("nombre","-"))}</b><br>{_esc(a.get("descripcion",""))}</div>'
        st.markdown(f"""
<div class="camp-block">
<div class="camp-h">🎯 Ángulos de venta</div>
{items}
</div>
""", unsafe_allow_html=True)

    # ══════════════ 5. PLAN DE TESTEO ══════════════
    if c.get("plan_testeo"):
        st.markdown('<div class="camp-meta-header">📊 Plan de testeo y escalado</div>', unsafe_allow_html=True)
        st.markdown(f"""
<div class="camp-block">
<div class="camp-text camp-pre">{_esc(c.get('plan_testeo', '-'))}</div>
</div>
""", unsafe_allow_html=True)
