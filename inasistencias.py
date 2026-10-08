import streamlit as st
import pandas as pd
import plotly.express as px
from google import genai

def mostrar_modulo(api_key, bytes_excel):
    st.title("🎯 Control de Inasistencia Conferencia Carlos Mazzetti")
    
    if not bytes_excel:
        st.warning("⚠️ No se pudo cargar la base de datos de Inasistencias desde Google Drive.")
        return
        
    try:
        df_inas = pd.read_excel(bytes_excel)
    except Exception:
        st.error("⚠️ Error al procesar la información de Inasistencias.")
        return
    
    # OBTENER CONFERENCIAS EN ORDEN (Más reciente primero)
    if 'post_titulo' in df_inas.columns:
        conf_unicas = df_inas['post_titulo'].dropna().unique().tolist()
        conf_list = conf_unicas[::-1]  # Invertido: la más reciente queda en posición 0
    else:
        conf_list = []

    # FILTROS PRINCIPALES DE LA PARTE SUPERIOR
    col1, col2 = st.columns(2)
    with col1:
        selected_conf = st.selectbox("📅 Seleccionar Conferencia:", conf_list, index=0 if conf_list else 0)
    
    df_c = df_inas[df_inas['post_titulo'] == selected_conf] if 'post_titulo' in df_inas.columns else df_inas

    with col2:
        terr_list = ["Todos"] + df_c['TERRITORIAL'].dropna().unique().tolist() if 'TERRITORIAL' in df_c.columns else ["Todos"]
        idx_fanny = terr_list.index("Fanny Alejo") if "Fanny Alejo" in terr_list else 0
        selected_terr = st.selectbox("🎯 Seleccionar Líder Territorial:", terr_list, index=idx_fanny)

    df_t = df_c if selected_terr == "Todos" else df_c[df_c['TERRITORIAL'] == selected_terr]

    tipos_pto = ["Todos"] + df_t['TIPO'].dropna().unique().tolist() if 'TIPO' in df_t.columns else ["Todos"]
    selected_tipo = st.selectbox("🏪 Filtrar por Tipo de Punto:", tipos_pto)
    df_tipo = df_t if selected_tipo == "Todos" else df_t[df_t['TIPO'] == selected_tipo]

    # COACHING IA TERRITORIAL
    with st.expander("💡 Recibe un consejo experto (Líder Territorial)", expanded=False):
        if st.button("🚀 Generar Diagnóstico Territorial", type="primary", key="btn_ia_terr"):
            if not api_key:
                st.error("API Key no configurada.")
            else:
                client = genai.Client(api_key=api_key)
                total_ausencias = len(df_tipo)
                prompt = f"""
                Actúa como un Director Comercial Senior de La Tinka.
                Genera un diagnóstico estratégico corto para la conferencia '{selected_conf}' del territorio '{selected_terr}'.
                Actualmente se registran {total_ausencias} inasistencias acumuladas.
                
                Estructura tu respuesta en 3 puntos claros:
                1. Estado de Alerta (Breve evaluación cuantitativa).
                2. Enfoque Táctico (Próximas 24 horas).
                3. Mensaje Motivacional para WhatsApp.
                """
                with st.spinner("Generando coaching con Gemini..."):
                    try:
                        res = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
                        st.markdown(res.text)
                    except Exception as e:
                        st.error(f"Error al conectar con la IA: {e}")

    # MÉTRICAS
    c1, c2, c3, c4 = st.columns(4)
    total_actual = len(df_tipo)
    c1.metric("Total Inasistencias", total_actual)
    
    delta_str = "N/A"
    try:
        if len(conf_list) > 1 and selected_conf in conf_list:
            idx = conf_list.index(selected_conf)
            if idx < len(conf_list) - 1: 
                prev_conf = conf_list[idx + 1]
                df_prev = df_inas[df_inas['post_titulo'] == prev_conf]
                if selected_terr != "Todos": df_prev = df_prev[df_prev['TERRITORIAL'] == selected_terr]
                if selected_tipo != "Todos": df_prev = df_prev[df_prev['TIPO'] == selected_tipo]
                total_prev = len(df_prev)
                delta = total_actual - total_prev
                if delta > 0: delta_str = f"Empeoró (+{delta})"
                elif delta < 0: delta_str = f"Mejoró ({delta})"
                else: delta_str = "Igual (0)"
    except Exception:
        pass
    
    c2.metric("Inasistencia vs Conf. Anterior", delta_str)
    c3.metric("Conferencias Analizadas", df_inas['post_titulo'].nunique() if 'post_titulo' in df_inas.columns else 0)
    comercios_unicos = df_tipo['username'].nunique() if 'username' in df_tipo.columns else len(df_tipo)
    c4.metric("Comercio Únicos", f"{selected_tipo if selected_tipo != 'Todos' else 'Total'}: {comercios_unicos}")
    st.divider()

    # CONFIGURACIÓN DESACTIVACIÓN DE ZOOM ACCIDENTAL (OBSERVACIÓN 1°)
    plotly_config = {
        'scrollZoom': False,
        'displayModeBar': False,
        'doubleClick': 'reset'
    }

    # GRÁFICOS
    col_ch1, col_ch2 = st.columns(2)
    with col_ch1:
        st.subheader("📈 Inasistencias por Conferencia")
        df_trend = df_inas.copy()
        if selected_terr != "Todos": df_trend = df_trend[df_trend['TERRITORIAL'] == selected_terr]
        if selected_tipo != "Todos": df_trend = df_trend[df_trend['TIPO'] == selected_tipo]
        if not df_trend.empty and 'post_titulo' in df_trend.columns:
            trend_data = df_trend.groupby('post_titulo').size().reset_index(name='Inasistencias')
            trend_data['fecha_corta'] = trend_data['post_titulo'].astype(str).apply(lambda x: x.split(':')[0].strip())
            fechas = trend_data['fecha_corta'].str.extract(r'(\d{2})/(\d{2})')
            trend_data['sort_key'] = fechas[1] + "-" + fechas[0]
            trend_data = trend_data.sort_values('sort_key')
            fig1 = px.bar(trend_data, x='fecha_corta', y='Inasistencias', text='Inasistencias')
            fig1.update_traces(marker_color='#096045', textposition='auto')
            fig1.update_layout(
                paper_bgcolor='rgba(0,0,0,0)', 
                plot_bgcolor='rgba(0,0,0,0)', 
                xaxis_title="", 
                yaxis_title="Ausencias", 
                dragmode=False,
                xaxis={'categoryorder': 'array', 'categoryarray': trend_data['fecha_corta']}
            )
            st.plotly_chart(fig1, use_container_width=True, config=plotly_config)
            
    with col_ch2:
        st.subheader("📌 Ausencias por Supervisor")
        if not df_tipo.empty and 'Jerarquia_Dinamica' in df_tipo.columns:
            sup_data = df_tipo.groupby('Jerarquia_Dinamica').size().reset_index(name='Inasistencias').sort_values('Inasistencias', ascending=True)
            fig2 = px.bar(sup_data, y='Jerarquia_Dinamica', x='Inasistencias', text='Inasistencias', orientation='h', color='Inasistencias', color_continuous_scale=['#FF6700', '#3CC666'])
            fig2.update_traces(textposition='auto')
            fig2.update_layout(
                paper_bgcolor='rgba(0,0,0,0)', 
                plot_bgcolor='rgba(0,0,0,0)', 
                xaxis_title="", 
                yaxis_title="", 
                dragmode=False,
                coloraxis_showscale=False
            )
            st.plotly_chart(fig2, use_container_width=True, config=plotly_config)

    st.divider()

    # CÁLCULO DE INASISTENCIAS CONTINUAS (OBSERVACIÓN 2°)
    df_agentes = df_tipo.copy()
    
    if not df_agentes.empty and 'username' in df_agentes.columns and conf_list and selected_conf in conf_list:
        idx_sel = conf_list.index(selected_conf)
        eval_confs = conf_list[idx_sel:]  # Desde la seleccionada hacia las conferencias anteriores
        
        # Mapa de terminales ausentes por conferencia evaluada
        absent_sets = [
            set(df_inas[df_inas['post_titulo'] == c]['username'].dropna())
            for c in eval_confs
        ]
        
        def contar_inasistencias_continuas(user):
            cant = 0
            for conf_set in absent_sets:
                if user in conf_set:
                    cant += 1
                else:
                    break
            return cant

        df_agentes['Cantidad de Inasistencias continuas'] = df_agentes['username'].apply(contar_inasistencias_continuas)
    else:
        df_agentes['Cantidad de Inasistencias continuas'] = 1

    # SECCIÓN: AGENTES PENDIENTES & GESTIÓN DE SUPERVISOR
    st.subheader("📋 Agentes Pendientes & Gestión de Supervisor")
    
    col_f1, col_f2, col_f3 = st.columns(3)
    
    with col_f1:
        tipos_tabla = ["Todos"] + df_agentes['TIPO'].dropna().unique().tolist() if 'TIPO' in df_agentes.columns else ["Todos"]
        selected_tipo_tabla = st.selectbox("Filtrar por Tipo de Punto:", tipos_tabla, key="f_tipo_tabla")
        
    with col_f2:
        sups = ["Todos"] + df_agentes['Jerarquia_Dinamica'].dropna().unique().tolist() if 'Jerarquia_Dinamica' in df_agentes.columns else ["Todos"]
        selected_sup = st.selectbox("Filtrar por Supervisor:", sups, key="f_sup_tabla")

    with col_f3:
        cantidades_unicas = sorted(df_agentes['Cantidad de Inasistencias continuas'].unique()) if 'Cantidad de Inasistencias continuas' in df_agentes.columns else [1]
        opciones_continuas = ["Todas"] + [str(c) for c in cantidades_unicas]
        selected_continuas = st.selectbox("Filtrar por Inasistencias Continuas:", opciones_continuas, key="f_cont_tabla")

    # APLICAR FILTROS A LA TABLA
    df_tabla = df_agentes.copy()
    if selected_tipo_tabla != "Todos" and 'TIPO' in df_tabla.columns:
        df_tabla = df_tabla[df_tabla['TIPO'] == selected_tipo_tabla]
    if selected_sup != "Todos" and 'Jerarquia_Dinamica' in df_tabla.columns:
        df_tabla = df_tabla[df_tabla['Jerarquia_Dinamica'] == selected_sup]
    if selected_continuas != "Todas" and 'Cantidad de Inasistencias continuas' in df_tabla.columns:
        df_tabla = df_tabla[df_tabla['Cantidad de Inasistencias continuas'] == int(selected_continuas)]

    # OCULTAR COLUMNAS NO DESEADAS
    cols_a_eliminar = ['post_titulo', 'post Titulo', 'TERRITORIAL', 'Terminales pendientes', 'Terminales Pendientes']
    df_mostrar = df_tabla.drop(columns=[c for c in cols_a_eliminar if c in df_tabla.columns])

    # COACHING SUPERVISOR
    with st.expander(f"💡 Recibe un consejo experto ({selected_sup})", expanded=False):
        if st.button("🚀 Generar Diagnóstico Supervisor", type="primary", key="btn_ia_sup"):
            if not api_key:
                st.error("API Key no configurada.")
            else:
                client = genai.Client(api_key=api_key)
                prompt_sup = f"""
                Actúa como Coach de Ventas para La Tinka S.A.
                Genera una recomendación de gestión para el Supervisor '{selected_sup}' en la conferencia '{selected_conf}'.
                Tiene {len(df_mostrar)} agentes ausentes. Brinda 2 acciones directas y un mensaje corto para WhatsApp.
                """
                with st.spinner("Generando coaching..."):
                    try:
                        res_sup = client.models.generate_content(model="gemini-3.6-flash", contents=prompt_sup)
                        st.markdown(res_sup.text)
                    except Exception as e:
                        st.error(f"Error: {e}")

    st.dataframe(df_mostrar, use_container_width=True, height=300)
    
    if st.button("📋 Copiar Inasistencias para WhatsApp", key="cp_m1"):
        if not df_mostrar.empty:
            lineas = [
                f"Comercio: {r.get('username', '')} - {r.get('AGENTE', '')} | Inasistencias Continuas: {r.get('Cantidad de Inasistencias continuas', 1)} | Sup: {r.get('Jerarquia_Dinamica', '')}" 
                for _, r in df_mostrar.iterrows()
            ]
            st.code("\n".join(lineas), language=None)
