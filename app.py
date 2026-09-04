import streamlit as st
import pandas as pd
import io
import json
import os
import smtplib
import uuid
from datetime import datetime
from pathlib import Path
from PIL import Image
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Canvas para Firmas Táctiles / Digitales
from streamlit_drawable_canvas import st_canvas

# Librerías para generación de PDF
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# 1. CONFIGURACIÓN DE PÁGINA
st.set_page_config(
    page_title="Control de Solicitudes y Materiales", 
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Directorios de persistencia
DB_FILE = "solicitudes_db.json"
UPLOADS_DIR = Path("uploads_fotos")
UPLOADS_DIR.mkdir(exist_ok=True)
FIRMAS_DIR = Path("uploads_firmas")
FIRMAS_DIR.mkdir(exist_ok=True)

# Configuración de Servidor de Correo
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_REMITENTE = "tu_correo@gmail.com"
EMAIL_PASSWORD = "xxxx xxxx xxxx xxxx"
EMAIL_DESTINATARIO = "OtecPlantaSSMM@grpleg.onmicrosoft.com"

# 2. FUNCIONES DE APOYO Y GENERACIÓN DE PDF
def generar_pdf_solicitud(sol, usuario_logueado):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter, 
        rightMargin=30, 
        leftMargin=30, 
        topMargin=30, 
        bottomMargin=30
    )
    story = []
    styles = getSampleStyleSheet()

    # Estilos personalizados
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#1E3A8A'),
        spaceAfter=10
    )
    
    label_style = ParagraphStyle(
        'DocLabel',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#374151')
    )

    cell_header_style = ParagraphStyle(
        'HeaderCell',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        textColor=colors.white,
        fontName="Helvetica-Bold"
    )

    cell_body_style = ParagraphStyle(
        'BodyCell',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#111827')
    )

    # Encabezado
    story.append(Paragraph(f"<b>REPORTE DE RECEPCIÓN DE MATERIALES Y CONFORMIDAD</b>", title_style))
    story.append(Paragraph(f"<b>N° Solicitud:</b> {sol['n_solicitud']} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Estado:</b> 100% COMPLETADO", label_style))
    story.append(Paragraph(f"<b>Fecha de Generación:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", label_style))
    story.append(Spacer(1, 10))

    # Tabla de Materiales
    df = sol["data"]
    data_table = []
    
    headers = ["Item", "Descripción", "Unidad", "Cant.", "OC", "Estado"]
    data_table.append([Paragraph(h, cell_header_style) for h in headers])

    for i, row in df.iterrows():
        item_val = str(row.get('Item', i + 1))
        desc_val = str(row.get('Descripción', ''))
        uni_val = str(row.get('Unidad', ''))
        cant_val = str(row.get('Cantidad OC', row.get('Cantidad a retirar', '')))
        oc_val = str(row.get('OC', ''))
        rev_val = "✔ Recibido" if row.get('Revisado', False) else "❌ Pendiente"

        data_table.append([
            Paragraph(item_val, cell_body_style),
            Paragraph(desc_val, cell_body_style),
            Paragraph(uni_val, cell_body_style),
            Paragraph(cant_val, cell_body_style),
            Paragraph(oc_val, cell_body_style),
            Paragraph(f"<b>{rev_val}</b>", cell_body_style)
        ])

    t = Table(data_table, colWidths=[35, 230, 45, 45, 65, 75])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D1D5DB')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')])
    ]))
    story.append(t)
    story.append(Spacer(1, 12))

    # Sección Observaciones
    obs_texto = sol.get("observaciones", "").strip()
    if not obs_texto:
        obs_texto = "Sin observaciones registradas."
    
    story.append(Paragraph("<b>OBSERVACIONES DE RECEPCIÓN:</b>", ParagraphStyle('SubObs', parent=styles['Heading2'], fontSize=10, textColor=colors.HexColor('#1E3A8A'))))
    story.append(Spacer(1, 3))
    
    t_obs = Table([[Paragraph(obs_texto, cell_body_style)]], colWidths=[490])
    t_obs.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F9FAFB')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_obs)
    story.append(Spacer(1, 12))

    # Bloque de Firmas
    firmas_info = sol.get("firmas", {})
    nom_rev = firmas_info.get("nombre_revisor", "N/A")
    fec_rev = firmas_info.get("fecha_revisor", "N/A")
    img_rev_p = firmas_info.get("path_firma_revisor", "")

    nom_bod = firmas_info.get("nombre_bodega", "N/A")
    fec_bod = firmas_info.get("fecha_bodega", "N/A")
    img_bod_p = firmas_info.get("path_firma_bodega", "")

    story.append(Paragraph("<b>CONFORMIDAD Y FIRMAS DE CORRESPONSABILIDAD</b>", ParagraphStyle('Sub', parent=styles['Heading2'], fontSize=10, textColor=colors.HexColor('#1E3A8A'))))
    story.append(Spacer(1, 5))

    cell_rev_img = RLImage(img_rev_p, width=130, height=45) if (img_rev_p and os.path.exists(img_rev_p)) else Paragraph("<i>Sin firma</i>", cell_body_style)
    cell_bod_img = RLImage(img_bod_p, width=130, height=45) if (img_bod_p and os.path.exists(img_bod_p)) else Paragraph("<i>Sin firma</i>", cell_body_style)

    firmas_data = [
        [
            Paragraph("<b>REVISOR / OPERADOR</b>", label_style),
            Paragraph("<b>ENCARGADO DE BODEGA</b>", label_style)
        ],
        [
            Paragraph(f"<b>Nombre:</b> {nom_rev}<br/><b>Fecha:</b> {fec_rev}", cell_body_style),
            Paragraph(f"<b>Nombre:</b> {nom_bod}<br/><b>Fecha:</b> {fec_bod}", cell_body_style)
        ],
        [cell_rev_img, cell_bod_img],
        [
            Paragraph("________________________<br/>Firma Revisor", cell_body_style),
            Paragraph("________________________<br/>Firma Bodega", cell_body_style)
        ]
    ]

    t_firmas = Table(firmas_data, colWidths=[245, 245])
    t_firmas.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F3F4F6')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E5E7EB')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_firmas)
    story.append(Spacer(1, 12))

    # Galería de Fotos / Evidencias
    story.append(Paragraph("<b>EVIDENCIAS FOTOGRÁFICAS REGISTRADAS</b>", ParagraphStyle('Sub2', parent=styles['Heading2'], fontSize=10, textColor=colors.HexColor('#1E3A8A'))))
    story.append(Spacer(1, 6))

    fotos_dict = sol.get("fotos", {})
    hay_fotos = False

    for item_idx, foto_paths in fotos_dict.items():
        if foto_paths:
            hay_fotos = True
            idx_int = int(item_idx)
            desc_item = df.iloc[idx_int].get('Descripción', f"Item {idx_int + 1}") if idx_int < len(df) else f"Item {idx_int + 1}"
            story.append(Paragraph(f"<b>• {desc_item}:</b>", label_style))
            story.append(Spacer(1, 3))

            img_cells = []
            for path_img in foto_paths:
                if os.path.exists(path_img):
                    try:
                        img_cells.append(RLImage(path_img, width=110, height=80))
                    except Exception:
                        pass
            
            if img_cells:
                chunks = [img_cells[i:i + 3] for i in range(0, len(img_cells), 3)]
                for chunk in chunks:
                    t_img = Table([chunk], colWidths=[120] * len(chunk))
                    t_img.setStyle(TableStyle([
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ]))
                    story.append(t_img)
                    story.append(Spacer(1, 4))

    if not hay_fotos:
        story.append(Paragraph("<i>No se registraron evidencias fotográficas para esta solicitud.</i>", label_style))

    doc.build(story)
    buffer.seek(0)
    return buffer

def enviar_correo_notificacion(n_solicitud):
    if "xxxx" in EMAIL_PASSWORD or "@gmail.com" not in EMAIL_REMITENTE:
        return False, "Credenciales SMTP pendientes de configurar."

    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_REMITENTE
        msg['To'] = EMAIL_DESTINATARIO
        msg['Subject'] = f"CHEQUEO DE SOLICITUDES - N° {n_solicitud}"

        cuerpo = f"""
        Estimados,

        Se informa que el chequeo de la Solicitud N° {n_solicitud} ha sido completado al 100%.

        ---
        Sistema Automático de Control de Materiales
        """
        msg.attach(MIMEText(cuerpo, 'plain', 'utf-8'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(EMAIL_REMITENTE, EMAIL_PASSWORD)
            server.send_message(msg)
        return True, "Correo enviado correctamente."
    except Exception as e:
        return False, str(e)

def cargar_base_datos():
    if not os.path.exists(DB_FILE):
        return []
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data:
                item["data"] = pd.DataFrame(item["data"])
                item["notificado"] = item.get("notificado", False)
                item["fotos"] = item.get("fotos", {})
                item["firmas"] = item.get("firmas", {})
                item["observaciones"] = item.get("observaciones", "")
            return data
    except Exception as e:
        st.error(f"Error cargando base de datos: {e}")
        return []

def guardar_base_datos(solicitudes):
    data_to_save = []
    for item in solicitudes:
        data_to_save.append({
            "n_solicitud": item["n_solicitud"],
            "data": item["data"].to_dict(orient="records"),
            "notificado": item.get("notificado", False),
            "fotos": item.get("fotos", {}),
            "firmas": item.get("firmas", {}),
            "observaciones": item.get("observaciones", "")
        })
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)

def guardar_foto_comprimida(uploaded_file, n_solicitud, item_idx):
    filename = f"sol_{n_solicitud}_item_{item_idx}_{uuid.uuid4().hex[:8]}.jpg"
    filepath = UPLOADS_DIR / filename
    try:
        img = Image.open(uploaded_file)
        img = img.convert("RGB")
        img.save(filepath, "JPEG", quality=75, optimize=True)
        return str(filepath)
    except Exception as e:
        st.error(f"Error al guardar foto: {e}")
        return None

def guardar_firma_canvas(canvas_result, n_solicitud, rol_firma):
    if canvas_result.image_data is not None:
        img_array = canvas_result.image_data
        img = Image.fromarray(img_array.astype('uint8'), 'RGBA')
        
        filename = f"firma_{n_solicitud}_{rol_firma}_{uuid.uuid4().hex[:6]}.png"
        filepath = FIRMAS_DIR / filename
        
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        bg.save(filepath, "PNG")
        return str(filepath)
    return None

# Inicialización del Session State
if "lista_solicitudes" not in st.session_state:
    st.session_state.lista_solicitudes = cargar_base_datos()

if "expander_states" not in st.session_state:
    st.session_state.expander_states = {}

USUARIOS = {
    "admin": {"password": "admin123", "role": "Administrador"},
    "revisor": {"password": "user123", "role": "Operador"}
}

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.username = None

# 3. CONTROL DE AUTENTICACIÓN
def login():
    st.sidebar.title("🔐 Acceso al Sistema")
    username = st.sidebar.text_input("Usuario")
    password = st.sidebar.text_input("Contraseña", type="password")
    
    if st.sidebar.button("Iniciar Sesión", use_container_width=True):
        if username in USUARIOS and USUARIOS[username]["password"] == password:
            st.session_state.logged_in = True
            st.session_state.role = USUARIOS[username]["role"]
            st.session_state.username = username
            st.rerun()
        else:
            st.sidebar.error("Usuario o contraseña incorrectos")

def logout():
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.username = None
    st.session_state.expander_states = {}
    st.rerun()

if not st.session_state.logged_in:
    st.title("📋 Sistema de Control y Revisión de Materiales")
    st.info("👋 Por favor, ingresa tus credenciales en el menú lateral para continuar.")
    login()
    st.stop()

# Menú Lateral
st.sidebar.markdown(f"👤 **Usuario:** {st.session_state.username}")
st.sidebar.markdown(f"🔑 **Rol:** {st.session_state.role}")
if st.sidebar.button("Cerrar Sesión", use_container_width=True):
    logout()

st.title("📋 Gestión y Revisión de Materiales")

# 4. PANEL ADMINISTRADOR
if st.session_state.role == "Administrador":
    with st.expander("➕ Cargar / Agregar Nueva Solicitud", expanded=False):
        col_sol, col_file = st.columns([1, 2])
        with col_sol:
            nuevo_n_solicitud = st.text_input("N° Solicitud:", placeholder="Ej: 4500123")
        with col_file:
            uploaded_file = st.file_uploader("Selecciona el archivo Excel", type=["xlsx", "xls"], key="uploader_multi")

        if st.button("📌 Agregar Solicitud a la Lista", use_container_width=True):
            if not nuevo_n_solicitud.strip():
                st.error("Por favor ingresa un N° de Solicitud.")
            elif uploaded_file is None:
                st.error("Por favor adjunta un archivo Excel.")
            else:
                try:
                    file_bytes = uploaded_file.read()
                    xls = pd.ExcelFile(io.BytesIO(file_bytes))
                    
                    df_final = None
                    for sheet_name in xls.sheet_names:
                        df_raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=None)
                        header_idx = None
                        for idx, row in df_raw.iterrows():
                            row_vals = [str(v).lower() for v in row.values if pd.notna(v)]
                            if any("item" in x or "descr" in x or "unidad" in x or "oc" in x for x in row_vals):
                                header_idx = idx
                                break
                        
                        if header_idx is not None:
                            df_temp = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=header_idx)
                            df_temp = df_temp.dropna(how='all').dropna(how='all', axis=1)
                            df_temp.columns = [str(col).strip() for col in df_temp.columns]
                            df_temp = df_temp.loc[:, ~df_temp.columns.str.contains('^Unnamed')]
                            
                            if not df_temp.empty and len(df_temp.columns) > 1:
                                df_final = df_temp
                                break

                    if df_final is not None:
                        if "Revisado" not in df_final.columns:
                            df_final["Revisado"] = False
                        else:
                            df_final["Revisado"] = df_final["Revisado"].fillna(False).astype(bool)

                        st.session_state.lista_solicitudes.append({
                            "n_solicitud": nuevo_n_solicitud,
                            "data": df_final,
                            "notificado": False,
                            "fotos": {},
                            "firmas": {},
                            "observaciones": ""
                        })
                        guardar_base_datos(st.session_state.lista_solicitudes)
                        st.success(f"¡Solicitud '{nuevo_n_solicitud}' agregada exitosamente!")
                        st.rerun()
                    else:
                        st.error("No se encontraron datos válidos en el archivo Excel.")
                except Exception as e:
                    st.error(f"Error al procesar el archivo: {e}")

    if st.session_state.lista_solicitudes:
        if st.button("🗑️ Borrar TODAS las solicitudes cargadas", type="secondary"):
            st.session_state.lista_solicitudes = []
            st.session_state.expander_states = {}
            guardar_base_datos([])
            st.rerun()

# 5. VISTA Y DESPLIEGUE DE SOLICITUDES
if st.session_state.lista_solicitudes:
    st.divider()

    total_items_global = 0
    total_revisados_global = 0
    indice_a_eliminar = None

    for idx, sol in enumerate(st.session_state.lista_solicitudes):
        df_current = sol["data"]
        tot_items = len(df_current)
        rev_items = int(df_current["Revisado"].sum()) if "Revisado" in df_current.columns else 0
        porcentaje = (rev_items / tot_items) if tot_items > 0 else 0.0
        
        es_completo = (tot_items > 0 and rev_items == tot_items)
        sol_id = sol["n_solicitud"]

        if sol_id not in st.session_state.expander_states:
            st.session_state.expander_states[sol_id] = True

        if es_completo:
            st.session_state.expander_states[sol_id] = False

        if es_completo and not sol.get("notificado", False):
            exito_mail, msg_mail = enviar_correo_notificacion(sol_id)
            st.session_state.lista_solicitudes[idx]["notificado"] = True
            guardar_base_datos(st.session_state.lista_solicitudes)
            
            if exito_mail:
                st.toast(f"📧 Correo enviado a {EMAIL_DESTINATARIO}", icon="✅")
            else:
                st.toast(f"⚠️ Solicitud completada ({msg_mail})", icon="ℹ️")

        estrellas = " ✅ (COMPLETADO)" if es_completo else ""
        titulo_expander = f"📂 Solicitud N° {sol_id}  —  Avance: {rev_items}/{tot_items} ({porcentaje*100:.0f}%){estrellas}"
        
        is_open = st.session_state.expander_states.get(sol_id, True)

        with st.expander(titulo_expander, expanded=is_open):
            st.progress(porcentaje)
            
            if es_completo:
                st.success(f"🎉 **¡Solicitud N° {sol_id} verificada al 100%!** Registra las observaciones y firmas para descargar el reporte.")
                
                # SECCIÓN DE OBSERVACIONES Y FIRMAS
                st.markdown("### ✍️ Validación, Observaciones y Firmas")
                
                # Campo de Observaciones Generales
                obs_ingresada = st.text_area(
                    "📝 Observaciones o Comentarios Adicionales del Revisor:",
                    value=sol.get("observaciones", ""),
                    placeholder="Ejemplo: Se reciben empaques en buen estado. Falta guía de despachos original...",
                    key=f"obs_input_{sol_id}"
                )

                col_f1, col_f2 = st.columns(2)
                firmas_sol = sol.get("firmas", {})

                with col_f1:
                    st.subheader("👨‍🔧 Firma Revisor")
                    nom_rev = st.text_input("Nombre Revisor:", value=firmas_sol.get("nombre_revisor", st.session_state.username), key=f"nom_rev_{sol_id}")
                    fec_rev = st.date_input("Fecha Revisor:", value=datetime.now(), key=f"fec_rev_{sol_id}").strftime("%d/%m/%Y")
                    
                    st.write("Dibuje su firma abajo:")
                    canvas_rev = st_canvas(
                        fill_color="rgba(255, 255, 255, 0)",
                        stroke_width=2,
                        stroke_color="#000000",
                        background_color="#F9FAFB",
                        height=120,
                        width=300,
                        drawing_mode="freedraw",
                        key=f"canvas_rev_{sol_id}"
                    )

                with col_f2:
                    st.subheader("📦 Firma Encargado de Bodega")
                    nom_bod = st.text_input("Nombre Encargado Bodega:", value=firmas_sol.get("nombre_bodega", ""), key=f"nom_bod_{sol_id}")
                    fec_bod = st.date_input("Fecha Bodega:", value=datetime.now(), key=f"fec_bod_{sol_id}").strftime("%d/%m/%Y")
                    
                    st.write("Dibuje su firma abajo:")
                    canvas_bod = st_canvas(
                        fill_color="rgba(255, 255, 255, 0)",
                        stroke_width=2,
                        stroke_color="#000000",
                        background_color="#F9FAFB",
                        height=120,
                        width=300,
                        drawing_mode="freedraw",
                        key=f"canvas_bod_{sol_id}"
                    )

                if st.button("💾 Guardar Datos y Firmas", key=f"btn_save_firmas_{sol_id}", use_container_width=True):
                    path_f_rev = guardar_firma_canvas(canvas_rev, sol_id, "revisor")
                    path_f_bod = guardar_firma_canvas(canvas_bod, sol_id, "bodega")
                    
                    st.session_state.lista_solicitudes[idx]["observaciones"] = obs_ingresada
                    st.session_state.lista_solicitudes[idx]["firmas"] = {
                        "nombre_revisor": nom_rev,
                        "fecha_revisor": fec_rev,
                        "path_firma_revisor": path_f_rev if path_f_rev else firmas_sol.get("path_firma_revisor", ""),
                        "nombre_bodega": nom_bod,
                        "fecha_bodega": fec_bod,
                        "path_firma_bodega": path_f_bod if path_f_bod else firmas_sol.get("path_firma_bodega", "")
                    }
                    guardar_base_datos(st.session_state.lista_solicitudes)
                    st.success("✅ Observaciones y firmas guardadas correctamente.")
                    st.rerun()

                # BOTÓN PARA DESCARGAR REPORTE EN PDF CON FIRMAS
                if firmas_sol.get("nombre_revisor") and firmas_sol.get("nombre_bodega"):
                    pdf_buffer = generar_pdf_solicitud(sol, st.session_state.username)
                    st.download_button(
                        label=f"📄 Descargar Reporte PDF Firmado (Solicitud N° {sol_id})",
                        data=pdf_buffer,
                        file_name=f"Reporte_Firmado_Solicitud_{sol_id}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key=f"pdf_btn_{sol_id}"
                    )
                else:
                    st.info("ℹ️ Ingresa los nombres y presiona 'Guardar Datos y Firmas' para habilitar la descarga del PDF.")

                st.divider()

            tab_check, tab_fotos = st.tabs(["📝 Lista de Verificación", "📷 Registro Fotográfico"])
            
            with tab_check:
                if st.session_state.role == "Administrador":
                    col_info, col_del = st.columns([5, 1])
                    with col_del:
                        if st.button("🗑️ Eliminar Solicitud", key=f"del_{idx}"):
                            indice_a_eliminar = idx

                disabled_cols = [] if st.session_state.role == "Administrador" else [c for c in df_current.columns if c != "Revisado"]

                edited_df = st.data_editor(
                    df_current,
                    column_config={
                        "Revisado": st.column_config.CheckboxColumn(
                            "✔️ Check",
                            help="Marcar para confirmar la revisión del ítem",
                            default=False,
                        )
                    },
                    disabled=disabled_cols,
                    hide_index=True,
                    use_container_width=True,
                    key=f"editor_{sol_id}"
                )
                
                if not edited_df.equals(df_current):
                    st.session_state.lista_solicitudes[idx]["data"] = edited_df
                    tot_rev = int(edited_df["Revisado"].sum())
                    
                    if tot_rev < len(edited_df):
                        st.session_state.expander_states[sol_id] = True
                        st.session_state.lista_solicitudes[idx]["notificado"] = False
                    else:
                        st.session_state.expander_states[sol_id] = False
                    
                    guardar_base_datos(st.session_state.lista_solicitudes)
                    st.rerun()

            with tab_fotos:
                opciones_items = [
                    f"Fila {i+1} - {row.get('Descripción', row.get('Item', f'Ítem {i+1}'))}" 
                    for i, row in edited_df.iterrows()
                ]
                
                if opciones_items:
                    item_seleccionado = st.selectbox(
                        "Selecciona el ítem para asociar evidencias:",
                        options=range(len(opciones_items)),
                        format_func=lambda x: opciones_items[x],
                        key=f"select_item_{sol_id}"
                    )
                    
                    col_cam, col_up = st.columns(2)
                    with col_cam:
                        camera_photo = st.camera_input("Tomar foto con la cámara", key=f"cam_{sol_id}_{item_seleccionado}")
                    with col_up:
                        uploaded_photos = st.file_uploader(
                            "O subir desde la galería / archivos",
                            type=["png", "jpg", "jpeg"],
                            accept_multiple_files=True,
                            key=f"uploader_photos_{sol_id}_{item_seleccionado}"
                        )

                    item_key = str(item_seleccionado)
                    if "fotos" not in sol:
                        sol["fotos"] = {}
                    if item_key not in sol["fotos"]:
                        sol["fotos"][item_key] = []

                    se_agrego_foto = False

                    if camera_photo:
                        path_img = guardar_foto_comprimida(camera_photo, sol_id, item_seleccionado)
                        if path_img and path_img not in sol["fotos"][item_key]:
                            sol["fotos"][item_key].append(path_img)
                            se_agrego_foto = True

                    if uploaded_photos:
                        for photo in uploaded_photos:
                            path_img = guardar_foto_comprimida(photo, sol_id, item_seleccionado)
                            if path_img and path_img not in sol["fotos"][item_key]:
                                sol["fotos"][item_key].append(path_img)
                                se_agrego_foto = True

                    if se_agrego_foto:
                        guardar_base_datos(st.session_state.lista_solicitudes)
                        st.success("📷 Foto guardada exitosamente.")
                        st.rerun()

                    fotos_guardadas = sol.get("fotos", {}).get(item_key, [])
                    if fotos_guardadas:
                        st.write(f"**Evidencias adjuntas ({len(fotos_guardadas)}):**")
                        cols = st.columns(4)
                        for f_idx, path_img in enumerate(fotos_guardadas):
                            with cols[f_idx % 4]:
                                if os.path.exists(path_img):
                                    st.image(path_img, use_column_width=True, caption=f"Foto {f_idx + 1}")
                                else:
                                    st.caption("⚠️ Imagen no encontrada")
                    else:
                        st.caption("Aún no se han adjuntado imágenes para este ítem.")

        total_items_global += tot_items
        total_revisados_global += rev_items

    if indice_a_eliminar is not None:
        sol_eliminada = st.session_state.lista_solicitudes.pop(indice_a_eliminar)
        st.session_state.expander_states.pop(sol_eliminada["n_solicitud"], None)
        guardar_base_datos(st.session_state.lista_solicitudes)
        st.success(f"Solicitud N° {sol_eliminada['n_solicitud']} eliminada.")
        st.rerun()

    # 6. MÉTRICAS Y DESCARGA CONSOLIDADA
    st.divider()
    st.subheader("📊 Resumen General")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Ítems Registrados", total_items_global)
    c2.metric("Total Ítems Revisados", total_revisados_global)
    c3.metric("Ítems Pendientes", total_items_global - total_revisados_global)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        current_row = 0
        for sol in st.session_state.lista_solicitudes:
            df_export = sol["data"]
            sheet_name = 'Solicitudes'
            if sheet_name not in writer.sheets:
                pd.DataFrame().to_excel(writer, sheet_name=sheet_name, index=False)
            
            sheet = writer.sheets[sheet_name]
            sheet.cell(row=current_row + 1, column=1, value=f"N°solicitud: {sol['n_solicitud']}")
            
            df_export.to_excel(writer, sheet_name=sheet_name, index=False, startrow=current_row + 1)
            current_row += len(df_export) + 4

    buffer.seek(0)
    st.download_button(
        label="📥 Descargar Reporte Consolidado (Excel)",
        data=buffer,
        file_name="Consolidado_Solicitudes_Revisadas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
else:
    if st.session_state.role == "Operador":
        st.warning("⚠️ No hay solicitudes listas para revisar en este momento. Notifica a un Administrador.")
    else:
        st.info("📌 No hay solicitudes en el sistema. Utiliza la sección superior para cargar un Excel.")