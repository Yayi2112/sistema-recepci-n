import streamlit as st
import json
import os
import io
from PIL import Image
from streamlit_drawable_canvas import st_canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Gestión de Materiales Teknica",
    page_icon="📦",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- RUTAS Y ARCHIVOS LOCALES ---
DB_FILE = "solicitudes_db.json"
DIR_FOTOS = "uploads_fotos"
DIR_FIRMAS = "uploads_firmas"

for directorio in [DIR_FOTOS, DIR_FIRMAS]:
    if not os.path.exists(directorio):
        os.makedirs(directorio)

# --- CONFIGURACIÓN DE CORREO (MICROSOFT 365) ---
SMTP_SERVER = "smtp.office365.com"
SMTP_PORT = 587
EMAIL_REMITENTE = "esteban.filun@teknica.cl"

EMAILS_DESTINATARIOS = [
    "Dayan.moena@teknica.cl",
    "esteban.filun@teknica.cl",
    "alexandra.miranda@teknica.cl",
    "nicolas.ponce@teknica.cl"
]

def enviar_notificacion_completado(num_solicitud):
    # Lee la contraseña de forma segura desde st.secrets de Streamlit Cloud
    password = st.secrets.get("EMAIL_PASSWORD", "")

    if not password:
        st.warning("⚠️ No se ha configurado la contraseña de correo en los Secrets de Streamlit.")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_REMITENTE
        msg['To'] = ", ".join(EMAILS_DESTINATARIOS)
        msg['Subject'] = f"CHEQUEO DE SOLICITUD COMPLETADO - N° {num_solicitud}"

        cuerpo = f"""
        Hola,

        Se ha completado al 100% la verificación de materiales para la Solicitud N° {num_solicitud}.

        Las revisiones, observaciones y firmas correspondientes han sido registradas exitosamente en el sistema.

        Saludos cordiales,
        Sistema de Gestión de Materiales Teknica
        """
        msg.attach(MIMEText(cuerpo, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_REMITENTE, password)
        server.sendmail(EMAIL_REMITENTE, EMAILS_DESTINATARIOS, msg.as_string())
        server.quit()

        st.toast("📧 Notificación enviada exitosamente a los destinatarios.", icon="✅")
    except Exception as e:
        st.error(f"No se pudo enviar el correo de notificación: {e}")

# --- BASE DE DATOS LOCAL ---
def cargar_datos():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "1001": {
            "cliente": "Proyecto Central",
            "items": [
                {"descripcion": "Gabinete Eléctrico Industrial", "verificado": False, "observacion": "", "foto": None},
                {"descripcion": "Interruptor Termomagnético 32A", "verificado": False, "observacion": "", "foto": None},
                {"descripcion": "Cable Cobre Unipolar 6mm (100m)", "verificado": False, "observacion": "", "foto": None}
            ],
            "firma_revisor": None,
            "firma_bodega": None,
            "notificado": False
        }
    }

def guardar_datos(datos):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=4)

# --- GENERADOR DE PDF ---
def generar_pdf(solicitud_id, datos_solicitud):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, leading=20, textColor=colors.HexColor("#003366"), alignment=1)
    story.append(Paragraph(f"REPORTE DE VERIFICACIÓN - SOLICITUD N° {solicitud_id}", title_style))
    story.append(Spacer(1, 10))

    info_texto = f"<b>Cliente/Proyecto:</b> {datos_solicitud.get('cliente', 'N/A')}"
    story.append(Paragraph(info_texto, styles['Normal']))
    story.append(Spacer(1, 15))

    # Tabla de Items
    tabla_data = [["Estado", "Descripción del Material", "Observaciones"]]
    for item in datos_solicitud["items"]:
        estado = "OK" if item["verificado"] else "PENDIENTE"
        tabla_data.append([estado, item["descripcion"], item.get("observacion", "")])

    t = Table(tabla_data, colWidths=[80, 270, 200])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#003366")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
    ]))
    story.append(t)
    story.append(Spacer(1, 20))

    # Firmas
    firmas_data = []
    f_rev = datos_solicitud.get("firma_revisor")
    f_bod = datos_solicitud.get("firma_bodega")

    img_rev = RLImage(f_rev, width=150, height=60) if f_rev and os.path.exists(f_rev) else Paragraph("Sin firma", styles['Normal'])
    img_bod = RLImage(f_bod, width=150, height=60) if f_bod and os.path.exists(f_bod) else Paragraph("Sin firma", styles['Normal'])

    firmas_table = Table([[img_rev, img_bod], ["Firma Revisor", "Firma Bodega"]], colWidths=[270, 270])
    firmas_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    story.append(firmas_table)

    doc.build(story)
    buffer.seek(0)
    return buffer

# --- INTERFAZ PRINCIPAL ---
st.title("📦 Control de Materiales Teknica")

datos = cargar_datos()
solicitud_id = st.selectbox("Seleccione Solicitud:", list(datos.keys()))
solicitud = datos[solicitud_id]

st.markdown(f"**Cliente / Proyecto:** {solicitud.get('cliente', 'N/A')}")

# Cálculo del progreso
total_items = len(solicitud["items"])
completados = sum(1 for item in solicitud["items"] if item["verificado"])
porcentaje = int((completados / total_items) * 100) if total_items > 0 else 0

st.progress(porcentaje / 100)
st.caption(f"Avance de verificación: {porcentaje}% ({completados}/{total_items} ítems)")

st.subheader("Verificación de Ítems")
for idx, item in enumerate(solicitud["items"]):
    with st.expander(f"{'✅' if item['verificado'] else '❌'} {item['descripcion']}"):
        check = st.checkbox("Marcado como verificado", value=item["verificado"], key=f"chk_{solicitud_id}_{idx}")
        obs = st.text_input("Observaciones:", value=item.get("observacion", ""), key=f"obs_{solicitud_id}_{idx}")
        
        foto_cap = st.camera_input("Capturar Evidencia Foto", key=f"cam_{solicitud_id}_{idx}")
        if foto_cap:
            ruta_foto = os.path.join(DIR_FOTOS, f"foto_{solicitud_id}_{idx}.png")
            img = Image.open(foto_cap)
            img.save(ruta_foto)
            item["foto"] = ruta_foto

        item["verificado"] = check
        item["observacion"] = obs

# Disparar correo si llega al 100%
if porcentaje == 100 and not solicitud.get("notificado", False):
    enviar_notificacion_completado(solicitud_id)
    solicitud["notificado"] = True
    guardar_datos(datos)

st.divider()
st.subheader("Módulo de Firmas Digitales")

col1, col2 = st.columns(2)

with col1:
    st.write("**Firma Revisor**")
    canvas_rev = st_canvas(stroke_width=2, stroke_color="#000000", background_color="#EEEEEE", height=120, width=220, key=f"rev_{solicitud_id}")
    if st.button("Guardar Firma Revisor", key=f"btn_rev_{solicitud_id}"):
        if canvas_rev.image_data is not None:
            ruta_f = os.path.join(DIR_FIRMAS, f"firma_rev_{solicitud_id}.png")
            Image.fromarray(canvas_rev.image_data.astype('uint8')).save(ruta_f)
            solicitud["firma_revisor"] = ruta_f
            guardar_datos(datos)
            st.success("Firma de Revisor guardada.")

with col2:
    st.write("**Firma Bodega**")
    canvas_bod = st_canvas(stroke_width=2, stroke_color="#000000", background_color="#EEEEEE", height=120, width=220, key=f"bod_{solicitud_id}")
    if st.button("Guardar Firma Bodega", key=f"btn_bod_{solicitud_id}"):
        if canvas_bod.image_data is not None:
            ruta_f = os.path.join(DIR_FIRMAS, f"firma_bod_{solicitud_id}.png")
            Image.fromarray(canvas_bod.image_data.astype('uint8')).save(ruta_f)
            solicitud["firma_bodega"] = ruta_f
            guardar_datos(datos)
            st.success("Firma de Bodega guardada.")

guardar_datos(datos)

st.divider()
# Generar y descargar PDF
pdf_bytes = generar_pdf(solicitud_id, solicitud)
st.download_button(
    label="📄 Descargar Reporte PDF Firmado",
    data=pdf_bytes,
    file_name=f"Reporte_Solicitud_{solicitud_id}.pdf",
    mime="application/pdf"
)
