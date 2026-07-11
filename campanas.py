"""
campanas.py — Laboratorio de Campañas: genera la configuración de Meta Ads con IA.
"""
from config import ZONAS_CHILE, OBJETIVOS_META
from ia import _groq_generate
from utils import extraer_json_respuesta


def _regiones_seleccionadas_a_texto(regiones_marcadas):
    """Convierte la lista de regiones marcadas en texto con ciudades para el prompt."""
    if not regiones_marcadas:
        return ""
    partes = []
    for zona, regiones in ZONAS_CHILE.items():
        for region, ciudades in regiones.items():
            if region in regiones_marcadas:
                partes.append(f"{region} ({', '.join(ciudades)})")
    return "; ".join(partes)


# ==============================================================================
# LABORATORIO DE CAMPAÑAS — generación con Gemini
# ==============================================================================
def generar_campana(nombre_producto: str, categoria: str = "", descripcion: str = "",
                    precio_ref: str = "", zonas_venta: str = "", objetivo: str = "") -> dict:
    """
    Genera un paquete completo de campaña publicitaria con IA.
    Devuelve dict con todas las secciones, o {'error': ...} si falla.
    """
    if not nombre_producto or len(nombre_producto.strip()) < 2:
        return {"error": "Falta el nombre del producto."}

    contexto_extra = ""
    if categoria:
        contexto_extra += f"\nCategoría: {categoria}"
    if descripcion:
        contexto_extra += f"\nDescripción: {descripcion}"
    if objetivo:
        desc_obj = OBJETIVOS_META.get(objetivo, "")
        contexto_extra += (f"\n\nOBJETIVO DE CAMPAÑA (define TODA la estrategia): '{objetivo}'. "
                           f"Significa: {desc_obj} "
                           f"Ajusta el objetivo_campana, los ángulos creativos, los llamados a la acción (CTA) "
                           f"y la optimización a ESTE objetivo específico. Si el objetivo es Ventas, todo debe "
                           f"empujar hacia el cierre de la compra (CTA tipo 'Comprar ahora', urgencia, oferta clara).")
    if zonas_venta:
        contexto_extra += (f"\n\nZONA DE VENTA (MUY IMPORTANTE): El vendedor SOLO despacha y vende en estas "
                           f"zonas de Chile: {zonas_venta}. "
                           f"Por lo tanto, en 'ubicaciones' debes recomendar EXACTAMENTE estas ciudades/regiones "
                           f"y NINGUNA otra. NO incluyas Santiago ni otras zonas si no están en esta lista. "
                           f"La ventaja competitiva del vendedor es el envío local barato en estas zonas. "
                           f"Ajusta toda la estrategia (segmentación, presupuesto, ángulos) a este mercado local.")
    if precio_ref:
        contexto_extra += f"\nPrecio de referencia: {precio_ref}"

    prompt = f"""Eres un MEDIA BUYER SENIOR y COMMUNITY MANAGER experto en Meta Ads (Facebook e Instagram) para e-commerce en Chile, con años y millones en pesos gestionando campañas reales rentables. Dominas el Administrador de Anuncios de Meta 2026 al detalle.

CONOCIMIENTO CLAVE 2026 que aplicas siempre:
- La segmentación detallada ahora es SUGERENCIA, no filtro rígido: Meta muestra el anuncio a tu audiencia y a otros si mejora resultados. Ganar = buenas señales + creativo fuerte, NO apilar 20 intereses.
- Meta quitó muchas opciones manuales y consolidó intereses en categorías amplias. Usa 3-6 intereses amplios, no muchos estrechos.
- Los datos propios (first-party: lista de clientes, lookalikes del top de compradores) superan a los intereses. Son la mejor señal.
- Advantage+ Audience es el modo por defecto y suele ganar para e-commerce con presupuesto sobre $50/día.
- Estructura por embudo: FRÍO (prospecting), TIBIO (retargeting engagement), CALIENTE (carritos/compradores).
- Las EXCLUSIONES importan: excluir compradores recientes de campañas de adquisición evita gastar de más.
- "El creativo es la segmentación": el anuncio (hook, visual, copy) le dice a la IA a quién buscar. Por eso importa el volumen y variedad de ángulos creativos.
- No sobre-restringir género/edad: suele desperdiciar conversiones baratas. Amplio + sugerencias funciona mejor.

PRODUCTO: {nombre_producto}{contexto_extra}

Tu tarea: entregar una CONFIGURACIÓN COMPLETA Y LISTA PARA COPIAR en el Administrador de Anuncios de Meta, como si tú mismo fueras a montar la campaña. Analiza el producto, deduce el cliente ideal chileno, y entrega parámetros concretos y accionables con la lógica 2026.

Usa lenguaje chileno, montos en pesos chilenos (CLP), y sé MUY específico y técnico. Nada genérico.

Responde SOLO JSON válido, sin markdown, con esta estructura EXACTA:
{{
  "resumen_estrategia": "2-3 frases explicando el enfoque general de la campana y por que funcionara para este producto",
  "objetivo_campana": "el objetivo de Meta recomendado (ej: Ventas / Conversiones, Trafico, Reconocimiento) y por que",
  "segmentacion": {{
    "filosofia_2026": "explica en 1-2 frases que en Meta 2026 la segmentacion detallada es SUGERENCIA (no filtro rigido): Meta muestra el anuncio a tu audiencia sugerida Y a otros si mejora resultados. La estrategia ganadora es dar buenas senales iniciales + creativo fuerte, no apilar intereses.",
    "genero": "Hombres / Mujeres / Todos — con justificacion. IMPORTANTE: recomienda 'Todos' salvo que el producto sea inequivocamente de un genero, porque restringir genero suele desperdiciar conversiones baratas.",
    "edad_min": 18,
    "edad_max": 45,
    "edad_recomendada": "el rango optimo donde concentrar (ej: 25-34) y por que, pero como SUGERENCIA amplia no como filtro estrecho",
    "ubicaciones": "ciudades o regiones de Chile recomendadas (ej: Santiago, Valparaiso, Concepcion) y si conviene todo el pais. Esto SI es un control rigido en Meta.",
    "idiomas": "idioma a configurar (normalmente Espanol)"
  }},
  "estructura_embudo": {{
    "frio_prospecting": "audiencia FRIA para captar clientes nuevos: usar Advantage+ Audience con 3-5 intereses como sugerencia. Describe que configurar.",
    "tibio_retargeting": "audiencia TIBIA (retargeting): personas que vieron videos, visitaron el sitio o interactuaron. Describe que publico crear.",
    "caliente_conversion": "audiencia CALIENTE: carritos abandonados, visitantes de ficha de producto, compradores previos para recompra. Describe que publico crear."
  }},
  "intereses_sugeridos": ["3 a 6 intereses AMPLIOS y relevantes de Meta como senales (no 20 estrechos). Interes 1", "interes 2", "interes 3", "interes 4", "interes 5"],
  "comportamientos_sugeridos": ["comportamiento 1 (ej: compradores online frecuentes)", "comportamiento 2", "comportamiento 3"],
  "exclusiones_recomendadas": ["exclusion 1 IMPORTANTE (ej: excluir compradores ultimos 30 dias en campanas de adquisicion)", "exclusion 2 (ej: excluir visitantes recientes si ya estan en otra campana)"],
  "datos_propios": "recomendacion sobre usar datos propios (first-party): subir lista de clientes/emails como Publico Personalizado y crear Lookalike del top 20% de compradores. En 2026 esto supera a los intereses. Explica en simple como empezar aunque tenga pocos datos.",
  "publico_advantage": "recomendacion clara sobre Advantage+ Audience: en 2026 es el modo por defecto y suele ganar para e-commerce con presupuesto sobre $50/dia. Explica si conviene para este producto/presupuesto y como configurarlo (activarlo + dar 3-5 intereses como sugerencia).",
  "publicos_personalizados": ["idea de publico personalizado 1 (ej: visitantes del sitio ultimos 30 dias)", "idea 2 (ej: lookalike de compradores)"],
  "presupuesto": {{
    "diario_recomendado": "monto diario inicial en CLP realista para testear (ej: $5.000 - $8.000 CLP)",
    "justificacion": "por que ese monto y que esperar con el",
    "distribucion": "como repartir el presupuesto (ej: 2 conjuntos de anuncios con X cada uno)"
  }},
  "ubicaciones_anuncios": "donde mostrar los anuncios (ej: Feeds de Instagram y Facebook, Stories, Reels) y cuales priorizar para este producto",
  "puja_optimizacion": "evento de optimizacion recomendado (ej: optimizar por Compras) y estrategia de puja (ej: Costo mas bajo)",
  "avatar": {{
    "descripcion": "perfil del comprador ideal en 2-3 frases concretas",
    "edad": "rango de edad",
    "genero": "genero predominante",
    "intereses": ["interes1", "interes2", "interes3"]
  }},
  "dolor_principal": "el principal problema que vive el cliente antes de comprar",
  "deseo_principal": "lo que el cliente realmente desea lograr",
  "beneficios": ["beneficio1", "beneficio2", "beneficio3", "beneficio4"],
  "propuesta_valor": "propuesta de valor unica en una frase potente",
  "hooks": ["hook1", "hook2", "hook3", "hook4", "hook5", "hook6", "hook7", "hook8", "hook9", "hook10"],
  "angulos_venta": [
    {{"nombre": "nombre del angulo", "descripcion": "como se enfoca"}},
    {{"nombre": "...", "descripcion": "..."}},
    {{"nombre": "...", "descripcion": "..."}}
  ],
  "titulos_publicacion": ["titulo/encabezado vendedor para el anuncio o la publicacion de Marketplace, corto (max 60 caracteres), que pare el scroll", "titulo 2 con otro enfoque", "titulo 3", "titulo 4", "titulo 5"],
  "guion_ugc": [
    {{"escena": 1, "duracion": "0-3s", "visual": "que se muestra en pantalla (plano, accion, producto)", "voz_o_texto": "que se dice o que texto aparece en pantalla"}},
    {{"escena": 2, "duracion": "3-8s", "visual": "...", "voz_o_texto": "..."}},
    {{"escena": 3, "duracion": "8-15s", "visual": "...", "voz_o_texto": "..."}},
    {{"escena": 4, "duracion": "15-25s (cierre + llamado a la accion)", "visual": "...", "voz_o_texto": "..."}}
  ],
  "copy_meta_corto": "copy breve para anuncio (maximo 2 lineas, directo, con emoji si aplica). Texto final, listo para copiar y pegar",
  "copy_meta_largo": "copy extenso del anuncio con estructura gancho + problema + solucion + beneficios + oferta + llamado a la accion. Texto final chileno, listo para copiar y pegar",
  "copy_tiktok": "copy nativo estilo TikTok/Reels, tono casual y hablado. Texto final, listo para copiar y pegar",
  "oferta_recomendada": "estructura de oferta (descuentos, bundles, garantia, envio) que maximice conversion",
  "plan_testeo": "plan de testeo paso a paso: que probar primero, metricas clave (CPM, CTR, CPA, ROAS), cuando escalar y cuando apagar un anuncio"
}}

IMPORTANTE:
- Los intereses y comportamientos deben ser categorias REALES que existan en Meta Ads, especificas para este producto.
- Los 10 hooks deben ser variados (preguntas, estadisticas, provocaciones, beneficios, historias), listos para usar.
- Los 5 titulos_publicacion deben ser distintos entre si (uno con oferta, uno con pregunta, uno con beneficio directo, uno con curiosidad, uno con urgencia), cortos y listos para pegar.
- Los copys (corto, largo, tiktok) deben venir LISTOS PARA COPIAR Y PEGAR: texto final real, sin comillas, sin corchetes y sin notas del tipo "aqui va...".
- El guion_ugc debe ser escena por escena, concreto: que se ve y que se dice o escribe en cada momento.
- Los montos en CLP deben ser realistas para un emprendedor chileno que esta empezando.
- Se un experto: deduce el publico correcto segun el tipo de producto, no des respuestas vagas."""

    try:
        respuesta, modelo_usado = _groq_generate(prompt)
        parsed = extraer_json_respuesta(respuesta)
        if parsed and isinstance(parsed, dict) and parsed.get("avatar"):
            parsed["_modelo"] = modelo_usado
            return parsed
        return {"error": "La IA no devolvió un formato válido. Intenta de nuevo."}
    except Exception as e:
        err = str(e)
        if "429" in err or "límite" in err.lower() or "quota" in err.lower():
            return {"error": "Límite de IA alcanzado. Espera unos minutos e intenta de nuevo."}
        return {"error": f"Error generando campaña: {err}"}
