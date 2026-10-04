import streamlit as st
import pandas as pd
import plotly.express as px
from google import genai

st.set_page_config(page_title="Dashboard Operativo - Inasistencias", layout="wide")

st.title("📊 Dashboard Analítico & Coaching Ejecutivo")
st.caption("Consolidado dinámico de inasistencias y generación de planes de acción con IA.")

st.sidebar.header("⚙️ Panel de Control")
api_key = st.sidebar.text_input("Gemini API Key (AQ...)", type="password")
uploaded_file = st.sidebar.file_uploader("Cargar Excel (.xlsx)", type=["xlsx"])

if uploaded_file and api_key:
    client = genai.Client(api_key=api_key)
    xls = pd.ExcelFile(uploaded_file)
    data_df = pd.read_excel(xls, sheet_name=0)
    dir_df = pd.read_excel(xls, sheet_name=1)

    territoriales = data_df['TERRITORIAL'].unique()
    selected_terr = st.sidebar.selectbox("Seleccionar Líder Territorial", territoriales)

    # Filtrado por territorio
    df_terr = data_df[data_df['TERRITORIAL'] == selected_terr]
    correo_match = dir_df[dir_df['TERRITORIAL'] == selected_terr]['CORREO'].values
    correo_leader = correo_match[0] if len(correo_match) > 0 else "Sin correo registrado"

    # KPIs
    c1, c2, c3 = st.columns(3)
    total_casos = len(df_terr)
    top_sup_counts = df_terr['Jerarquia_Dinamica'].value_counts()
    top_sup_nombre = top_sup_counts.index[0] if not top_sup_counts.empty else "N/A"
    top_sup_val = top_sup_counts.values[0] if not top_sup_counts.empty else 0

    c1.metric("Puntos Pendientes", total_casos)
    c2.metric("Supervisor Crítico", top_sup_nombre, f"{top_sup_val} ausencias")
    c3.metric("Líder Afectado", selected_terr)

    st.divider()

    col_chart, col_ai = st.columns([1, 1.2])

    with col_chart:
        st.subheader("📌 Ausencias por Supervisor")
        sup_df = top_sup_counts.reset_index()
        sup_df.columns = ['Supervisor', 'Casos']
        fig = px.bar(sup_df.head(5), x='Casos', y='Supervisor', orientation='h',
                     text='Casos', color='Casos', color_continuous_scale='Reds')
        fig.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False, height=350)
        st.plotly_chart(fig, use_container_width=True)

    with col_ai:
        st.subheader("✉️ Tarjeta de Coaching Ejecutivo")
        
        if st.button("✨ Generar Mensaje de Coaching", type="primary"):
            top_3_str = "\n".join([f"- {sup}: {cant} inasistencias" for sup, cant in top_sup_counts.head(3).items()])
            agentes_sample = ", ".join(df_terr['AGENTE'].dropna().head(5).tolist())

            prompt = f"""
            Redacta un correo profesional de coaching operativo para {selected_terr}.
            Datos:
            - Total ausencias: {total_casos}
            - Muestra de comercios: {agentes_sample}
            - Supervisores críticos:
            {top_3_str}

            Estructura:
            Asunto breve y directo.
            Saludo ejecutivo.
            Diagnóstico con datos exactos.
            2 Acciones prioritarias enfocadas en los supervisores críticos.
            Cierre colaborador.
            Maximum 150 palabras.
            """
            
            with st.spinner("Procesando con Gemini 3.6 Flash..."):
                try:
                    res = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
                    st.success(f"Destinatario: {correo_leader}")
                    st.text_area("Cuerpo del mensaje (Listo para copiar):", res.text, height=220)
                except Exception as e:
                    st.error(f"Error generando reporte: {e}")
else:
    st.info("👈 Por favor ingresa tu API Key y sube el archivo Excel en el menú lateral para iniciar.")
