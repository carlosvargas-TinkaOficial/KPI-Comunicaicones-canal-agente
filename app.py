import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re

# --- FUNCIÓN DE LIMPIEZA Y CORRECCIÓN DE URLs (.jpe -> .jpeg) ---
def limpiar_url_evidencia(url):
    if not url or pd.isna(url):
        return None
    url_str = str(url).strip()
    if url_str == "" or url_str.lower() in ["nan", "none", "-", "null"]:
        return None
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

# --- NORMALIZACIÓN Y ORDENAMIENTO CRONOLÓGICO RÁPIDO ---
def ordenar_base_pozos_cronologicamente(df):
    col_f = next((c for c in df.columns if str(c).strip().upper() == 'FECHA'), None)
    col_h = next((c for c in df.columns if str(c).strip().upper() == 'HORA'), None)
    
    if not col_f:
        return df

    def conv_fecha(val):
        if pd.isna(val):
            return "1970-01-01"
        if hasattr(val, 'strftime'):
            return val.strftime('%Y-%m-%d')
        s = str(val).strip().split(' ')[0]
        if '/' in s:
            partes = s.split('/')
            if len(partes) == 3:
                if len(partes[2]) == 4:
                    return f"{partes[2]}-{int(partes[1]):02d}-{int(partes[0]):02d}"
                elif len(partes[0]) == 4:
                    return f"{partes[0]}-{int(partes[1]):02d}-{int(partes[2]):02d}"
        return s

    def conv_hora(val):
        if pd.isna(val):
            return "00:00:00"
        if hasattr(val, 'strftime'):
            return val.strftime('%H:%M:%S')
        s = str(val).strip()
        if ' ' in s:
            s = s.split(' ')[-1]
        return s

    fechas_norm = df[col_f].apply(conv_fecha)
    horas_norm = df[col_h].apply(conv_hora) if col_h else "00:00:00"
    
    dt_combined = pd.to_datetime(fechas_norm + ' ' + horas_norm, errors='coerce')
    df['_FECHA_HORA_ORDEN'] = dt_combined
    return df.sort_values(by=['_FECHA_HORA_ORDEN'], ascending=True).reset_index(drop=True)

# --- MOTOR DE PROCESAMIENTO CON ALTA VELOCIDAD Y CACHÉ ---
@st.cache_data(ttl=600, show_spinner=False)
def cargar_y_precomputar_pozos(bytes_pozos, bytes_inasistencias):
    # 1. Diccionario de Tipo de Punto desde Inasistencias
    dict_tipos = {}
    if bytes_inasistencias:
        try:
            df_inas_data = pd.read_excel(bytes_inasistencias)
            df_inas_data = df_inas_data.rename(columns={c: str(c).strip() for c in df_inas_data.columns})
            col_t_inas = next((c for c in df_inas_data.columns if str(c).upper() in ['TERMINAL', 'USERNAME']), None)
            if not col_t_inas:
                col_t_inas = next((c for c in df_inas_data.columns if any(w in str(c).lower() for w in ['terminal', 'username', 'codigo', 'código'])), None)
            col_tipo_inas = next((c for c in df_inas_data.columns if str(c).upper() == 'TIPO'), None)
            if not col_tipo_inas:
                col_tipo_inas = next((c for c in df_inas_data.columns if 'tipo' in str(c).lower()), None)
            if col_t_inas and col_tipo_inas:
                df_inas_data['T_CLEAN'] = df_inas_data[col_t_inas].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
                df_inas_data['TIPO_CLEAN'] = df_inas_data[col_tipo_inas].astype(str).str.strip()
                dict_tipos = df_inas_data.dropna(subset=['T_CLEAN', 'TIPO_CLEAN']).drop_duplicates(subset=['T_CLEAN']).set_index('T_CLEAN')['TIPO_CLEAN'].to_dict()
        except Exception:
            pass

    # 2. Hojas de Pozos
    xl = pd.ExcelFile(bytes_pozos)
    nombres_hojas = xl.sheet_names
    hoja_encuestas = next((h for h in nombres_hojas if '1' in h or 'pozo' in h.lower()), nombres_hojas[0])
    df_pozos_raw = pd.read_excel(xl, sheet_name=hoja_encuestas)
    
    if "Hoja 2" in nombres_hojas:
        df_obj_raw = pd.read_excel(xl, sheet_name="Hoja 2")
    elif len(nombres_hojas) > 1:
        df_obj_raw = pd.read_excel(xl, sheet_name=nombres_hojas[1])
    else:
        df_obj_raw = df_pozos_raw

    # 3. Directorio Objetivo (Hoja 2)
    df_obj = df_obj_raw.rename(columns={c: str(c).strip() for c in df_obj_raw.columns})
    col_term_obj = next((c for c in df_obj.columns if any(w in str(c).lower() for w in ['código', 'codigo', 'terminal', 'username'])), None)
    df_obj['TERMINAL_CLEAN'] = df_obj[col_term_obj].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    
    col_terr = next((c for c in df_obj.columns if 'territorial' in str(c).lower()), None)
    col_reg = next((c for c in df_obj.columns if str(c).strip().upper() == 'REG'), None)
    col_sup = next((c for c in df_obj.columns if str(c).strip().upper() == 'SUP'), None)
    if not col_reg:
        col_reg = next((c for c in df_obj.columns if any(w in str(c).lower() for w in ['regional', 'jerarquia'])), None)
    if not col_sup:
        col_sup = next((c for c in df_obj.columns if 'supervisor' in str(c).lower()), None)

    def asignar_regional_supervisor(row):
        terr_val = str(row[col_terr]).strip() if (col_terr and pd.notna(row[col_terr])) else ''
        sup_val = str(row[col_sup]).strip() if (col_sup and pd.notna(row[col_sup])) else ''
        reg_val = str(row[col_reg]).strip() if (col_reg and pd.notna(row[col_reg])) else ''
        if 'edgar padilla' in terr_val.lower():
            return sup_val if sup_val and sup_val.lower() not in ['nan', 'none', '-'] else reg_val
        if reg_val and reg_val.lower() not in ['nan', 'none', '-']:
            return reg_val
        return sup_val if sup_val and sup_val.lower() not in ['nan', 'none', '-'] else terr_val

    df_obj['Regional / supervisor'] = df_obj.apply(asignar_regional_supervisor, axis=1)
    df_universo = df_obj[['TERMINAL_CLEAN', col_terr, 'Regional / supervisor']].dropna(subset=['TERMINAL_CLEAN']).drop_duplicates(subset=['TERMINAL_CLEAN'])
    df_universo = df_universo.rename(columns={'TERMINAL_CLEAN': 'TERMINAL', col_terr: 'Territorial'})
    df_universo['Tipo de Punto'] = df_universo['TERMINAL'].map(dict_tipos).fillna('-')

    # 4. Respuestas de Pozos
    df_p = df_pozos_raw.rename(columns={c: str(c).strip() for c in df_pozos_raw.columns})
    col_term_p = next((c for c in df_p.columns if any(w in str(c).lower() for w in ['terminal', 'username', 'código', 'codigo'])), None)
    df_p['TERMINAL'] = df_p[col_term_p].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    col_url = next((c for c in df_p.columns if any(w in str(c).lower() for w in ['url', 'link', 'foto', 'image', 'imagen', 'evidencia'])), None)
    df_p = ordenar_base_pozos_cronologicamente(df_p)

    formularios_validos = [f for f in df_p['FORMULARIO'].dropna().unique().tolist() if 'POZO' in str(f).upper() and 'NL' not in str(f).upper()]
    formularios_ordenados = ordenar_formularios_por_fecha(formularios_validos)

    # 5. Precomputación Vectorizada de Todos los Formularios
    master_eval_list = []
    for form in formularios_ordenados:
        sub_form = df_p[df_p['FORMULARIO'] == form]
        res_list = []
        
        if not sub_form.empty:
            for term, group in sub_form.groupby('TERMINAL', sort=False):
                num_intentos = len(group)
                ultimo_reg = group.iloc[-1]
                ultimo_res = str(ultimo_reg.get('RESULTADO', '')).strip().lower()
                resultados_todos = [str(r).strip().lower() for r in group['RESULTADO'].dropna().tolist()]
                
                tiene_match = any('match' in r and 'no_match' not in r for r in resultados_todos)
                ultimo_es_match = ('match' in ultimo_res and 'no_match' not in ultimo_res)
                
                url_val = None
                if col_url:
                    fotos_validas = group[
                        group[col_url].notna() &
                        (~group[col_url].astype(str).str.strip().str.lower().isin(['', '-', 'none', 'nan', 'null']))
                    ]
                    if not fotos_validas.empty:
                        raw_url = fotos_validas[col_url].iloc[-1]
                        url_val = limpiar_url_evidencia(raw_url)
                
                if ultimo_es_match:
                    estado = "True - 1er intento" if num_intentos == 1 else "True - 2do intento"
                    url_val = None
                elif tiene_match:
                    estado = "True - 2do intento"
                    url_val = None
                else:
                    estado = "No comprobado"

                res_list.append({
                    'TERMINAL': term,
                    'Estado': estado,
                    'Intentos': num_intentos,
                    'Evidencia': url_val
                })
        
        df_summary = pd.DataFrame(res_list) if res_list else pd.DataFrame(columns=['TERMINAL', 'Estado', 'Intentos', 'Evidencia'])
        
        merged = df_universo.merge(df_summary, on='TERMINAL', how='left')
        merged['Formulario'] = form
        merged['Estado'] = merged['Estado'].fillna('Sin respuesta')
        merged['Intentos'] = merged['Intentos'].fillna(0).astype(int)
        
        master_eval_list.append(merged)

    df_master = pd.concat(master_eval_list, ignore_index=True) if master_eval_list else pd.DataFrame()
    return df_universo, df_master, formularios_ordenados

# --- FUNCIÓN PRINCIPAL DEL MÓDULO ---
def mostrar_modulo(api_key, bytes_pozos, bytes_inasistencias=None):
    st.title("📋 Resultado Encuesta de Pozo")
    
    if not bytes_pozos:
        st.warning("⚠️ No se pudo cargar el archivo Data_Pozos desde Google Drive.")
        return

    with st.spinner("⚡ Cargando datos consolidados..."):
        df_universo, df_master, formularios_ordenados = cargar_y_precomputar_pozos(bytes_pozos, bytes_inasistencias)

    if df_master.empty or not formularios_ordenados:
        st.warning("No se encontraron formularios válidos de Pozo para procesar.")
        return

    forms_dropdown = formularios_ordenados[::-1] + ["Todos"]

    # --- 1. FILTROS PRINCIPALES SUPERIORES ---
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        selected_form = st.selectbox("📋 1. Formulario:", forms_dropdown, index=0)
    with col_f2:
        territoriales = ["Todos"] + sorted(df_universo['Territorial'].dropna().unique().tolist())
        selected_terr = st.selectbox("🎯 2. Territorial:", territoriales)

    df_u_terr = df_universo if selected_terr == "Todos" else df_universo[df_universo['Territorial'] == selected_terr]
    with col_f3:
        supervisores = ["Todos"] + sorted(df_u_terr['Regional / supervisor'].dropna().unique().tolist())
        selected_sup = st.selectbox("👔 3. Regional / supervisor:", supervisores)

    df_u_sup = df_u_terr if selected_sup == "Todos" else df_u_terr[df_u_terr['Regional / supervisor'] == selected_sup]

    tipos_disponibles = sorted([str(x).strip() for x in df_universo['Tipo de Punto'].dropna().unique() if str(x).strip() not in ['', '-']])
    if not tipos_disponibles:
        tipos_disponibles = ['FQ', 'PR']
    with col_f4:
        selected_tipo = st.selectbox("🏪 4. Tipo de Punto:", ["Todos"] + tipos_disponibles)

    # Filtrado global por Territorial, Supervisor y Tipo de Punto
    df_filtrado_global = df_master.copy()
    if selected_terr != "Todos":
        df_filtrado_global = df_filtrado_global[df_filtrado_global['Territorial'] == selected_terr]
    if selected_sup != "Todos":
        df_filtrado_global = df_filtrado_global[df_filtrado_global['Regional / supervisor'] == selected_sup]
    if selected_tipo != "Todos":
        df_filtrado_global = df_filtrado_global[df_filtrado_global['Tipo de Punto'] == selected_tipo]

    # --- 2. CUADROS EVOLUTIVOS (HISTÓRICO PERMANENTE) ---
    datos_evolutivo = {}
    for form in formularios_ordenados:
        sub_form = df_filtrado_global[df_filtrado_global['Formulario'] == form]
        tot_pts = len(sub_form)
        t_1er = (sub_form['Estado'] == 'True - 1er intento').sum()
        t_2do = (sub_form['Estado'] == 'True - 2do intento').sum()
        tot_comp = t_1er + t_2do
        n_comp = (sub_form['Estado'] == 'No comprobado').sum()
        s_resp = (sub_form['Estado'] == 'Sin respuesta').sum()
        tot_no_comp = n_comp + s_resp
        
        datos_evolutivo[form] = [tot_pts, tot_comp, t_1er, t_2do, tot_no_comp, n_comp, s_resp]

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
                bg_color = "#6EB24B"; text_color = "#FFFFFF"; font_weight = "bold"
            elif tipo_fila == "yellow_header":
                bg_color = "#FFFF00"; text_color = "#000000"; font_weight = "bold"
            else:
                bg_color = "#FFFFFF"; text_color = "#000000"; font_weight = "normal"

            html += f'<tr style="background-color: {bg_color}; color: {text_color}; font-weight: {font_weight};">'
            html += f'<td style="padding: 8px 14px; text-align: left; position: sticky; left: 0; z-index: 2; background-color: {bg_color}; color: {text_color}; font-weight: {font_weight}; min-width: 175px; max-width: 175px; border-bottom: 1px solid #E6E6E6; box-shadow: 3px 0 5px -2px rgba(0,0,0,0.15);">{label}</td>'
            
            for f in formularios_ordenados:
                val = datos_evolutivo[f][idx]
                tot = datos_evolutivo[f][0]
                val_str = f"{(val / tot * 100):.1f}%" if es_porcentaje and tot > 0 else f"{val:,}"
                html += f'<td style="padding: 8px 14px; text-align: center; border-bottom: 1px solid #E6E6E6; min-width: 110px; white-space: nowrap;">{val_str}</td>'
            html += '</tr>'

        html += "</tbody></table></div>"
        return html

    st.subheader("📊 Evolutivo de la Encuesta")
    st.markdown(renderizar_tabla_html(es_porcentaje=False), unsafe_allow_html=True)

    st.subheader("📈 Evolutivo de la Encuesta (%)")
    st.markdown(renderizar_tabla_html(es_porcentaje=True), unsafe_allow_html=True)

    st.divider()

    # --- 3. NUEVOS GRÁFICOS EJECUTIVOS (EMBUDO IA, VELOCÍMETRO META 85% Y COMPOSICIÓN 100%) ---
    df_eval_total = df_filtrado_global[df_filtrado_global['Formulario'] == selected_form] if selected_form != "Todos" else df_filtrado_global
    plotly_config = {'scrollZoom': False, 'displayModeBar': False, 'doubleClick': 'reset'}

    if not df_eval_total.empty:
        # Cálculos para Embudo y Medidor
        tot_term = len(df_eval_total)
        sin_resp = (df_eval_total['Estado'] == 'Sin respuesta').sum()
        con_resp = tot_term - sin_resp
        kpi_1er = (df_eval_total['Estado'] == 'True - 1er intento').sum()
        kpi_2do = (df_eval_total['Estado'] == 'True - 2do intento').sum()
        kpi_aprob = kpi_1er + kpi_2do

        pct_resp = int(round((con_resp / tot_term * 100))) if tot_term > 0 else 0
        pct_aprob = int(round((kpi_aprob / tot_term * 100))) if tot_term > 0 else 0
        pct_1er = int(round((kpi_1er / tot_term * 100))) if tot_term > 0 else 0

        col_top1, col_top2 = st.columns(2)

        # GRÁFICO 1: EMBUDO VALIDACIÓN IA
        with col_top1:
            fig_funnel = go.Figure(go.Funnel(
                y=["Total Terminales", "Con Respuesta", "KPI Aprobadas", "KPI 1er Intento"],
                x=[tot_term, con_resp, kpi_aprob, kpi_1er],
                text=[
                    f"{tot_term:,}",
                    f"{con_resp:,} ({pct_resp}%)",
                    f"{kpi_aprob:,} ({pct_aprob}%)",
                    f"{kpi_1er:,} ({pct_1er}%)"
                ],
                textinfo="text",
                textposition="inside",
                textfont=dict(color="white", size=14, family="Arial"),
                marker=dict(
                    color=["#033E24", "#086333", "#119925", "#0BB76D"]
                ),
                connector=dict(visible=False)
            ))
            fig_funnel.update_layout(
                title=dict(text="Embudo Validación IA", font=dict(size=17, color="#000000"), x=0.02, y=0.95),
                paper_bgcolor="#FFFFFF",
                plot_bgcolor="#FFFFFF",
                margin=dict(l=140, r=20, t=55, b=20),
                height=320,
                yaxis=dict(tickfont=dict(color="#444444", size=13))
            )
            st.plotly_chart(fig_funnel, use_container_width=True, config=plotly_config)

        # GRÁFICO 2: AVANCE GLOBAL VS META (MEDIDOR SEMICIRCULAR)
        with col_top2:
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=pct_aprob,
                number={'suffix': " %", 'font': {'size': 46, 'color': '#555555'}},
                gauge={
                    'axis': {
                        'range': [0, 100],
                        'tickmode': 'array',
                        'tickvals': [0, 85, 100],
                        'ticktext': ['0 %', '85 %', '100 %'],
                        'tickwidth': 1,
                        'tickcolor': "#555555",
                        'tickfont': {'size': 15, 'color': '#555555'}
                    },
                    'bar': {'color': "#119925", 'thickness': 1},
                    'bgcolor': "#E6E0D8",
                    'borderwidth': 0,
                    'threshold': {
                        'line': {'color': "#033E24", 'width': 3},
                        'thickness': 1,
                        'value': 85
                    }
                }
            ))
            fig_gauge.update_layout(
                title=dict(text="Avance Global vs Meta", font=dict(size=17, color="#000000"), x=0.02, y=0.95),
                paper_bgcolor="#FFFFFF",
                margin=dict(l=30, r=30, t=65, b=20),
                height=320
            )
            st.plotly_chart(fig_gauge, use_container_width=True, config=plotly_config)

        # GRÁFICO 3: COMPOSICIÓN ESTADOS POR TERRITORIAL (BARRAS 100% APILADAS)
        col_bot1, col_bot2 = st.columns([1.15, 0.85])
        with col_bot1:
            df_comp = df_eval_total.copy()
            df_comp['Cat_Estado'] = df_comp['Estado'].apply(
                lambda x: 'Aprobadas' if 'True' in str(x) else ('No Comprobado' if x == 'No comprobado' else 'Sin Respuesta')
            )
            
            # Agrupar y calcular porcentajes sobre el total de cada territorial
            grp_terr = df_comp.groupby(['Territorial', 'Cat_Estado']).size().unstack(fill_value=0)
            for col_req in ['Aprobadas', 'No Comprobado', 'Sin Respuesta']:
                if col_req not in grp_terr.columns:
                    grp_terr[col_req] = 0
            
            grp_terr['Total'] = grp_terr[['Aprobadas', 'No Comprobado', 'Sin Respuesta']].sum(axis=1)
            grp_terr = grp_terr.sort_values('Total', ascending=True)

            fig_comp = go.Figure()
            colores_comp = {
                'Aprobadas': '#119925',
                'No Comprobado': '#F7567C',
                'Sin Respuesta': '#E65C19'
            }

            for estado_cat in ['Aprobadas', 'No Comprobado', 'Sin Respuesta']:
                pct_vals = (grp_terr[estado_cat] / grp_terr['Total'] * 100).round(0).astype(int)
                text_labels = [f"{v}%" if v >= 4 else "" for v in pct_vals]
                
                fig_comp.add_trace(go.Bar(
                    name=estado_cat,
                    y=grp_terr.index,
                    x=pct_vals,
                    orientation='h',
                    marker=dict(color=colores_comp[estado_cat]),
                    text=text_labels,
                    textposition='inside',
                    insidetextanchor='middle',
                    textfont=dict(color='white', size=12, family="Arial")
                ))

            fig_comp.update_layout(
                title=dict(text="Composición Estados por Territorial", font=dict(size=17, color="#000000"), x=0.02, y=0.96),
                barmode='stack',
                paper_bgcolor="#FFFFFF",
                plot_bgcolor="#FFFFFF",
                height=340,
                margin=dict(l=140, r=20, t=75, b=35),
                xaxis=dict(
                    range=[0, 100],
                    tickvals=[0, 50, 100],
                    ticktext=['0%', '50%', '100%'],
                    showgrid=True,
                    gridcolor="#EEEEEE",
                    tickfont=dict(color="#666666")
                ),
                yaxis=dict(tickfont=dict(color="#555555", size=13)),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="center",
                    x=0.5,
                    font=dict(size=12, color="#333333")
                )
            )
            st.plotly_chart(fig_comp, use_container_width=True, config=plotly_config)

        st.divider()

    # --- 4. ANÁLISIS SEGÚN TERRITORIAL Y ANÁLISIS SEGÚN REGIONAL ---
    titulo_graficos = f"📊 Análisis de Desempeño y Cobertura ({selected_form})" if selected_form != "Todos" else "📊 Análisis de Desempeño y Cobertura (Consolidado)"
    st.subheader(titulo_graficos)

    modo_metrica = st.radio("Selecciona la métrica a visualizar:", ["Pendientes", "Cumplimiento"], horizontal=True, key="radio_modo_analisis")
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.markdown("#### 📍 Análisis según territorial")
        if not df_eval_total.empty:
            if modo_metrica == "Pendientes":
                df_terr_pend = df_eval_total[df_eval_total['Estado'].isin(['No comprobado', 'Sin respuesta'])]
                if not df_terr_pend.empty:
                    df_t_grp = df_terr_pend.groupby(['Territorial', 'Estado']).size().reset_index(name='Cantidad')
                    fig_terr = px.bar(
                        df_t_grp, y='Territorial', x='Cantidad', color='Estado', orientation='h', barmode='stack',
                        color_discrete_map={'No comprobado': '#FF6700', 'Sin respuesta': '#D9381E'}, text='Cantidad'
                    )
                    fig_terr.update_traces(textposition='inside', insidetextanchor='middle')
                    fig_terr.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis_title="Pozo No Comprobado", yaxis_title="", legend_title="", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig_terr, use_container_width=True, config=plotly_config)
                else:
                    st.success("🎉 No hay pendientes registrados en Territorial.")
            else:
                df_t_tot = df_eval_total.groupby('Territorial').agg(Total=('TERMINAL', 'count'), Comprobados=('Estado', lambda x: x.str.contains('True').sum())).reset_index()
                df_t_tot['% Cumplimiento'] = (df_t_tot['Comprobados'] / df_t_tot['Total'] * 100).round(1)
                df_t_tot = df_t_tot.sort_values('% Cumplimiento', ascending=True)

                fig_terr = px.bar(df_t_tot, y='Territorial', x='% Cumplimiento', orientation='h', text=df_t_tot['% Cumplimiento'].apply(lambda x: f"{x:.1f}%"), color_discrete_sequence=['#096045'])
                fig_terr.update_traces(textposition='outside')
                fig_terr.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis_title="% de Cumplimiento", yaxis_title="", xaxis=dict(range=[0, 115]))
                st.plotly_chart(fig_terr, use_container_width=True, config=plotly_config)

    with col_g2:
        st.markdown("#### 👤 Análisis según regional")
        if not df_eval_total.empty:
            if modo_metrica == "Pendientes":
                df_sup_pend = df_eval_total[df_eval_total['Estado'].isin(['No comprobado', 'Sin respuesta'])]
                if not df_sup_pend.empty:
                    df_s_grp = df_sup_pend.groupby(['Regional / supervisor', 'Estado']).size().reset_index(name='Cantidad')
                    fig_sup = px.bar(
                        df_s_grp, y='Regional / supervisor', x='Cantidad', color='Estado', orientation='h', barmode='stack',
                        color_discrete_map={'No comprobado': '#FF6700', 'Sin respuesta': '#D9381E'}, text='Cantidad'
                    )
                    fig_sup.update_traces(textposition='inside', insidetextanchor='middle')
                    fig_sup.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis_title="Pozo No Comprobado", yaxis_title="", legend_title="", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig_sup, use_container_width=True, config=plotly_config)
                else:
                    st.success("🎉 No hay pendientes registrados en Regional / supervisor.")
            else:
                df_s_tot = df_eval_total.groupby('Regional / supervisor').agg(Total=('TERMINAL', 'count'), Comprobados=('Estado', lambda x: x.str.contains('True').sum())).reset_index()
                df_s_tot['% Cumplimiento'] = (df_s_tot['Comprobados'] / df_s_tot['Total'] * 100).round(1)
                df_s_tot = df_s_tot.sort_values('% Cumplimiento', ascending=True)

                fig_sup = px.bar(df_s_tot, y='Regional / supervisor', x='% Cumplimiento', orientation='h', text=df_s_tot['% Cumplimiento'].apply(lambda x: f"{x:.1f}%"), color_discrete_sequence=['#096045'])
                fig_sup.update_traces(textposition='outside')
                fig_sup.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis_title="% de Cumplimiento", yaxis_title="", xaxis=dict(range=[0, 115]))
                st.plotly_chart(fig_sup, use_container_width=True, config=plotly_config)

    st.divider()

    # --- 5. ALERTAS Y PENDIENTES ---
    st.subheader("⚠️ Alertas y Pendientes")

    col_al1, col_al2, col_al3 = st.columns(3)
    with col_al1:
        opciones_form_alertas = formularios_ordenados[::-1] + ["Todos"]
        filtro_form_al = st.selectbox("📋 Filtrar por Formulario:", opciones_form_alertas, index=0, key="f_form_alertas_sub")
    with col_al2:
        lista_sups = ["Todos"] + sorted(df_filtrado_global['Regional / supervisor'].dropna().unique().tolist())
        filtro_sup_al = st.selectbox("👔 Filtrar por Supervisor:", lista_sups, index=0, key="f_sup_alertas_sub")
    with col_al3:
        filtro_estado_al = st.selectbox("🔍 Filtrar por Estado:", ["Todos", "No comprobado", "Sin respuesta"], index=0, key="f_estado_alertas_sub")

    df_alertas_raw = df_filtrado_global if filtro_form_al == "Todos" else df_filtrado_global[df_filtrado_global['Formulario'] == filtro_form_al]
    if filtro_sup_al != "Todos":
        df_alertas_raw = df_alertas_raw[df_alertas_raw['Regional / supervisor'] == filtro_sup_al]

    df_pendientes_base = df_alertas_raw[df_alertas_raw['Estado'].isin(['No comprobado', 'Sin respuesta'])].copy()

    cant_no_comp = int((df_pendientes_base['Estado'] == 'No comprobado').sum())
    cant_sin_resp = int((df_pendientes_base['Estado'] == 'Sin respuesta').sum())

    card1, card2 = st.columns(2)
    card1.metric("Cantidad No Comprobados", f"{cant_no_comp:,}")
    card2.metric("Cantidad de Sin Respuesta", f"{cant_sin_resp:,}")

    df_tabla_final = df_pendientes_base.copy()
    if filtro_estado_al != "Todos":
        df_tabla_final = df_tabla_final[df_tabla_final['Estado'] == filtro_estado_al]

    cols_orden = ['Formulario', 'Territorial', 'Regional / supervisor', 'Tipo de Punto', 'TERMINAL', 'Estado', 'Intentos', 'Evidencia']
    df_mostrar = df_tabla_final[[c for c in cols_orden if c in df_tabla_final.columns]].rename(columns={'TERMINAL': 'Terminal'})

    if df_mostrar.empty:
        st.success("🎉 ¡Excelente! No hay pendientes registrados bajo los filtros seleccionados.")
    else:
        st.dataframe(
            df_mostrar,
            use_container_width=True,
            height=380,
            hide_index=True,
            column_config={
                "Intentos": st.column_config.NumberColumn("Intentos", format="%d"),
                "Evidencia": st.column_config.LinkColumn("Evidencia", validate=r"^https?://.*", display_text="👁️ Ver Foto")
            }
        )

        if st.button("📋 Copiar Pendientes de Pozo para WhatsApp", key="btn_wsp_pozo"):
            lineas = [
                f"Form: {r['Formulario']} | Term: {r['Terminal']} ({r.get('Tipo de Punto', '-')}) | Terr: {r['Territorial']} | Sup: {r['Regional / supervisor']} | Estado: {r['Estado']} | Intentos: {r['Intentos']}" + (f" | Foto: {r['Evidencia']}" if pd.notna(r['Evidencia']) else "")
                for _, r in df_mostrar.iterrows()
            ]
            st.code("\n".join(lineas), language=None)
