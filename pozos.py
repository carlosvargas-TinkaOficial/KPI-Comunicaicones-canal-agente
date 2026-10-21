import streamlit as st
import pandas as pd
import re

def ordenar_formularios_por_fecha(forms):
    def clave_fecha(f):
        m = re.search(r'(\d{2})(\d{2})(\d{4})', str(f))
        if m:
            d, mo, y = m.groups()
            return f"{y}-{mo}-{d}"
        return str(f)
    return sorted(forms, key=clave_fecha)

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
    
    # Universo de terminales únicos objetivo
    df_universo = df_inas[['TERMINAL_CLEAN', col_reg, col_sup]].dropna(subset=['TERMINAL_CLEAN']).drop_duplicates(subset=['TERMINAL_CLEAN'])
    df_universo = df_universo.rename(columns={'TERMINAL_CLEAN': 'TERMINAL', col_reg: 'Regional', col_sup: 'Supervisor'})

    # --- 2. FILTRADO Y LIMPIEZA DE DATA_POZOS ---
    df_p = df_pozos_raw.rename(columns={c: str(c).strip() for c in df_pozos_raw.columns})
    col_term_p = 'TERMINAL' if 'TERMINAL' in df_p.columns else ('USERNAME' if 'USERNAME' in df_p.columns else None)
    if not col_term_p:
        st.error("No se encontró la columna TERMINAL en Data_Pozos.")
        return
    df_p['TERMINAL'] = df_p[col_term_p].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)

    # Identificar columna de URL si existe
    col_url = next((c for c in df_p.columns if any(w in c.lower() for w in ['url', 'link', 'foto', 'image', 'imagen'])), None)

    # REGLA 3: Formularios con 'POZO' y sin 'NL'
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
    forms_dropdown = formularios_ordenados[::-1]

    # --- 3. FILTROS PRINCIPALES ---
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        selected_form = st.selectbox("📋 1. Formulario:", forms_dropdown, index=0)
    
    with col_f2:
        regionales = ["Todos"] + sorted(df_universo['Regional'].dropna().unique().tolist())
        selected_reg = st.selectbox("🎯 2. Regional:", regionales)

    df_u_reg = df_universo if selected_reg == "Todos" else df_universo[df_universo['Regional'] == selected_reg]
    with col_f3:
        supervisores = ["Todos"] + sorted(df_u_reg['Supervisor'].dropna().unique().tolist())
        selected_sup = st.selectbox("👔 3. Supervisor:", supervisores)

    # Base objetivo final según filtros seleccionados
    df_objetivo_filtrado = df_u_reg if selected_sup == "Todos" else df_u_reg[df_u_reg['Supervisor'] == selected_sup]

    # --- 4. FUNCIÓN EVALUADORA POR FORMULARIO ---
    def evaluar_formulario(form_name, base_objetivo):
        df_sub = df_p[df_p['FORMULARIO'] == form_name]
        registros = []
        
        for _, row in base_objetivo.iterrows():
            term = row['TERMINAL']
            reg = row['Regional']
            sup = row['Supervisor']
            
            puntos_term = df_sub[df_sub['TERMINAL'] == term]
            
            if puntos_term.empty:
                estado = "Sin respuesta"
                url_val = "-"
            else:
                resultados = puntos_term['RESULTADO'].astype(str).str.lower().tolist()
                tiene_match = any('match' == r for r in resultados)
                tiene_no_match = any('no_match' == r for r in resultados)
                
                url_val = puntos_term[col_url].dropna().iloc[-1] if (col_url and not puntos_term[col_url].dropna().empty) else "-"
                
                if tiene_match:
                    if not tiene_no_match and len(puntos_term) == 1:
                        estado = "True - 1er intento"
                    else:
                        estado = "True - 2do intento"
                    url_val = "-"
                else:
                    estado = "No comprobado"

            registros.append({
                'Regional': reg,
                'Supervisor': sup,
                'Terminal': term,
                'Estado': estado,
                'URL': url_val
            })
        return pd.DataFrame(registros)

    # --- 5. CUADRO 1: EVOLUTIVO DE LA ENCUESTA (DISEÑO IDÉNTICO A LA CAPTURA) ---
    st.subheader("📊 Evolutivo de la Encuesta")

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

    # Renderizado HTML con estilos visuales de tu imagen
    html_table = """
    <div style="overflow-x: auto; margin-bottom: 25px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.08);">
    <table style="width: 100%; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, sans-serif; font-size: 14px;">
        <thead>
            <tr style="border-bottom: 2px solid #ccc; background-color: #FFFFFF;">
                <th style="padding: 10px 14px; text-align: left; color: #000000; font-weight: 800;"></th>
    """
    for f in formularios_ordenados:
        html_table += f'<th style="padding: 10px 14px; text-align: center; color: #000000; font-weight: 800; font-size: 14px;">{f}</th>'
    html_table += "</tr></thead><tbody>"

    for idx, (label, tipo_fila) in enumerate(filas_config):
        if tipo_fila == "total":
            style_tr = "background-color: #6EB24B; color: #FFFFFF; font-weight: bold;"
        elif tipo_fila == "yellow_header":
            style_tr = "background-color: #FFFF00; color: #000000; font-weight: bold;"
        else:
            style_tr = "background-color: #FFFFFF; color: #000000;"

        html_table += f'<tr style="{style_tr}; border-bottom: 1px solid #E6E6E6;">'
        html_table += f'<td style="padding: 8px 14px; text-align: left;">{label}</td>'
        for f in formularios_ordenados:
            val = datos_evolutivo[f][idx]
            html_table += f'<td style="padding: 8px 14px; text-align: center;">{val:,}</td>'
        html_table += '</tr>'

    html_table += "</tbody></table></div>"
    st.markdown(html_table, unsafe_allow_html=True)

    st.divider()

    # --- 6. CUADRO 2: ALERTAS Y PENDIENTES ---
    st.subheader(f"⚠️ Alertas y Pendientes ({selected_form})")
    
    df_activo = evaluar_formulario(selected_form, df_objetivo_filtrado)
    
    # Filtrar únicamente los no comprobados y sin respuesta
    df_alertas = df_activo[df_activo['Estado'].isin(['No comprobado', 'Sin respuesta'])].copy()
    
    # Orden de columnas solicitado
    cols_mostrar = ['Regional', 'Supervisor', 'Terminal', 'Estado', 'URL']
    df_alertas = df_alertas[[c for c in cols_mostrar if c in df_alertas.columns]]

    if df_alertas.empty:
        st.success("🎉 ¡Excelente! Todos los terminales tienen estado comprobado en este formulario.")
    else:
        st.dataframe(
            df_alertas,
            use_container_width=True,
            height=340,
            column_config={
                "URL": st.column_config.LinkColumn("URL Evidencia")
            }
        )

        # Botón para gestión directa en WhatsApp
        if st.button("📋 Copiar Pendientes de Pozo para WhatsApp", key="btn_wsp_pozo"):
            lineas = [
                f"Terminal: {r['Terminal']} | Reg: {r['Regional']} | Sup: {r['Supervisor']} | Estado: {r['Estado']} | Link: {r['URL']}"
                for _, r in df_alertas.iterrows()
            ]
            st.code("\n".join(lineas), language=None)
