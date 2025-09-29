from flask import Flask, render_template, request, redirect, flash
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as ExcelImage
import io
import threading
import base64
import tempfile
import os
import logging
import requests

# (Opcional en local) carga .env si existe; en Render usará Environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = Flask(__name__)
app.secret_key = 'supersecretkey'
logging.basicConfig(level=logging.INFO)

# =========================
#  CONFIG (ENTORNO/RENDER)
# =========================
# Debes tener esta variable en Render → Service → Environment
GAS_WEBHOOK_URL = os.getenv("GAS_WEBHOOK_URL")   # URL de Apps Script (termina en /exec)
MAIL_TO_ADMIN   = os.getenv("MAIL_TO_ADMIN")     # opcional: copia de seguridad

# =========================
#  RUTAS
# =========================

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

    # Firma en base64 (proveniente de un <canvas> o similar)
    firma_base64 = data.get('firma_cliente')
    firma_bytes = None
    if firma_base64:
        try:
            # Se espera "data:image/png;base64,AAAA..."
            firma_bytes = base64.b64decode(firma_base64.split(",")[1])
        except Exception:
            firma_bytes = None

    # Validación: al menos una planta
    hay_una_planta = any(plantas_data.get(f'planta_nombre_{i}') for i in range(1, 11))
    if not hay_una_planta:
        flash('⚠️ Debes rellenar al menos los datos de una planta antes de continuar.')
        return render_template('plantas.html', datos_cliente=form_data)

    # Generar excels en memoria
    archivo_excel_cliente = crear_excel_en_memoria(data, firma_bytes)
    archivo_excel_plantas = crear_excel_plantas_en_memoria(data)

    # Enviar correos (2 correos: 1 por cada adjunto) vía Gmail / Apps Script en segundo plano
    threading.Thread(
        target=enviar_correos_alta_cliente_via_webhook,
        args=(archivo_excel_cliente, archivo_excel_plantas, data.get('correo_comercial'), data.get('nombre') or "cliente"),
        daemon=True
    ).start()

    return render_template("gracias.html")

# =========================
#  FUNCIONES EXCEL
# =========================

def crear_excel_en_memoria(data, firma_bytes=None):
    """
    Rellena la plantilla 'Copia de Alta de Cliente.xlsx' (hoja 'FICHA CLIENTE')
    y devuelve un BytesIO con el archivo.
    """
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

    # Insertar imagen de firma si la hay
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
    """
    Rellena la plantilla 'Copia de Alta de Plantas.xlsx' (hoja 'Plantas')
    y devuelve un BytesIO con el archivo.
    Empieza a escribir en fila 4 (3 + i) y usa columnas B..M (orden directo).
    """
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
        fila = 3 + i  # i=1 -> fila 4
        valores = [data.get(campo.format(i), "") for campo in campos]
        if not valores[0]:  # sin nombre de planta -> omite
            continue
        for col, valor in zip(columnas, valores):
            ws[f"{col}{fila}"] = valor

    excel_mem = io.BytesIO()
    wb.save(excel_mem)
    excel_mem.seek(0)
    return excel_mem

# =========================
#  ENVÍO POR WEBHOOK GMAIL
# =========================

def enviar_via_gmail_webhook_bytes(to_email, subject, text, html, attachment_bytes=None, filename=None, mime_type=None):
    """
    Envía un email a través de Google Apps Script (MailApp) usando la URL del webhook (GAS_WEBHOOK_URL).
    Acepta UN adjunto por envío (por eso mandamos 2 correos cuando hay 2 excels).
    """
    if not GAS_WEBHOOK_URL:
        raise RuntimeError("Falta GAS_WEBHOOK_URL")

    payload = {
        "to": to_email,
        "subject": subject,
        "text": text or "",
        "html": html or (text or "")
    }

    if attachment_bytes is not None and filename and mime_type:
        payload["attachmentBase64"] = base64.b64encode(attachment_bytes).decode("utf-8")
        payload["filename"] = filename
        payload["mimeType"] = mime_type

    r = requests.post(GAS_WEBHOOK_URL, json=payload, timeout=20)
    if r.status_code != 200 or "OK" not in r.text:
        raise RuntimeError(f"Webhook Gmail error: {r.status_code} {r.text}")
    logging.info(f"✅ Correo enviado: {subject}")

def enviar_correos_alta_cliente_via_webhook(archivo1, archivo2, correo_comercial, nombre_cliente):
    """
    Envía dos correos:
      1) Ficha Cliente (Excel 1)
      2) Plantas (Excel 2)
    Incluye el cuerpo HTML largo con todas las tablas que nos pasaste.
    """
    destinatarios = ['tesoreria@dimensasl.com']
    if correo_comercial and "@" in correo_comercial:
        destinatarios.append(correo_comercial)
    if MAIL_TO_ADMIN and "@" in MAIL_TO_ADMIN:
        destinatarios.append(MAIL_TO_ADMIN)
    to_csv = ",".join(destinatarios)

    # ======= CUERPO HTML COMPLETO (SIN RECORTES) =======
    body_html = f"""
    <html>
    <body>
    <p>Buenas,</p>
    <p>Se ha completado el alta de un nuevo cliente en el sistema: <strong>{nombre_cliente}</strong>.</p>
    <p>Adjuntamos en este correo dos archivos Excel:<br>
    - Uno con los datos generales del cliente.<br>
    - Otro con la información detallada de sus plantas.</p>

    <p><strong><span style='color:red;'>⚠️ IMPORTANTE: REENVIAR ESTE CORREO A MIGUEL INDICANDO EL RIESGO A SOLICITAR PARA ESTE CLIENTE, SECTOR Y SUBSECTOR.</span></strong></p>

    <p><strong>Seleccione el riesgo, el sector y el subsector marcando la casilla correspondiente:</strong></p>

    <table style="width: 100%; border-collapse: collapse;" cellspacing="15">
        <tr>
            <td style="vertical-align: top;">
                <table style="border-collapse: collapse; border: 1px solid black;">
                    <thead>
                        <tr><th style="padding: 5px; border: 1px solid black;">Riesgo</th><th style="padding: 5px; border: 1px solid black;">Selección</th></tr>
                    </thead>
                    <tbody>
                        <tr><td style="padding:5px; border:1px solid black;">0</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">500</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">1000</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">1500</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">2000</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">2500</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">3000</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">3500</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">4000</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">4500</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">5000</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">20000</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">Otro (especificar)</td><td style="padding:5px; border:1px solid black;"><input type="text" placeholder="Escriba aquí el riesgo"></td></tr>
                    </tbody>
                </table>
            </td>

            <td style="vertical-align: top;">
                <table style="border-collapse: collapse; border: 1px solid black;">
                    <thead>
                        <tr><th style="padding: 5px; border: 1px solid black;">Sector</th><th style="padding: 5px; border: 1px solid black;">Selección</th></tr>
                    </thead>
                    <tbody>
                        <tr><td style="padding:5px; border:1px solid black;">Agricultura</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">Aguas</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">Alimentación</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">Distribuidor</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">Ganadería</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">Industrial</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">Piscinas</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">Sector0</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                    </tbody>
                </table>
            </td>

            <td style="vertical-align: top;">
                <table style="border-collapse: collapse; border: 1px solid black;">
                    <thead>
                        <tr><th colspan="2" style="padding: 5px; border: 1px solid black;">Subsectores</th></tr>
                    </thead>
                    <tbody>
                        <tr><th style="padding: 5px; border: 1px solid black;">Agricultura</th><th style="padding: 5px; border: 1px solid black;">Selección</th></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(AG)Agricultura</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><th style="padding: 5px; border: 1px solid black;">Aguas</th><th style="padding: 5px; border: 1px solid black;">Selección</th></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(A)Industrial</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(A)Potable</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(A)Residual</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><th style="padding: 5px; border: 1px solid black;">Alimentación</th><th style="padding: 5px; border: 1px solid black;">Selección</th></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(AL)Aceituna</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(AL)Aditivos, aromas, azucares y salsas</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(AL)Bebidas</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(AL)Cárnicas</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(AL)Chocolate, café y confiteria</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(AL)Conserva - procesado frutas, hortalizas y cereales</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(AL)Grasas animales y vegetales</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(AL)Lácteos</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(AL)Panadería,pasta,harina,galletas, y pasteleria</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(AL)Pescado</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(AL)Vino</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><th style="padding: 5px; border: 1px solid black;">Distribuidor</th><th style="padding: 5px; border: 1px solid black;">Selección</th></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(D)Agricultura</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(D)Aguas</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(D)Alimentación</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(D)Ganadería</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(D)Industrial</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(D)Piscinas</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><th style="padding: 5px; border: 1px solid black;">Ganadería</th><th style="padding: 5px; border: 1px solid black;">Selección</th></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(G)Explotaciones Ganaderas</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(G)Fabricación Alimentos FEED</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><th style="padding: 5px; border: 1px solid black;">Industrial</th><th style="padding: 5px; border: 1px solid black;">Selección</th></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Biodiésel</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Cemento,yeso y hormigón</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Comercio</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Construcción</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Detergencia y Cosmética</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Energía</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Energía Renovable</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Farmacia</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Fertilizantes y agroquímicos</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Madera</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Metalurgia</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Minerales</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Papel y cartón</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Petróleo y gas</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Pinturas,barnices,resinas,masillas,tintas</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Plástico</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Química básica</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Química fina / formulados</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Residuos</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Textil y curtidos</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Transportes</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(I)Vidrio y Cerámica</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><th style="padding: 5px; border: 1px solid black;">Piscinas</th><th style="padding: 5px; border: 1px solid black;">Selección</th></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(P)Privada</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(P)Pública</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                        <tr><th style="padding: 5px; border: 1px solid black;">Sector 0</th><th style="padding: 5px; border: 1px solid black;">Selección</th></tr>
                        <tr><td style="padding:5px; border:1px solid black;">(S)Sector 0</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>
                    </tbody>
                </table>
            </td>
        </tr>
    </table>

    <p>Gracias por vuestra colaboración.</p>
    <p>Un saludo,<br>Departamento de Tesorería</p>
    </body>
    </html>
    """

    # 1/2 — FICHA CLIENTE
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

    # 2/2 — PLANTAS
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

# =========================
#  MAIN
# =========================

if __name__ == '__main__':
    # En local: python app.py
    # En Render: el propio servicio lanza el proceso con tu start command.
    app.run(debug=True)






