import streamlit as st
import requests
import os
import pandas as pd
import google.generativeai as genai

# Configuración inicial de la página
st.set_page_config(
    page_title="Alerta Temprana Agrícola", 
    page_icon="🍅", 
    layout="wide"
)

# --- CONFIGURACIÓN DEL PROYECTO ---
CULTIVO = "Tomate"

# Credenciales de ThingSpeak Reales Integradas
THINGSPEAK_CHANNEL_ID = "3395745"
THINGSPEAK_READ_API_KEY = "1WUC7SN53PTGGZY8"

# Credencial de Gemini Real Integrada
GEMINI_API_KEY = "AQ.Ab8RN6IL-iVor1NMyP9Uu_alAnZcarFUb5rt_9bApmPxRweqQw"
genai.configure(api_key=GEMINI_API_KEY)


# --- FUNCIONES CORE ---

def get_thingspeak_data():
    """Obtiene el ÚLTIMO dato de temperatura y humedad en tiempo real"""
    url = f"https://api.thingspeak.com/channels/{THINGSPEAK_CHANNEL_ID}/feeds/last.json?api_key={THINGSPEAK_READ_API_KEY}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        temp = float(data.get('field2', 0))
        hum = float(data.get('field1', 0))
        return {"temperatura": temp, "humedad": hum}
    except Exception as e:
        st.error(f"Error al obtener datos en tiempo real: {e}")
        return None


def get_thingspeak_history():
    """Obtiene las últimas 100 lecturas acumuladas para construir las gráficas diarios"""
    url = f"https://api.thingspeak.com/channels/{THINGSPEAK_CHANNEL_ID}/feeds.json?api_key={THINGSPEAK_READ_API_KEY}&results=100"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get('feeds', [])
    except Exception as e:
        st.error(f"Error al obtener historial para gráficas: {e}")
        return []


def evaluar_riesgo(temp, hum):
    """Evalúa el riesgo basado en temperatura y humedad para Tomate"""
    if hum >= 80 and 15 <= temp <= 28:
        return "Rojo", "Riesgo Alto"
    elif hum >= 70 and 10 <= temp <= 30:
        return "Amarillo", "Monitorear"
    else:
        return "Verde", "Seguro"


def obtener_recomendacion_ia(temp, hum, nivel_riesgo):
    """Obtiene recomendaciones agrícolas usando la API de Gemini (Usa gemini-pro que es más compatible)"""
    prompt = f"""
    Actúa como un ingeniero agrónomo experto.
    El cultivo que estoy monitoreando es {CULTIVO}.
    Las lecturas actuales de mi sensor son:
    - Temperatura: {temp} °C
    - Humedad relativa: {hum} %
    El sistema de alerta temprana ha clasificado el nivel de riesgo actual como: {nivel_riesgo}.
    
    Por favor, proporciona recomendaciones de prevención de enfermedades (ej. proliferación de hongos o plagas específicas) 
    para las condiciones actuales en un lenguaje sencillo y directo para el agricultor.
    Mantenlo práctico y en un máximo de 3-4 viñetas.
    """
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ Error al consultar la IA: {e}"


# --- INTERFAZ DE USUARIO (STREAMLIT) ---

st.title(f"🌱 Panel de Alerta Temprana: Cultivo de {CULTIVO}")
st.markdown("Monitor de microclima e historial de sensores para la prevención de enfermedades.")

# Botón para refrescar datos
actualizar = st.button("🔄 Actualizar Datos del Sensor")

# Mostrar la info cuando inicia la página o al hacer clic
if actualizar or 'datos' not in st.session_state:
    st.session_state.datos = get_thingspeak_data()
    st.session_state.historial = get_thingspeak_history()

datos = st.session_state.datos
historial = st.session_state.historial

if datos:
    temp = datos["temperatura"]
    hum = datos["humedad"]
    
    color_alerta, texto_riesgo = evaluar_riesgo(temp, hum)
    
    # 1. Panel de lecturas actuales (Tarjetas numéricas)
    st.subheader("📊 Lecturas Actuales")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(label="Temperatura Actual 🌡️", value=f"{temp} °C")
    with col2:
        st.metric(label="Humedad Relativa Actual 💧", value=f"{hum} %")
    with col3:
        if color_alerta == "Verde":
            st.success(f"Estado de Riesgo: **{texto_riesgo}** 🟢")
        elif color_alerta == "Amarillo":
            st.warning(f"Estado de Riesgo: **{texto_riesgo}** 🟡")
        else:
            st.error(f"Estado de Riesgo: **{texto_riesgo}** 🔴")
    
    st.divider()
    
    # 2. Panel de Gráficas Históricas Diarias
    st.subheader("📈 Historial de las Últimas Lecturas")
    
    if historial:
        df = pd.DataFrame(historial)
        df['Temperatura (°C)'] = pd.to_numeric(df['field2'], errors='coerce')
        df['Humedad (%)'] = pd.to_numeric(df['field1'], errors='coerce')
        
        df['Fecha'] = pd.to_datetime(df['created_at'])
        df['Hora'] = df['Fecha'].dt.strftime('%H:%M')
        df = df.set_index('Hora')
        
        col_graf1, col_graf2 = st.columns(2)
        
        with col_graf1:
            st.markdown("### 🌡️ Evolución de Temperatura")
            st.line_chart(df['Temperatura (°C)'], color="#FF4B4B")
            
        with col_graf2:
            st.markdown("### 💧 Evolución de Humedad")
            st.line_chart(df['Humedad (%)'], color="#0068C9")
    else:
        st.warning("No hay suficientes datos históricos guardados en ThingSpeak para generar gráficas aún.")
        
    st.divider()
    
    # 3. Recomendaciones de la IA
    st.subheader("🤖 Recomendaciones del Ingeniero Agrónomo IA")
    with st.spinner("Generando recomendaciones en base al clima..."):
        recomendaciones = obtener_recomendacion_ia(temp, hum, texto_riesgo)
        st.info(recomendaciones)
        