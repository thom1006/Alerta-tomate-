import streamlit as st
import requests
import os
import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Configuración inicial
st.set_page_config(page_title="Alerta Temprana - Tomate", page_icon="🍅", layout="wide")
load_dotenv()

# --- CONFIGURACIÓN DEL PROYECTO ---
THINGSPEAK_CHANNEL_ID = os.getenv("THINGSPEAK_CHANNEL_ID", "3395745")
THINGSPEAK_READ_API_KEY = os.getenv("THINGSPEAK_READ_API_KEY", "1WUC7SN53PTGGZY8")

# --- FUNCIONES DE DATOS Y CÁLCULOS TÉCNICOS ---

def calcular_punto_rocio(T, HR):
    """
    Cálculo de la Temperatura de Rocío (Td) usando la aproximación de Magnus-Tetens.
    Fórmula: 
    alpha = ((17.27 * T) / (237.7 + T)) + ln(HR / 100.0)
    Td = (237.7 * alpha) / (17.27 - alpha)
    """
    if HR <= 0:
        return T
    # Aseguramos que HR no exceda 100 para el cálculo matemático puro
    HR = min(HR, 100.0) 
    
    alpha = ((17.27 * T) / (237.7 + T)) + np.log(HR / 100.0)
    Td = (237.7 * alpha) / (17.27 - alpha)
    return Td

def generar_datos_simulados(dias):
    """Genera datos históricos simulados para rellenar cuando faltan datos reales."""
    fechas = pd.date_range(end=datetime.now(), periods=dias * 24, freq='h')
    temperaturas = []
    humedades = []
    
    for fecha in fechas:
        hora = fecha.hour
        # Curva de temperatura diaria
        temp_base = 15 + 10 * ((hora - 4) / 10 if 4 <= hora <= 14 else (28 - hora) / 14 if hora > 14 else (hora + 10) / 14)
        hum_base = 95 - (temp_base - 10) * 1.5
        
        temperaturas.append(temp_base + random.uniform(-2, 2))
        humedades.append(hum_base + random.uniform(-4, 4))
        
    df = pd.DataFrame({
        'Fecha': fechas,
        'Temperatura (°C)': temperaturas,
        'Humedad (%)': humedades
    }).set_index('Fecha')
    
    # Calcular el punto de rocío en la simulación
    df['Punto de Rocío (°C)'] = df.apply(lambda row: calcular_punto_rocio(row['Temperatura (°C)'], row['Humedad (%)']), axis=1)
    return df

def get_thingspeak_history(dias):
    """Obtiene el historial de datos desde ThingSpeak para los últimos X días"""
    url = f"https://api.thingspeak.com/channels/{THINGSPEAK_CHANNEL_ID}/feeds.json?api_key={THINGSPEAK_READ_API_KEY}&days={dias}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        feeds = data.get('feeds', [])
        
        # Si hay muy pocos datos reales, usar simulados
        if len(feeds) < 5: 
            return generar_datos_simulados(dias), True

        # Procesar JSON a DataFrame
        df = pd.DataFrame(feeds)
        df['Fecha'] = pd.to_datetime(df['created_at'])
        df['Temperatura (°C)'] = pd.to_numeric(df['field2'], errors='coerce')
        df['Humedad (%)'] = pd.to_numeric(df['field1'], errors='coerce')
        
        df = df.dropna(subset=['Temperatura (°C)', 'Humedad (%)'])
        df = df[['Fecha', 'Temperatura (°C)', 'Humedad (%)']].set_index('Fecha')
        
        # Calcular temperatura de rocío
        df['Punto de Rocío (°C)'] = df.apply(lambda row: calcular_punto_rocio(row['Temperatura (°C)'], row['Humedad (%)']), axis=1)
        
        return df, False 
    except Exception as e:
        st.error(f"Error al obtener historial de ThingSpeak: {e}")
        return generar_datos_simulados(dias), True

# --- MATRIZ DE RIESGO DE PATÓGENOS ---

def evaluar_riesgo_patogenos(temp, hum, punto_rocio, df_hist, etapa):
    """
    Evalúa el riesgo de Alternaria solani y Botrytis cinerea basado en reglas biológicas
    y el historial climático de las últimas 24 horas.
    """
    riesgo_alt = "Bajo"
    riesgo_bot = "Bajo"
    
    # ---------------------------------------------------------
    # 1. EVALUACIÓN DE ALTERNARIA SOLANI (Tizón Temprano)
    # ---------------------------------------------------------
    # Activo entre 15 °C y 32 °C. Óptimo: 24 °C - 29 °C. Agua libre / HR > 85%
    if 15 <= temp <= 32:
        if 24 <= temp <= 29 and hum > 85:
            riesgo_alt = "Alto"
        elif hum > 85:
            riesgo_alt = "Medio"
            
        # Condición Especial (Efecto Alternancia):
        # Si en las últimas 24 horas hubo alta humedad (>85%) y bajó abruptamente (ej. < 60% actual),
        # las esporas se dispersan, el riesgo se dispara a ALTO.
        if not df_hist.empty and len(df_hist) >= 24:
            df_24h = df_hist.tail(24)
            max_hum_24h = df_24h['Humedad (%)'].max()
            if max_hum_24h > 85 and hum < 60:
                riesgo_alt = "Alto"

    # ---------------------------------------------------------
    # 2. EVALUACIÓN DE BOTRYTIS CINEREA (Moho Gris)
    # ---------------------------------------------------------
    # Óptimo: 15 °C - 22 °C. HR persistente > 93%. Requiere condensación (Temp ~ Td)
    if 15 <= temp <= 22:
        if hum > 93:
            # Verificamos condensación: la temperatura ambiental se acerca al punto de rocío (diferencia <= 1.5 °C)
            if (temp - punto_rocio) <= 1.5:
                riesgo_bot = "Alto"
            else:
                riesgo_bot = "Medio"
    
    # ---------------------------------------------------------
    # 3. AJUSTES POR ETAPA FENOLÓGICA (Sensibilidad)
    # ---------------------------------------------------------
    if etapa == "Fructificación y Maduración":
        # Etapa crítica para Alternaria. Si el clima daba riesgo Medio, se eleva a Alto por susceptibilidad.
        if riesgo_alt == "Medio":
            riesgo_alt = "Alto"
            
    if etapa == "Floración":
        # Etapa crítica para Botrytis. Si el clima daba riesgo Medio, se eleva a Alto.
        if riesgo_bot == "Medio":
            riesgo_bot = "Alto"

    return riesgo_alt, riesgo_bot


# --- INTERFAZ (STREAMLIT) ---

st.title("🍅 Monitor Inteligente: Alerta Temprana en Tomate")
st.markdown("Evaluación agronómica de patógenos (Alternaria solani y Botrytis cinerea) basada en termodinámica.")

# --- BARRA LATERAL: MENÚ FENOLÓGICO Y CONFIGURACIÓN ---
st.sidebar.header("⚙️ Configuración del Cultivo")

etapa_fenologica = st.sidebar.selectbox(
    "Etapa Fenológica Actual", 
    ["Desarrollo Vegetativo", "Floración", "Fructificación y Maduración"],
    help="Indica la etapa de tu cultivo para ajustar la sensibilidad del riesgo de patógenos."
)

st.sidebar.markdown("---")
rango_tiempo = st.sidebar.selectbox("Periodo de gráficas", ["Últimas 24 horas", "Última semana", "Último mes"])
dias = 1 if rango_tiempo == "Últimas 24 horas" else 7 if rango_tiempo == "Última semana" else 30

actualizar = st.sidebar.button("🔄 Actualizar Datos")

# --- CARGA DE DATOS ---
if actualizar or f'historico_{dias}' not in st.session_state:
    df_hist, es_simulado = get_thingspeak_history(dias)
    st.session_state[f'historico_{dias}'] = df_hist
    st.session_state[f'es_simulado_{dias}'] = es_simulado

df_hist = st.session_state[f'historico_{dias}']
es_simulado = st.session_state[f'es_simulado_{dias}']

# --- MENSAJES DE RIESGO POR ETAPA FENOLÓGICA ---
if etapa_fenologica == "Desarrollo Vegetativo":
    st.info("🌱 **Desarrollo Vegetativo:** Nivel de riesgo base para Alternaria en hojas basales (alto follaje incrementa riesgo). Riesgo de entrada para Botrytis si hay podas/desbrotes recientes.")
elif etapa_fenologica == "Floración":
    st.error("🌼 **Floración:** **¡ETAPA CRÍTICA para Botrytis cinerea!** (Infección por pétalos marchitos/aborto floral). Nivel de susceptibilidad alto para Alternaria.")
elif etapa_fenologica == "Fructificación y Maduración":
    st.error("🍅 **Fructificación y Maduración:** **¡ETAPA CRÍTICA para Alternaria solani!** (Máxima demanda energética, defoliación acelerada y manchas negras en frutos). Fase de reactivación latente para Botrytis (pudrición blanda por azúcares).")

if not df_hist.empty:
    # --- 1. LECTURA DE VARIABLES ACTUALES ---
    ultimo_dato = df_hist.iloc[-1]
    temp_actual = ultimo_dato['Temperatura (°C)']
    hum_actual = ultimo_dato['Humedad (%)']
    rocio_actual = ultimo_dato['Punto de Rocío (°C)']
    
    # Calcular riesgos biológicos
    riesgo_alt, riesgo_bot = evaluar_riesgo_patogenos(temp_actual, hum_actual, rocio_actual, df_hist, etapa_fenologica)
    
    st.subheader("📊 Variables Meteorológicas Actuales")
    if es_simulado:
        st.warning("⚠️ Mostrando datos simulados temporalmente (no hay suficientes datos reales de ThingSpeak).")
        
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Temperatura 🌡️", value=f"{temp_actual:.1f} °C")
    with col2:
        st.metric(label="Humedad Relativa 💧", value=f"{hum_actual:.1f} %")
    with col3:
        # Visualización de la Temperatura de Rocío
        dif_rocio = temp_actual - rocio_actual
        # Si la diferencia es menor a 2°C, hay peligro de condensación
        color_rocio = "normal" if dif_rocio > 2 else "inverse"
        st.metric(
            label="Temperatura de Rocío ❄️", 
            value=f"{rocio_actual:.1f} °C", 
            delta=f"Dif: {dif_rocio:.1f} °C", 
            delta_color=color_rocio,
            help="Si la temperatura ambiente se iguala al punto de rocío, ocurre condensación (agua libre), detonando infecciones fúngicas."
        )
    
    st.divider()
    
    # --- 2. RECOMENDACIONES PROGRAMADAS (MANEJO AGRONÓMICO) ---
    st.subheader("🛡️ Recomendaciones de Manejo Agronómico")
    
    recomendaciones_emitidas = False
    
    if riesgo_alt == "Alto":
        st.error("🔴 **Alternaria solani (Tizón Temprano) - RIESGO ALTO:**\n"
                 "- Aplicar tratamientos preventivos.\n"
                 "- Monitorear defoliación en el dosel inferior.\n"
                 "- Revisar niveles nutricionales de Nitrógeno.")
        recomendaciones_emitidas = True
        
    if riesgo_bot == "Alto" or etapa_fenologica == "Floración":
        st.error("🔴 **Botrytis cinerea (Moho Gris) - RIESGO ALTO / ETAPA CRÍTICA:**\n"
                 "- Optimizar la poda manual para favorecer la circulación de aire.\n"
                 "- Retirar pétalos senescentes.\n"
                 "- Evitar riegos que generen condensación en las flores.")
        recomendaciones_emitidas = True
        
    if not recomendaciones_emitidas:
        st.success("🟢 **Condiciones Estables:**\n"
                   "- Mantener el monitoreo preventivo de rutina.\n"
                   "- Los parámetros actuales no son críticos para Alternaria ni Botrytis.")
                   
    st.divider()
    
    # --- 3. GRÁFICOS TEMPORALES ---
    st.subheader(f"📈 Evolución del Microclima ({rango_tiempo})")
    
    # Gráficos en 3 columnas
    g1, g2, g3 = st.columns(3)
    with g1:
        st.markdown("**Temperatura (°C)**")
        st.line_chart(df_hist[['Temperatura (°C)']], color="#ff4b4b")
    with g2:
        st.markdown("**Humedad Relativa (%)**")
        st.line_chart(df_hist[['Humedad (%)']], color="#0068c9")
    with g3:
        st.markdown("**Temp. de Rocío (°C)**")
        st.line_chart(df_hist[['Punto de Rocío (°C)']], color="#8c52ff")

else:
    st.error("No se encontraron datos para mostrar.")
