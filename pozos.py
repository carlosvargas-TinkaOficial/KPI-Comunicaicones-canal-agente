import streamlit as st
import pandas as pd
import re

# --- FUNCIÓN DE LIMPIEZA Y CORRECCIÓN DE URLs (.jpe -> .jpeg) ---
def limpiar_url_evidencia(url):
    if not url or pd.isna(url):
        return None
    url_str = str(url).strip()
    if url_str == "" or url_str.lower() in ["nan", "none", "-", "null"]:
        return None
    # Reemplaza .jpe por .jpeg de forma segura al final o antes de parámetros ?token=
    url_str = re.sub(r'\.jpe(?=[?#]|$)', '.jpeg', url_str, flags=re.IGNORECASE)
    return url_str

# --- ORDENAMIENTO DE FORMULARIOS POR FECHA (ddmmyyyy) ---
def ordenar_formularios_por_fecha(forms):
    def clave_fecha(f):
        m = re.search(r'(\d{2})(\d{2})(\d{4})', str(f))
        if m:
            d, mo, y = m.groups()
            return f"{y}-{mo}-{d}"
        return str(f)
    return sorted(forms, key=clave_fecha)

# --- NORMALIZACIÓN Y ORDENAMIENTO POR FECHA Y HORA DE SUBIDA ---
def ordenar_base_pozos_cronologicamente(df):
    col_f = next((c for c in df.columns if str(c).strip().upper() == 'FECHA'), None)
    col_h = next((c for c in df.columns if str(c).strip().upper() == 'HORA'), None)
    
    if not col_f:
        return df

    def normalizar_fecha(val):
        if pd.isna(val):
            return "1970-01-01"
        if hasattr(val, 'strftime'):
            return val.strftime('%Y-%m-%d')
        val_str = str(val).strip().split(' ')[0]
        partes = val_str.split('/')
        if len(partes) == 3:
            return f"{partes[2]}-{partes[1]}-{partes[0]}"
        return val_str

    def normalizar_hora(val):
        if pd.isna(val):
            return "00:00:00"
        if hasattr(val, 'strftime'):
            return val.strftime('%H:%M:%S')
        val_str = str(val).strip()
        if ' ' in val_str:
            val_str = val_str.split(' ')[-1]
        return val_str

    f_norm = df[col_f].apply(normalizar_fecha)
    h_norm = df[col_h].apply(normalizar_hora) if col_h else "00:00:00"
    
    dt_series = pd.to_datetime(f_norm + ' ' + h_norm, errors='coerce')
    df['_FECHA_HORA_ORDEN'] = dt_series
    
    # Se ordena de menor a mayor para que la última subida quede siempre al final (iloc[-1])
    df = df.sort_values(by=['_FECHA_HORA_ORDEN'], ascending=True).reset_index(drop=True)
    return df

def mostrar_modulo(api_key, bytes_pozos, bytes_inasistencias):
    st.title("🎱 Resultado Encuesta de Pozo")
    
    if not bytes_pozos:
        st.warning("⚠️ No se pudo cargar la base de datos de Pozos desde Google Drive.")
        return
    if not bytes_inasistencias:
        st.warning("⚠️ No se pudo cargar la base de datos de Inasistencias (Directorio de Puntos).")
        return

    try:
        df_pozos_raw = pd.read_excel(bytes_pozos)
        df_inas_raw = pd.read_excel(bytes_inasistencias)
    except Exception as e:
        st.error(f"⚠️ Error al leer los archivos: {e}")
        return

    # --- 1. PREPARACIÓN DEL DIRECTORIO BASE DE PUNTOS OBJETIVO (INASISTENCIAS) ---
    df_inas = df_inas_raw.rename(columns={c: str(c).strip() for c in df_inas_raw.columns})
    col_term_inas = 'TERMINAL' if 'TERMINAL' in df_inas.columns else ('username' if 'username' in df_inas.columns else None)
    if not col_term_inas:
        st.error("No se encontró la columna de terminal o username en la base de Inasistencias.")
        return

    df_inas['TERMINAL_CLEAN'] = df_inas[col_term_inas].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    col_reg = next((c for c in df_inas.columns if any(w in c.lower() for w in ['territorial', 'regional'])), 'TERRITORIAL')
    col_sup = next((c for c in df_inas.columns if 'jerarquia' in c.lower() or 'supervisor' in c.lower()), 'Jerarquia_Dinamica')
    
    df_universo = df_inas[['TERMINAL_CLEAN', col_reg, col_sup]].dropna(subset=['TERMINAL_CLEAN']).drop_duplicates(subset=['TERMINAL_CLEAN'])
    df_universo = df_universo.rename(columns={'TERMINAL_CLEAN': 'TERMINAL', col_reg: 'Regional', col_sup: 'Supervisor'})

    # --- 2. FILTRADO, LIMPIEZA Y ORDENAMIENTO POR FECHA/HORA DE DATA_POZOS ---
    df_p = df_pozos_raw.rename(columns={c: str(c).strip() for c in df_pozos_raw.columns})
    col_term_p = 'TERMINAL' if 'TERMINAL' in df_p.columns else ('USERNAME' if 'USERNAME' in df_p.columns else None)
    if not col_term_p:
        st.error("No se encontró la columna TERMINAL en Data_Pozos.")
        return
    df_p['TERMINAL'] = df_p[col_term_p].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)

    # Identificar columna de URL / Evidencia
    col_url = next((c for c in df_p.columns if any(w in str(c).lower() for w in ['url', 'link', 'foto', 'image', 'imagen', 'evidencia'])), None)

    # Ordenar por FECHA y HORA para asegurar que la última foto subida sea la seleccionada
    df_p = ordenar_base_pozos_cronologicamente(df_p)

    # Formularios válidos con 'POZO' y sin 'NL'
    if 'FORMULARIO' not in df_p.columns:
        st.error("No se encontró la columna FORMULARIO en Data_Pozos.")
        return

    todos_formularios = df_p['FORMULARIO'].dropna().unique().tolist()
    formularios_validos = [
        f for f in todos_formularios 
        if 'POZO' in str(f).upper() and 'NL' not in str(f).upper()
    ]

    if not formularios_validos:
        st.warning("No se encontraron formularios con 'POZO' (sin 'NL').")
        return

    formularios_ordenados = ordenar_formularios_por_fecha(formularios_validos)

    # --- 3. FILTROS GENERALES SUPERIORES (REGIONAL Y SUPERVISOR) ---
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        regionales = ["Todos"] + sorted(df_universo['Regional'].dropna().unique().tolist())
        selected_reg = st.selectbox("🎯 1. Regional:", regionales)

    df_u_reg = df_universo if selected_reg == "Todos" else df_universo[df_universo['Regional'] == selected_reg]
    with col_f2:
        supervisores = ["Todos"] + sorted(df_u_reg['Supervisor'].dropna().unique().tolist())
        selected_sup = st.selectbox("👔 2. Supervisor:", supervisores)

    df_objetivo_filtrado = df_u_reg if selected_sup == "Todos" else df_u_reg[df_u_reg['Supervisor'] == selected_sup]

    # --- 4. FUNCIÓN EVALUADORA POR FORMULARIO (ÚLTIMA FOTO SUBIDA) ---
    def evaluar_formulario(form_name, base_objetivo):
        df_sub = df_p[df_p['FORMULARIO'] == form_name]
        registros = []
        
        for _, row in base_objetivo.iterrows():
            term = row['TERMINAL']
            reg = row['Regional']
            sup = row['Supervisor']
            
            puntos_term = df_sub[df_sub['TERMINAL'] == term]
            num_intentos = len(puntos_term)
            
            if puntos_term.empty:
                estado = "Sin respuesta"
                url_val = None
                intentos_val = 0
            else:
                resultados = puntos_term['RESULTADO'].astype(str).str.lower().tolist()
                tiene_match = any('match' == r for r in resultados)
                tiene_no_match = any('no_match' == r for r in resultados)
                
                # Extraer la última foto válida en orden cronológico ascendente (último intento subido)
                url_val = None
                if col_url:
                    fotos_validas = puntos_term[
                        puntos_term[col_url].notna() &
                        (~puntos_term[col_url].astype(str).str.strip().str.lower().isin(['', '-', 'none', 'nan', 'null']))
                    ]
                    if not fotos_validas.empty:
                        raw_url = fotos_validas[col_url].iloc[-1]
                        url_val = limpiar_url_evidencia(raw_url)
                
                if tiene_match:
                    if not tiene_no_match and num_intentos == 1:
                        estado = "True - 1er intento"
                    else:
                        estado = "True - Segundo intento"
                    url_val = None  # Solo los no comprobados muestran fotografía
                    intentos_val = num_intentos
                else:
                    estado = "No comprobado"
                    intentos_val = num_intentos

            registros.append({
                'Regional': reg,
                'Supervisor': sup,
                'Terminal': term,
                'Estado': estado,
                'Intentos': intentos_val,
                'Evidencia': url_val
            })
        return pd.DataFrame(registros)

    # --- 5. CUADROS EVOLUTIVOS (CANTIDADES Y PORCENTAJES) ---
    datos_evolutivo = {}
    for form in formularios_ordenados:
        df_eval = evaluar_formulario(form, df_objetivo_filtrado)
        
        tot_pts = len(df_eval)
        t_1er = (df_eval['Estado'] == 'True - 1er intento').sum()
        t_2do = (df_eval['Estado'] == 'True - 2do intento').sum()
        tot_comp = t_1er + t_2do
        
        n_comp = (df_eval['Estado'] == 'No comprobado').sum()
        s_resp = (df_eval['Estado'] == 'Sin respuesta').sum()
        tot_no_comp = n_comp + s_resp
        
        datos_evolutivo[form] = [
            tot_pts,
            tot_comp,
            t_1er,
            t_2do,
            tot_no_comp,
            n_comp,
            s_resp
        ]

    filas_config = [
        ("Total de Puntos", "total"),
        ("Pozos Comprobados", "yellow_header"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;True - 1er intento", "item"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;True - 2do intento", "item"),
        ("Pozo No comprobado", "yellow_header"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;No comprobado", "item"),
        ("&nbsp;&nbsp;&nbsp;&nbsp;Sin respuesta", "item")
    ]

    def renderizar_tabla_html(es_porcentaje=False):
        html = """
        <div style="overflow-x: auto; margin-bottom: 25px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.08); border: 1px solid #E6E6E6; background-color: #FFFFFF;">
        <table style="width: 100%; border-collapse: separate; border-spacing: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 14px;">
            <thead>
                <tr style="background-color: #FFFFFF;">
                    <th style="padding: 10px 14px; position: sticky; left: 0; z-index: 3; background-color: #FFFFFF; min-width: 175px; max-width: 175px; border-bottom: 2px solid #ccc; box-shadow: 3px 0 5px -2px rgba(0,0,0,0.15);"></th>
        """
        for f in formularios_ordenados:
            html += f'<th style="padding: 10px 14px; text-align: center; color: #000000; font-weight: 800; font-size: 14px; min-width: 110px; border-bottom: 2px solid #ccc; white-space: nowrap;">{f}</th>'
        html += "</tr></thead><tbody>"

        for idx, (label, tipo_fila) in enumerate(filas_config):
            if tipo_fila == "total":
                bg_color = "#6EB24B"
                text_color = "#FFFFFF"
                font_weight = "bold"
            elif tipo_fila == "yellow_header":
                bg_color = "#FFFF00"
                text_color = "#000000"
                font_weight = "bold"
            else:
                bg_color = "#FFFFFF"
                text_color = "#000000"
                font_weight = "normal"

            html += f'<tr style="background-color: {bg_color}; color: {text_color}; font-weight: {font_weight};">'
            html += f'<td style="padding: 8px 14px; text-align: left; position: sticky; left: 0; z-index: 2; background-color: {bg_color}; color: {text_color}; font-weight: {font_weight}; min-width: 175px; max-width: 175px; border-bottom: 1px solid #E6E6E6; box-shadow: 3px 0 5px -2px rgba(0,0,0,0.15);">{label}</td>'
            
            for f in formularios_ordenados:
                val = datos_evolutivo[f][idx]
                tot = datos_evolutivo[f][0]
                if es_porcentaje:
                    val_str = f"{(val / tot * 100):.1f}%" if tot > 0 else "0.0%"
                else:
                    val_str = f"{val:,}"
                html += f'<td style="padding: 8px 14px; text-align: center; border-bottom: 1px solid #E6E6E6; min-width: 110px; white-space: nowrap;">{val_str}</td>'
            html += '</tr>'

        html += "</tbody></table></div>"
        return html

    # CUADRO 1: CANTIDADES
    st.subheader("📊 Evolutivo de la Encuesta")
    st.markdown(renderizar_tabla_html(es_porcentaje=False), unsafe_allow_html=True)

    # CUADRO 2: PORCENTAJES
    st.subheader("📈 Evolutivo de la Encuesta (%)")
    st.markdown(renderizar_tabla_html(es_porcentaje=True), unsafe_allow_html=True)

    st.divider()

    # --- 6. CUADRO 3: ALERTAS Y PENDIENTES CON FILTRO DE FORMULARIO Y ESTADO ---
    st.subheader("⚠️ Alertas y Pendientes")

    # FILTROS INTEGRADOS DIRECTAMENTE EN LA SECCIÓN
    col_al1, col_al2 = st.columns(2)
    with col_al1:
        filtro_form = st.selectbox(
            "📋 Filtrar por Formulario:",
            ["Todos"] + formularios_ordenados[::-1],
            index=0,
            key="f_form_alertas"
        )
    with col_al2:
        filtro_estado = st.selectbox(
            "🔍 Filtrar por Estado:",
            ["Todos", "No comprobado", "Sin respuesta"],
            index=0,
            key="f_estado_alertas"
        )

    # EVALUACIÓN DE FORMULARIOS SEGÚN EL FILTRO SELECCIONADO
    if filtro_form == "Todos":
        dfs_alertas = []
        for f_name in formularios_ordenados[::-1]:
            df_eval_f = evaluar_formulario(f_name, df_objetivo_filtrado)
            df_eval_f['Formulario'] = f_name
            dfs_alertas.append(df_eval_f)
        df_activo = pd.concat(dfs_alertas, ignore_index=True) if dfs_alertas else pd.DataFrame()
    else:
        df_activo = evaluar_formulario(filtro_form, df_objetivo_filtrado)
        df_activo['Formulario'] = filtro_form

    df_alertas_base = df_activo[df_activo['Estado'].isin(['No comprobado', 'Sin respuesta'])].copy()

    df_alertas = df_alertas_base.copy()
    if filtro_estado != "Todos":
        df_alertas = df_alertas[df_alertas['Estado'] == filtro_estado]

    cols_orden = ['Formulario', 'Regional', 'Supervisor', 'Terminal', 'Estado', 'Intentos', 'Evidencia']
    df_mostrar = df_alertas[[c for c in cols_orden if c in df_alertas.columns]]

    if df_mostrar.empty:
        st.success("🎉 ¡Excelente! No hay pendientes registrados bajo los filtros seleccionados.")
    else:
        st.dataframe(
            df_mostrar,
            use_container_width=True,
            height=380,
            hide_index=True,
            column_config={
                "Intentos": st.column_config.NumberColumn(
                    "Intentos",
                    help="Número de intentos de validación registrados",
                    format="%d"
                ),
                "Evidencia": st.column_config.LinkColumn(
                    "Evidencia",
                    help="Haz clic para ver la fotografía de la encuesta",
                    validate=r"^https?://.*",
                    display_text="👁️ Ver Foto"
                )
            }
        )

        if st.button("📋 Copiar Pendientes de Pozo para WhatsApp", key="btn_wsp_pozo"):
            lineas = [
                f"Form: {r['Formulario']} | Term: {r['Terminal']} | Reg: {r['Regional']} | Sup: {r['Supervisor']} | Estado: {r['Estado']} | Intentos: {r['Intentos']}" + (f" | Foto: {r['Evidencia']}" if pd.notna(r['Evidencia']) else "")
                for _, r in df_mostrar.iterrows()
            ]
            st.code("\n".join(lineas), language=None)
