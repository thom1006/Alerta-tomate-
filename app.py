import streamlit as st
import requests
import pandas as pd
import google.generativeai as genai

# --- CONFIGURACIÓN INICIAL DE LA PÁGINA ---
st.set_page_config(
    page_title="Alerta Temprana Agrícola", 
    page_icon="🍅", 
    layout="wide"
)

# --- CONFIGURACIÓN DEL PROYECTO Y CLAVES ---
CULTIVO = "Tomate"

# Tus credenciales reales de ThingSpeak
THINGSPEAK_CHANNEL_ID = "3395745"
THINGSPEAK_READ_API_KEY = "1WUC7SN53PTGGZY8"

# Tu credencial real de Gemini
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

def get_thingspeak_history(periodo):
    """Obtiene el historial dependiendo del filtro de tiempo seleccionado"""
    base_url = f"https://api.thingspeak.com/channels/{THINGSPEAK_CHANNEL_ID}/feeds.json?api_key={THINGSPEAK_READ_API_KEY}"
    
    # Ajustar la URL de ThingSpeak según lo que elija el usuario
    if periodo == "Últimas 24 horas":
        url = f"{base_url}&minutes=1440"
    elif periodo == "Últimos 7 días":
        url = f"{base_url}&days=7"
    else: # "Últimos 100 registros"
        url = f"{base_url}&results=100"
        
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
    """Obtiene recomendaciones agrícolas usando la API de Gemini"""
    prompt = f"""
    Actúa como un ingeniero agrónomo experto.
    El cultivo que estoy monitoreando es {CULTIVO}.
    Las lecturas actuales de mi sensor son:
    - Temperatura: {temp} °C
    - Humedad relativa: {hum} %
    El sistema de alerta ha clasificado el nivel de riesgo actual como: {nivel_riesgo}.
    
    Proporciona recomendaciones de prevención de enfermedades en un lenguaje sencillo para el agricultor.
    Mantenlo práctico y en un máximo de 3-4 viñetas.
    """
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ Error al consultar la IA: {e}"


# --- INTERFAZ DE USUARIO (STREAMLIT) ---

# BARRA LATERAL (MENÚ)
st.sidebar.title("⚙️ Visualización")
st.sidebar.markdown("Filtra el periodo de las gráficas:")
periodo_seleccionado = st.sidebar.selectbox(
    "Periodo de gráficas",
    ["Últimos 100 registros", "Últimas 24 horas", "Últimos 7 días"]
)

# PANEL PRINCIPAL
st.title(f"🌱 Panel de Alerta Temprana: Cultivo de {CULTIVO}")
st.markdown("Monitor de microclima e historial de sensores para la prevención de enfermedades.")

actualizar = st.button("🔄 Actualizar Datos del Sensor")

# Obtener datos (se actualizan al presionar el botón o cambiar el menú)
datos = get_thingspeak_data()
historial = get_thingspeak_history(periodo_seleccionado)

if datos:
    temp = datos["temperatura"]
    hum = datos["humedad"]
    
    color_alerta, texto_riesgo = evaluar_riesgo(temp, hum)
    
    # 1. Panel de lecturas actuales
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
    
    # 2. Panel de Gráficas Históricas
    st.subheader(f"📈 Historial ({periodo_seleccionado})")
    
    if historial:
        df = pd.DataFrame(historial)
        # Limpiar datos
        df['Temperatura (°C)'] = pd.to_numeric(df['field2'], errors='coerce')
        df['Humedad (%)'] = pd.to_numeric(df['field1'], errors='coerce')
        
        # Ajustar la fecha y hora a la zona horaria de Perú (UTC -5)
        df['Fecha_Hora'] = pd.to_datetime(df['created_at']) - pd.Timedelta(hours=5)
        
        # Dependiendo del periodo, mostramos el formato en la gráfica
        if periodo_seleccionado == "Últimas 24 horas":
            df['Eje_X'] = df['Fecha_Hora'].dt.strftime('%H:%M')
        else:
            df['Eje_X'] = df['Fecha_Hora'].dt.strftime('%d-%b %H:%M')
            
        df = df.set_index('Eje_X')
        
        col_graf1, col_graf2 = st.columns(2)
        
        with col_graf1:
            st.markdown("### 🌡️ Evolución de Temperatura")
            st.line_chart(df['Temperatura (°C)'], color="#FF4B4B")
            
        with col_graf2:
            st.markdown("### 💧 Evolución de Humedad")
            st.line_chart(df['Humedad (%)'], color="#0068C9")
    else:
        st.warning(f"No hay registros guardados en ThingSpeak para el periodo: {periodo_seleccionado}.")
        
    st.divider()
    
    # 3. Recomendaciones de la IA
    st.subheader("🤖 Recomendaciones del Ingeniero Agrónomo IA")
    with st.spinner("Generando recomendaciones en base al clima..."):
        recomendaciones = obtener_recomendacion_ia(temp, hum, texto_riesgo)
        st.info(recomendaciones)