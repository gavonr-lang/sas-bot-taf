import os
import time
import streamlit as st
from google import genai
from google.genai import types

# ==============================================================================
# 1. CONFIGURACIÓN DE PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="SAS-Bot | Asistente de Subestaciones (Gemini)",
    page_icon="⚡",
    layout="centered"
)

# ==============================================================================
# 2. BASE DE CONOCIMIENTO (15 FAQs) Y PROTOCOLO CONVERSACIONAL (SYSTEM INSTRUCTION)
# ==============================================================================
SYSTEM_INSTRUCTION = """
Eres SAS-Bot, un asistente técnico especializado en automatización de subestaciones eléctricas (SAS/SCADA), relés de protección/medición SEL y protocolos de comunicación industrial (IEC 61850, DNP 3.0, MODBUS, PTP/IRIG-B).

DEBES SEGUIR ESTRICTAMENTE ESTE PROTOCOLO CONVERSACIONAL DE 5 ESTADOS:

1. ALCANCE Y DELIMITACIÓN:
   - Responde ÚNICAMENTE consultas técnicas basadas en tu Base de Conocimiento o conceptos directamente vinculados a protocolos industriales (IEC 61850, DNP 3.0, MODBUS), sincronización horaria (PTP, IRIG-B, SNTP), equipos SEL (SEL-351A, SEL-451, SEL-735, SEL-3530 RTAC), redes OT y SCADA zenon.
   - NO ejecutes ni instruyas maniobras de apertura/cierre de interruptores de potencia en vivo.

2. DESAMBIGUACIÓN (ESTADO 2B):
   - Si el usuario escribe únicamente una sigla o término aislado sin contexto (ej. "GOOSE", "PTP", "DNP3", "SEL-735"), NO des una respuesta larga todavía. Pídele brevemente que precise qué necesita saber sobre ese término (definición, puertos/red o diagnóstico de falla).

3. ESTRUCTURA DE RESPUESTA TÉCNICA (ESTADO 3A):
   - Para toda consulta válida y clara, responde en español técnico, máximo 120 palabras, siguiendo este orden sin usar encabezados pesados:
     * Definición directa o respuesta puntual (1-2 líneas).
     * Dato operativo clave (puertos, tiempos, comandos o parámetros).
     * Recomendación práctica de verificación.
   - Al final de cada respuesta técnica válida, agrega en una línea separada: "¿Deseas consultar otro parámetro técnico o finalizar la sesión?"

4. MANEJO DE FUERA DE ALCANCE / FALLBACK SEGURO (ESTADO 3B):
   - Si la pregunta está fuera del dominio (ej. clima, cocina, programación general no vinculada a OT, cálculo de flujos de potencia o maniobras de interruptores), responde EXACTAMENTE con este mensaje:
     "Esa consulta está fuera de mi alcance operativo. Solo respondo preguntas técnicas sobre protocolos de comunicación (IEC 61850, DNP 3.0, MODBUS), sincronización horaria y equipos SEL/SCADA. ¿Deseas consultar sobre alguno de estos temas?"

5. CIERRE DE SESIÓN (ESTADO 5):
   - Si el usuario indica que desea terminar, agradece o se despide (ej. "gracias", "eso es todo", "adiós", "finalizar"), despídete cordialmente y pídele calificar la atención del 1 al 5 usando el panel lateral de validación UX.

==============================================================================
BASE DE CONOCIMIENTO OFICIAL (15 FAQs):
==============================================================================

[FAQ-01] ¿Qué es un mensaje GOOSE en IEC 61850?
Respuesta: Es un mensaje multicast de Capa 2 (Ethernet) diseñado para transmitir eventos críticos (como disparos o bloqueos) entre IEDs en menos de 4 ms. No usa IP ni TCP, operando mediante publicación/suscripción con retransmisión acelerada ante cambios de estado. Verifica siempre la suscripción por dirección MAC multicast y APPID.

[FAQ-02] ¿Cuál es la diferencia entre MMS y Sampled Values (SV)?
Respuesta: MMS opera en nivel estación (cliente/servidor sobre TCP/IP) para monitoreo SCADA, reportes y comandos. Sampled Values (SV) opera en bus de proceso (multicast Capa 2) enviando muestras digitalizadas de corriente y tensión desde Merging Units hacia los relés a tasas fijas (ej. 80 muestras/ciclo para protección).

[FAQ-03] ¿Para qué sirven los archivos ICD, CID y SCD?
Respuesta: Son archivos de configuración basados en XML (lenguaje SCL de IEC 61850): ICD describe las capacidades de un modelo de IED; SCD contiene la ingeniería completa de toda la subestación (enlaces GOOSE/MMS y topología); y CID es el archivo final instanciado que se carga en cada relé individual.

[FAQ-04] ¿Qué puerto TCP/UDP utiliza por defecto el protocolo DNP 3.0?
Respuesta: El protocolo DNP 3.0 utiliza por defecto el puerto 20000 (tanto en TCP como en UDP). Para verificar conectividad entre una RTU (como SEL-3530 RTAC) y el servidor SCADA, comprueba que el puerto 20000 esté abierto en ambos sentidos en los firewalls perimetrales.

[FAQ-05] ¿Qué son las Clases 0, 1, 2 y 3 en DNP 3.0?
Respuesta: Son agrupaciones de puntos para optimizar el sondeo (polling): Clase 0 devuelve el estado estático actual de todos los puntos (Integrity Poll); Clases 1, 2 y 3 agrupan eventos con estampado de tiempo ordenados por prioridad, siendo Clase 1 la más alta (usada para alarmas y disparos críticos).

[FAQ-06] ¿Cuál es la diferencia entre MODBUS RTU y MODBUS TCP?
Respuesta: MODBUS RTU transmite tramas binarias compactas sobre enlaces seriales (RS-485/RS-232) con verificación de error CRC-16. MODBUS TCP encapsula la trama sobre Ethernet TCP/IP usando el puerto 502, eliminando el checksum serial porque la capa TCP ya garantiza la integridad de entrega.

[FAQ-07] ¿Qué precisión ofrece PTP (IEEE 1588) frente a SNTP?
Respuesta: PTP (IEEE 1588v2) con perfil de potencia (IEEE C37.238) alcanza precisión sub-microsegundo (< 1 µs) mediante estampado por hardware en switches Transparent/Boundary Clock, indispensable para sincrofasores y Sampled Values. SNTP ofrece precisión de milisegundos (1 a 10 ms), suficiente solo para registro básico de eventos SCADA.

[FAQ-08] ¿Cómo verifico si un relé SEL perdió sincronización IRIG-B?
Respuesta: Revisa el bit de calidad de tiempo o ejecuta el comando TIM o STATUS vía consola serial/Telnet en el relé. Si el reloj muestra error de calidad o la fecha retrocede al año por defecto (ej. 1990 o 2000), inspecciona el cableado coaxial BNC, la impedancia y la salida demodulada del reloj GPS.

[FAQ-09] ¿Qué función cumple el concentrador SEL-3530 RTAC?
Respuesta: El SEL-3530 RTAC actúa como Unidad Terminal Remota (RTU) y concentrador de protocolos. Recopila datos de múltiples IEDs en campo (vía IEC 61850, DNP3 o Modbus), ejecuta lógica de automatización IEC 61131-3 y envía la telemetría consolidada hacia el centro de control SCADA.

[FAQ-10] ¿Cómo se extraen perfiles de carga (LDP) en un medidor SEL-735?
Respuesta: Se descargan mediante el software acSELerator QuickSet o por línea de comandos (Telnet/Serial) usando el comando "LDP 1" (o el número de registrador configurado) tras autenticarse en el medidor con nivel de acceso 1 (comando ACC).

[FAQ-11] ¿Qué diferencia hay entre el relé SEL-351A y el SEL-451?
Respuesta: El SEL-351A es un relé de sobrecorriente direccional y recierre enfocado en alimentadores de distribución. El SEL-451 es una plataforma de gama alta para transmisión y control de bahía que añade control de interruptor integrado, verificación de sincronismo (25), múltiples grupos de ajuste avanzados y soporte nativo IEC 61850 doble puerto.

[FAQ-12] ¿Por qué se usan VLANs y prioridad 802.1Q en tráfico GOOSE?
Respuesta: Como GOOSE es tráfico multicast de Capa 2, las VLANs (IEEE 802.1Q) aíslan su difusión para no saturar puertos de equipos no suscritos, mientras que la prioridad CoS (valores 4 a 7) garantiza que los switches industriales despachen los disparos antes que el tráfico SCADA normal.

[FAQ-13] ¿Cómo capturar tráfico IEC 61850 con Wireshark en un switch gestionable?
Respuesta: Debes configurar Port Mirroring (SPAN) en el switch industrial (ej. SEL-2730M o RUGGEDCOM), replicando el puerto del IED hacia el puerto de tu laptop. Luego filtra en Wireshark usando "goose", "sv" o "mms" para inspeccionar el incremento de stNum (cambio de estado) y sqNum.

[FAQ-14] ¿Qué significa una alarma de "Invalid" o "Bad Quality" en SCADA zenon?
Respuesta: Indica que el driver de comunicación perdió enlace con el IED o que el dispositivo reportó un bit de calidad inválido (falla de hardware o fuera de rango). Verifica primero el ping IP al equipo, el estado del driver en el Runtime de zenon y los registros en el Diagnosis Viewer.

[FAQ-15] ¿Qué pasos seguir si un IED responde a PING pero no reporta datos al SCADA?
Respuesta: Si hay respuesta ICMP (ping) pero sin datos: 1) Verifica que el puerto TCP/UDP (ej. 20000 para DNP3 o 502 para Modbus) no esté bloqueado por firewall; 2) Confirma que las direcciones lógicas Master/Outstation coincidan; 3) Revisa que no exista otra sesión maestra ocupando el socket único del relé.
"""

# ==============================================================================
# 3. INICIALIZACIÓN DE ESTADO DE SESIÓN
# ==============================================================================
MENSAJE_BIENVENIDA = (
    "Hola, soy **SAS-Bot**, tu asistente técnico en automatización de subestaciones "
    "(SAS/SCADA), relés SEL y protocolos industriales (**IEC 61850, DNP 3.0, MODBUS, PTP/IRIG-B**).\n\n"
    "Puedes consultarme sobre puertos, configuración de protocolos, sincronización horaria o diagnóstico de fallas. "
    "¿Qué consulta técnica deseas realizar hoy?"
)

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": MENSAJE_BIENVENIDA, "latency": None}
    ]

if "latencies" not in st.session_state:
    st.session_state.latencies = []

# ==============================================================================
# 4. BARRA LATERAL (CONFIGURACIÓN, CASOS DE PRUEBA Y VALIDACIÓN UX)
# ==============================================================================
with st.sidebar:
    st.header("⚡ Configuración SAS-Bot")
    
	# --- INICIO DEL PASO 1: Lectura segura de API Key (Nube / Local / Manual) ---
    api_key_default = os.getenv("GEMINI_API_KEY", "")
    try:
        if "GEMINI_API_KEY" in st.secrets:
            api_key_default = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass  # En entorno local sin secrets.toml, continúa sin error

    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        value=api_key_default,
        help="Configurada automáticamente en la nube o ingrésala manualmente."
    )
    # --- FIN DEL PASO 1 ---

    modelo_seleccionado = st.selectbox(
        "Modelo Gemini",
        options=["gemini-3.8-flash", "gemini-3.8-flash-lite"],
        index=0
    )

    if st.button("🔄 Reiniciar conversación", use_container_width=True):
        st.session_state.messages = [
            {"role": "assistant", "content": MENSAJE_BIENVENIDA, "latency": None}
        ]
        st.session_state.latencies = []
        st.rerun()

    st.divider()
    st.subheader("🧪 Casos de Prueba (Validación)")
    st.caption("Haz clic para probar los estados del protocolo conversacional:")

    ejemplos = [
        ("FAQ Técnica", "¿Qué puerto usa DNP 3.0 y cómo verifico conectividad?"),
        ("Desambiguación", "GOOSE"),
        ("Diagnóstico", "Un relé responde ping pero no comunica con SCADA zenon"),
        ("Fuera de alcance", "¿Cómo abro remotamente el interruptor 52-1?"),
        ("Cierre", "Muchas gracias, eso es todo.")
    ]

    prompt_ejemplo = None
    for etiqueta, texto_prueba in ejemplos:
        if st.button(f"{etiqueta}: {texto_prueba[:28]}...", use_container_width=True):
            prompt_ejemplo = texto_prueba

    st.divider()
    st.subheader("📊 Métricas TAF (Paso 6)")
    if st.session_state.latencies:
        lat_prom = sum(st.session_state.latencies) / len(st.session_state.latencies)
        st.metric("Latencia promedio", f"{lat_prom:.2f} s")
        st.metric("Consultas procesadas", len(st.session_state.latencies))
    else:
        st.caption("Aún no se registran consultas.")

    calificacion = st.slider("Calificación UX de la sesión (1-5)", 1, 5, 5)
    if st.button("Registrar evaluación UX", use_container_width=True):
        st.success(f"Evaluación registrada: {calificacion}/5 estrellas.")

# ==============================================================================
# 5. INTERFAZ PRINCIPAL DE CHAT
# ==============================================================================
st.title("⚡ SAS-Bot: Soporte Técnico SAS/SCADA")
st.caption("Motor: Google Gemini API | Trabajo Académico Final (TAF)")

# Mostrar historial de mensajes
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("latency") is not None:
            st.caption(f"⏱️ Tiempo de respuesta: {msg['latency']:.2f} s")

# Capturar entrada del usuario (por teclado o botón de prueba)
user_input = st.chat_input("Escribe tu consulta sobre IEC 61850, DNP 3.0, relés SEL o SCADA...")
prompt = prompt_ejemplo if prompt_ejemplo else user_input

if prompt:
    if not api_key:
        st.warning("⚠️ Por favor, ingresa tu Gemini API Key en la barra lateral para iniciar.")
        st.stop()

    # 1. Agregar y mostrar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": prompt, "latency": None})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Construir historial en el formato Content de google-genai
    # En la API de Gemini los roles válidos son "user" y "model"
    historial_gemini = []
    for m in st.session_state.messages:
        rol_gemini = "model" if m["role"] == "assistant" else "user"
        historial_gemini.append(
            types.Content(
                role=rol_gemini,
                parts=[types.Part.from_text(text=m["content"])]
            )
        )

    # 3. Llamar a la API de Gemini con reintento automático ante saturación (503)
    with st.chat_message("assistant"):
        with st.spinner("Consultando base técnica SAS con Gemini..."):
            client = genai.Client(api_key=api_key)
            respuesta_bot = None
            latencia = 0.0
            error_final = None

            # Hasta 3 intentos con espera progresiva (1s, 2s)
            for intento in range(3):
                try:
                    inicio = time.time()
                    response = client.models.generate_content(
                        model=modelo_seleccionado,
                        contents=historial_gemini,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            temperature=0.1,
                            max_output_tokens=350
                        )
                    )
                    latencia = time.time() - inicio
                    respuesta_bot = response.text
                    error_final = None
                    break
                except Exception as e:
                    error_final = e
                    if "503" in str(e) and intento < 2:
                        time.sleep(intento + 1)
                    else:
                        break

            if respuesta_bot:
                st.markdown(respuesta_bot)
                st.caption(f"⏱️ Tiempo de respuesta: {latencia:.2f} s")

                st.session_state.latencies.append(latencia)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": respuesta_bot,
                    "latency": latencia
                })
            else:
                # Eliminar el último mensaje del usuario si falló para evitar duplicados al reintentar
                st.session_state.messages.pop()
                st.error(f"Servicio temporalmente saturado. Intenta nuevamente o cambia a 'gemini-3.8-flash-lite'. Detalle: {error_final}")