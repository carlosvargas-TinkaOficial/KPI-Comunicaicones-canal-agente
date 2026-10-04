import streamlit as st
import pandas as pd
from google import genai

def mostrar_modulo(api_key, bytes_excel):
    st.title("📊 Control de Avance Mensual NPS")

    if not bytes_excel:
        st.warning("⚠️ No se pudo cargar la base de datos de NPS desde Google Drive.")
        return

    try:
        xls = pd.ExcelFile(bytes_excel)
        df_avance = pd.read_excel(xls, sheet_name=0)
        df_comentarios = pd.read_excel(xls, sheet_name=1) if len(xls.sheet_names) > 1 else pd.DataFrame()
    except Exception:
        st.error("⚠️ Error al procesar la información de NPS.")
        return

    col_cumplimiento = '% NPS Cumplimiento Terminales'
    if col_cumplimiento in df_avance.columns:
        df_avance[col_cumplimiento] = pd.to_numeric(df_avance[col_cumplimiento], errors='coerce').fillna(0)

    # FILTROS
    col1, col2 = st.columns(2)
    with col1:
        meses = df_avance['Mes'].dropna().unique().tolist() if 'Mes' in df_avance.columns else []
        selected_mes = st.selectbox("📅 Seleccionar Mes:", meses)

    df_mes = df_avance[df_avance['Mes'] == selected_mes] if 'Mes' in df_avance.columns else df_avance

    with col2:
        terrs = ["Todos"] + df_mes['TERRITORIAL'].dropna().unique().tolist() if 'TERRITORIAL' in df_mes.columns else ["Todos"]
        selected_terr = st.selectbox("🎯 Seleccionar Líder Territorial:", terrs)

    df_terr = df_mes if selected_terr == "Todos" else df_mes[df_mes['TERRITORIAL'] == selected_terr]

    # COACHING IA NPS
    with st.expander("💡 Generar Análisis Inteligente de Feedback (NPS Global)", expanded=False):
        if st.button("🚀 Analizar Comentarios NPS", type="primary", key="btn_ia_m2"):
            if not api_key:
                st.error("API Key no configurada.")
            elif df_comentarios.empty or 'RESPUESTA' not in df_comentarios.columns:
                st.warning("Hoja de comentarios no encontrada o falta la columna 'RESPUESTA'.")
            else:
                client = genai.Client(api_key=api_key)
                comentarios = df_comentarios['RESPUESTA'].dropna().astype(str).tolist()
                prompt = f"""
                Actúa como Analista CX. Analiza estos comentarios NPS centrándote ÚNICAMENTE en fricciones/negativos:
                1. Principales Puntos de Dolor (3 viñetas).
                2. Sugerencias de Acción Inmediata (2 acciones).
                Comentarios:
                - {" ".join(comentarios)}
                """
                with st.spinner("Analizando feedback de clientes..."):
                    try:
                        res = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
                        st.markdown(res.text)
                    except Exception as e:
                        st.error(f"Error con la IA: {e}")

    regs = ["Todos"] + df_terr['REGIONAL'].dropna().unique().tolist() if 'REGIONAL' in df_terr.columns else ["Todos"]
    selected_reg = st.selectbox("👤 Filtrar por Regional:", regs)
    df_disp = df_terr if selected_reg == "Todos" else df_terr[df_terr['REGIONAL'] == selected_reg]

    # MÉTRICAS
    total_u = len(df_disp)
    comp = df_disp[df_disp[col_cumplimiento] > 0].shape[0] if col_cumplimiento in df_disp.columns else 0
    pend = total_u - comp
    pct = (comp / total_u * 100) if total_u > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Terminales", total_u)
    c2.metric("NPS Completado", comp)
    c3.metric("Terminales Pendientes", pend, delta="-Atención Requerida", delta_color="inverse")
    c4.metric("% de Avance", f"{pct:.1f}%")

    st.subheader("📋 Detalle de Terminales Pendientes")
    df_pend = df_disp[df_disp[col_cumplimiento] == 0] if col_cumplimiento in df_disp.columns else df_disp
    st.dataframe(df_pend, use_container_width=True, height=300)

    if st.button("📋 Copiar Pendientes para WhatsApp", key="cp_m2"):
        if not df_pend.empty:
            col_t = 'TERMINAL' if 'TERMINAL' in df_pend.columns else df_pend.columns[0]
            col_r = 'REGIONAL' if 'REGIONAL' in df_pend.columns else df_pend.columns[1]
            lineas = [f"Regional: {r[col_r]} | Terminal: {r[col_t]}" for _, r in df_pend.iterrows()]
            st.code("\n".join(lineas), language=None)
