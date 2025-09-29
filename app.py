from flask import Flask, render_template, request, redirect, flash
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as ExcelImage
from email import encoders
import io, threading, base64, tempfile
import os, logging, requests

app = Flask(__name__)
app.secret_key = 'supersecretkey'
logging.basicConfig(level=logging.INFO)

# === Usamos el mismo webhook de Gmail (Apps Script) que ya tienes ===
GAS_WEBHOOK_URL = os.getenv("GAS_WEBHOOK_URL")   # En Render ya la creaste
MAIL_TO_ADMIN   = os.getenv("MAIL_TO_ADMIN")     # opcional, para copias

# ------------------- RUTAS -------------------

@app.route('/', methods=['GET'])
def formulario():
    return render_template('formulario.html')

@app.route('/plantas', methods=['POST', 'GET'])
def plantas():
    if request.method == 'GET':
        flash('Por favor, rellena primero el formulario de cliente.')
        return redirect('/')
    datos_cliente = request.form.to_dict()
    return render_template('plantas.html', datos_cliente=datos_cliente)

@app.route('/guardar', methods=['POST'])
def guardar():
    form_data = request.form.to_dict()
    plantas_data = request.form.to_dict()
    data = {**form_data, **plantas_data}

    # Firma en base64 (canvas) -> bytes
    firma_base64 = data.get('firma_cliente')
    firma_bytes = None
    if firma_base64:
        try:
            firma_bytes = base64.b64decode(firma_base64.split(",")[1])
        except Exception:
            firma_bytes = None

    # Validación: al menos una planta
    hay_una_planta = any(plantas_data.get(f'planta_nombre_{i}') for i in range(1, 11))
    if not hay_una_planta:
        flash('⚠️ Debes rellenar al menos los datos de una planta antes de continuar.')
        return render_template('plantas.html', datos_cliente=form_data)

    # Generar excels en memoria (BytesIO)
    archivo_excel_cliente = crear_excel_en_memoria(data, firma_bytes)
    archivo_excel_plantas = crear_excel_plantas_en_memoria(data)

    # Enviar 2 correos (uno por adjunto) vía webhook, en hilo
    threading.Thread(
        target=enviar_correos_alta_cliente_via_webhook,
        args=(archivo_excel_cliente, archivo_excel_plantas, data.get('correo_comercial'), data.get('nombre') or "cliente"),
        daemon=True
    ).start()

    return render_template("gracias.html")

# ------------------- FUNCIONES AUXILIARES -------------------

def crear_excel_en_memoria(data, firma_bytes=None):
    wb = load_workbook("Copia de Alta de Cliente.xlsx")
    ws = wb["FICHA CLIENTE"]

    ws["B4"] = data.get("nombre")
    ws["B5"] = data.get("nif")
    ws["D5"] = data.get("telefono_general")
    ws["B6"] = data.get("email_general")
    ws["D6"] = data.get("web")
    ws["B7"] = data.get("direccion")
    ws["D7"] = data.get("cp")
    ws["B8"] = data.get("poblacion")
    ws["D8"] = data.get("provincia")
    ws["B13"] = data.get("forma_pago")
    ws["B18"] = data.get("compras_nombre")
    ws["D18"] = data.get("compras_telefono")
    ws["B19"] = data.get("compras_email")
    ws["B22"] = data.get("contabilidad_nombre")
    ws["D22"] = data.get("contabilidad_telefono")
    ws["B24"] = data.get("contabilidad_email")
    ws["B27"] = data.get("facturacion_nombre")
    ws["D27"] = data.get("facturacion_telefono")
    ws["B29"] = data.get("facturacion_email")
    ws["B32"] = data.get("descarga_nombre")
    ws["D32"] = data.get("descarga_telefono")
    ws["B34"] = data.get("descarga_email")
    ws["C38"] = data.get("contacto_documentacion")
    ws["C39"] = data.get("contacto_devoluciones")
    ws["B43"] = data.get("sepa_nombre_banco")
    ws["B44"] = data.get("sepa_domicilio_banco")
    ws["B45"] = data.get("sepa_cp")
    ws["B46"] = data.get("sepa_poblacion")
    ws["B47"] = data.get("sepa_provincia")
    ws["B48"] = data.get("iban_completo")

    if firma_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(firma_bytes)
            tmp_path = tmp.name
        try:
            img = ExcelImage(tmp_path)
            img.width = 200
            img.height = 60
            ws.add_image(img, "B49")
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    excel_mem = io.BytesIO()
    wb.save(excel_mem)
    excel_mem.seek(0)
    return excel_mem

def crear_excel_plantas_en_memoria(data):
    wb = load_workbook("Copia de Alta de Plantas.xlsx")
    ws = wb["Plantas"]

    columnas = ["B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M"]
    campos = [
        "planta_nombre_{}", "planta_direccion_{}", "planta_cp_{}", "planta_poblacion_{}",
        "planta_provincia_{}", "planta_telefono_{}", "planta_email_{}", "planta_horario_{}",
        "planta_observaciones_{}", "planta_contacto_nombre_{}", "planta_contacto_telefono_{}",
        "planta_contacto_email_{}"
    ]

    for i in range(1, 11):
        fila = 3 + i  # en tu plantilla de "Alta de Plantas.xlsx" empiezas en fila 4
        valores = [data.get(campo.format(i), "") for campo in campos]
        if not valores[0]:
            continue
        for col, valor in zip(columnas, valores):
            ws[f"{col}{fila}"] = valor

    excel_mem = io.BytesIO()
    wb.save(excel_mem)
    excel_mem.seek(0)
    return excel_mem

# -------- Envío vía Gmail (Apps Script) --------

def enviar_via_gmail_webhook_bytes(to_email, subject, text, html, attachment_bytes=None, filename=None, mime_type=None):
    if not GAS_WEBHOOK_URL:
        raise RuntimeError("Falta GAS_WEBHOOK_URL")
    payload = {
        "to": to_email,
        "subject": subject,
        "text": text or "",
        "html": html or (text or "")
    }
    if attachment_bytes and filename and mime_type:
        payload["attachmentBase64"] = base64.b64encode(attachment_bytes).decode("utf-8")
        payload["filename"] = filename
        payload["mimeType"] = mime_type

    r = requests.post(GAS_WEBHOOK_URL, json=payload, timeout=20)
    if r.status_code != 200 or "OK" not in r.text:
        raise RuntimeError(f"Webhook Gmail error: {r.status_code} {r.text}")
    logging.info(f"✅ Correo enviado: {subject}")

def enviar_correos_alta_cliente_via_webhook(archivo1, archivo2, correo_comercial, nombre_cliente):
    # Destinatarios como lista → Gmail acepta CSV en "to"
    destinatarios = ['tesoreria@dimensasl.com']
    if correo_comercial and "@" in correo_comercial:
        destinatarios.append(correo_comercial)
    if MAIL_TO_ADMIN and "@" in MAIL_TO_ADMIN:
        destinatarios.append(MAIL_TO_ADMIN)
    to_csv = ",".join(destinatarios)

    # Cuerpo HTML (el mismo que ya usabas)
    body_html = f"""
    <html>
    <body>
    <p>Buenas,</p>
    <p>Se ha completado el alta de un nuevo cliente en el sistema: <strong>{nombre_cliente}</strong>.</p>
    <p>Adjuntamos en este correo dos archivos Excel:<br>
    - Uno con los datos generales del cliente.<br>
    - Otro con la información detallada de sus plantas.</p>

    <p><strong><span style='color:red;'>⚠️ IMPORTANTE: REENVIAR ESTE CORREO A MIGUEL INDICANDO EL RIESGO A SOLICITAR PARA ESTE CLIENTE, SECTOR Y SUBSECTOR.</span></strong></p>

    <!-- (Tablas largas omitidas aquí por brevedad; puedes mantener tu HTML original) -->
    <p>Gracias por vuestra colaboración.</p>
    <p>Un saludo,<br>Departamento de Tesorería</p>
    </body>
    </html>
    """

    # 1/2: Excel de CLIENTE
    archivo1.seek(0)
    enviar_via_gmail_webhook_bytes(
        to_email=to_csv,
        subject=f"Alta de cliente: {nombre_cliente} (1/2) — Ficha Cliente",
        text="Alta de cliente — Ficha Cliente",
        html=body_html,
        attachment_bytes=archivo1.getvalue(),
        filename=f"Alta Cliente - {nombre_cliente}.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # 2/2: Excel de PLANTAS
    archivo2.seek(0)
    enviar_via_gmail_webhook_bytes(
        to_email=to_csv,
        subject=f"Alta de cliente: {nombre_cliente} (2/2) — Plantas",
        text="Alta de cliente — Plantas",
        html=body_html,
        attachment_bytes=archivo2.getvalue(),
        filename=f"Alta Plantas - {nombre_cliente}.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ------------------- EJECUTAR -------------------

if __name__ == '__main__':
    # En local puedes usar flask run o python app.py
    app.run(debug=True)









