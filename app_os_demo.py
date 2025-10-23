import streamlit as st
import pandas as pd
import pdfplumber
import re
from datetime import datetime, timedelta
import io
import plotly.graph_objects as go

# === FUNCIÓN PRINCIPAL DE PROCESAMIENTO ===
def procesar_pdf_orden_servicio(archivo_pdf):
    texto_pdf = ""
    with pdfplumber.open(archivo_pdf) as pdf:
        for pagina in pdf.pages:
            contenido = pagina.extract_text()
            if contenido:
                texto_pdf += contenido + " "

    texto_pdf = re.sub(r"\s+", " ", texto_pdf)

    # === Extracción: N° de OS ===
    os_match = re.search(r"ORDEN\s+DE\s+SERVICIO\s*N[°º]?\s*(\d+)", texto_pdf, flags=re.IGNORECASE)
    numero_os = os_match.group(1) if os_match else "No identificado"

    # === Extracción: Fecha de notificación ===
    fecha_match = re.search(
        r"Fecha\s+de\s+NOTIFICACI[ÓO]N(?:\s+DE\s+LA\s+OS)?\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
        texto_pdf
    )
    fecha_os = datetime.strptime(fecha_match.group(1), "%d/%m/%Y") if fecha_match else datetime(2025, 1, 10)

    # === Extracción flexible del monto total ===
    monto_match = re.search(
        r"(?:VALOR\s*TOTAL\s*(?:DEL\s+SERVICIO)?|MONTO\s*TOTAL|TOTAL\s*S/)\s*[:\-]?\s*(?:S/)?\s*([\d,]+\.\d{2})",
        texto_pdf,
        flags=re.IGNORECASE
    )
    if not monto_match:
        monto_match = re.search(r"S/\s*([\d,]+\.\d{2})", texto_pdf)

    monto_total = float(monto_match.group(1).replace(",", "")) if monto_match else 0.0



    # === Extracción: Cantidad explícita de entregables ===
    cantidad_match = re.search(
        r"(?:N[°º]\s*DE\s*ENTREGABLES?|CANTIDAD\s+DE\s+PRODUCTOS?|N[ÚU]MERO\s+DE\s+ENTREGABLES?)\s*[:\-]?\s*(\d+)",
        texto_pdf,
        flags=re.IGNORECASE
    )
    cantidad_entregables = int(cantidad_match.group(1)) if cantidad_match else 0

    # === Detección controlada de entregables (solo primera página válida) ===
    entregables_detectados = []
    vistos = set()
    primera_pagina_detectada = False

    with pdfplumber.open(archivo_pdf) as pdf:
        for pagina in pdf.pages:
            texto_pag = pagina.extract_text()
            if not texto_pag:
                continue

            texto_pag = re.sub(r"\s+", " ", texto_pag)

            patron_pag = re.findall(
                r"(PRIMER|SEGUNDO|TERCER|CUARTO|QUINTO|SEXTO|S[ÉE]PTIMO|SEPTIMO|OCTAVO|NOVENO|D[ÉE]CIMO)"
                r"\s+ENTREGABLES?\s*[:\-]?\s*HASTA\s+(?:LOS\s+)?(\d{1,4})\s*D[ÍI]AS",
                texto_pag,
                flags=re.IGNORECASE
            )


            if patron_pag:
                for nombre, dias in patron_pag:
                    nombre_norm = nombre.upper().replace("É", "E").strip()
                    plazo = int(dias)
                    clave = (nombre_norm, plazo)
                    if clave not in vistos:
                        vistos.add(clave)
                        entregables_detectados.append(clave)

                primera_pagina_detectada = True
                break  # 🔹 Solo analizamos la primera página con entregables válidos

    # === Determinar número de entregables ===
    if len(entregables_detectados) > cantidad_entregables:
        cantidad_entregables = len(entregables_detectados)

    # === Si no se detectaron entregables, generamos automáticamente ===
    if not entregables_detectados:
        entregables_detectados = [(f"ENTREGABLE_{i+1}", (i+1)*30) for i in range(int(cantidad_entregables or 5))]

    # === Validación manual si faltan datos ===
    if monto_total == 0:
        monto_total = st.number_input("💰 Ingrese el monto total del servicio (S/):", min_value=0.0, step=100.0)
    if cantidad_entregables == 0:
        cantidad_entregables = st.number_input("📦 Ingrese el número de entregables:", min_value=1, step=1)

    # === Construcción de tabla de cronograma ===
    rows = []
    pago_unitario = round(monto_total / cantidad_entregables, 2) if cantidad_entregables > 0 else 0.0
    porcentaje_pago = round(100 / cantidad_entregables, 2) if cantidad_entregables > 0 else 0.0
    fecha_inicio_str = fecha_os.strftime("%d/%m/%Y")

    for i, (nombre, plazo) in enumerate(entregables_detectados, start=1):
        fecha_contractual = fecha_os + timedelta(days=plazo)
        rows.append([
            numero_os,
            f"{i}°_{nombre}_ENTREGABLE",
            plazo,
            f"{porcentaje_pago}%",
            pago_unitario,
            fecha_inicio_str,
            fecha_contractual.strftime("%d/%m/%Y")
        ])

    rows.append([numero_os, "Total", "", "100%", monto_total, "", ""])

    df = pd.DataFrame(rows, columns=[
        "N° OS", "Entregables", "Plazo_dias", "%_Pago", "Pago_soles",
        "Fecha_OS", "Fecha_Contractual"
    ])

    # === Exportar Excel en memoria ===
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Cronograma")
    buffer.seek(0)

    return df, buffer, numero_os, monto_total, fecha_os, cantidad_entregables, pago_unitario


# === INTERFAZ WEB ===
st.set_page_config(page_title="Procesador OS", page_icon="📘", layout="centered")
st.title("📘 Procesamiento Automático de Órdenes de Servicio")

uploaded_file = st.file_uploader("📂 Cargar archivo PDF de la Orden de Servicio", type=["pdf"])

if uploaded_file:
    with st.spinner("Procesando archivo..."):
        df, excel_buffer, numero_os, monto_total, fecha_os, cantidad_entregables, pago_unitario = procesar_pdf_orden_servicio(uploaded_file)

    st.success("✅ Procesamiento completado")

    st.subheader("📊 Resumen General")
    st.write(f"**N° OS:** {numero_os}")
    st.write(f"**Monto total:** S/ {monto_total:,.2f}")
    st.write(f"**Fecha de notificación:** {fecha_os.strftime('%d/%m/%Y')}")
    st.write(f"**Entregables detectados:** {cantidad_entregables}")
    st.write(f"**Pago por entregable:** S/ {pago_unitario:,.2f}")

    st.subheader("🧾 Cronograma Detectado")
    st.dataframe(df, use_container_width=True)

    # === Gráfico ===
    df_plot = df[df["Entregables"] != "Total"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_plot["Fecha_Contractual"],
        y=df_plot["Entregables"],
        mode="lines+markers",
        name="Fecha Contractual",
        line=dict(color="green", dash="solid")
    ))
    st.plotly_chart(fig, use_container_width=True)

    # === Botón de descarga ===
    st.download_button(
        label="⬇️ Descargar Excel",
        data=excel_buffer,
        file_name=f"Cronograma_OS{numero_os}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
