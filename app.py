# app.py
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

# (Opcional en local) .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = Flask(__name__)
app.secret_key = 'supersecretkey'

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ===== Config =====
GAS_WEBHOOK_URL = os.getenv("GAS_WEBHOOK_URL")    # URL de Apps Script (termina en /exec)
MAIL_TO_ADMIN   = os.getenv("MAIL_TO_ADMIN")      # opcional
FORCE_SYNC_SEND = os.getenv("FORCE_SYNC_SEND", "false").lower() in ("1", "true", "yes")

# ===== Rutas =====
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

    # Firma base64 (canvas)
    firma_base64 = data.get('firma_cliente')
    firma_bytes = None
    if firma_base64:
        try:
            firma_bytes = base64.b64decode(firma_base64.split(",")[1])
        except Exception:
            firma_bytes = None

    # Validación mínima: al menos una planta
    hay_una_planta = any(plantas_data.get(f'planta_nombre_{i}') for i in range(1, 11))
    if not hay_una_planta:
        flash('⚠️ Debes rellenar al menos los datos de una planta antes de continuar.')
        return render_template('plantas.html', datos_cliente=form_data)

    # Generar Excels
    try:
        excel_cliente = crear_excel_en_memoria(data, firma_bytes)
        excel_plantas = crear_excel_plantas_en_memoria(data)
    except Exception as e:
        logging.exception("❌ Error generando Excels")
        flash(f'Error generando Excels: {e}')
        return render_template('plantas.html', datos_cliente=form_data)

    if not GAS_WEBHOOK_URL:
        logging.error("❌ GAS_WEBHOOK_URL no configurado")
        flash('Error de configuración: falta GAS_WEBHOOK_URL en el servidor.')
        return render_template('gracias.html')

    nombre_cliente = data.get('nombre') or "cliente"
    correo_comercial = data.get('correo_comercial')

    if FORCE_SYNC_SEND:
        ok, detalle = enviar_un_correo_con_dos_adjuntos(excel_cliente, excel_plantas, correo_comercial, nombre_cliente)
        flash('Documentación enviada correctamente.' if ok else f'Error enviando: {detalle}')
        return render_template("gracias.html")
    else:
        threading.Thread(
            target=_thread_enviar_unico,
            args=(excel_cliente, excel_plantas, correo_comercial, nombre_cliente),
            daemon=True
        ).start()
        return render_template("gracias.html")

def _thread_enviar_unico(archivo1, archivo2, correo, nombre):
    try:
        ok, detalle = enviar_un_correo_con_dos_adjuntos(archivo1, archivo2, correo, nombre)
        if ok:
            logging.info("✅ Envío (1 correo, 2 adjuntos): %s", detalle)
        else:
            logging.error("❌ Fallo de envío (1 correo): %s", detalle)
    except Exception as e:
        logging.exception("❌ Excepción en hilo de envío: %s", e)

# ===== Funciones Excel =====
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

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio

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

    for i in range(1, 10+1):
        fila = 3 + i  # i=1 -> fila 4
        valores = [data.get(campo.format(i), "") for campo in campos]
        if not valores[0]:
            continue
        for col, valor in zip(columnas, valores):
            ws[f"{col}{fila}"] = valor

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio

# ===== Envío por Webhook (1 correo con 2 adjuntos) =====
def _build_recipients(correo_comercial):
    dest = ['tesoreria@dimensasl.com']
    if correo_comercial and "@" in correo_comercial:
        dest.append(correo_comercial)
    if MAIL_TO_ADMIN and "@" in MAIL_TO_ADMIN:
        dest.append(MAIL_TO_ADMIN)
    return ",".join(dest)

def _encode_attachment(bytes_io, filename):
    bytes_io.seek(0)
    raw = bytes_io.getvalue()
    b64 = base64.b64encode(raw).decode("utf-8")
    # Enviamos "content" y "base64" para compatibilidad con cualquier Apps Script
    return {
        "filename": filename,
        "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "content": b64,
        "base64": b64,
        "raw_size": len(raw),
    }

def _post_to_webhook(payload):
    try:
        r = requests.post(GAS_WEBHOOK_URL, json=payload, timeout=30)
        logging.info("Webhook status=%s body=%s", r.status_code, r.text[:400])
        if r.status_code == 200 and "OK" in r.text:
            return True, f"status={r.status_code}"
        return False, f"Webhook error status={r.status_code} body={r.text[:400]}"
    except Exception as e:
        logging.exception("Excepción en requests.post")
        return False, f"Excepción: {e}"

def enviar_un_correo_con_dos_adjuntos(archivo_cliente, archivo_plantas, correo_comercial, nombre_cliente):
    if not GAS_WEBHOOK_URL:
        return False, "Falta GAS_WEBHOOK_URL"

    to_csv = _build_recipients(correo_comercial)
    subject = f"Alta de cliente: {nombre_cliente} — Documentación"
    body_html = construir_body_html(nombre_cliente)

    att1 = _encode_attachment(archivo_cliente, f"Copia Alta de Cliente - {nombre_cliente}.xlsx")
    att2 = _encode_attachment(archivo_plantas, f"Copia Alta de Plantas - {nombre_cliente}.xlsx")

    payload = {
        "to": to_csv,
        "subject": subject,
        "text": "Adjuntamos la documentación del alta (Cliente y Plantas).",
        "html": body_html,
        "attachments": [
            {k: v for k, v in att1.items() if k != "raw_size"},
            {k: v for k, v in att2.items() if k != "raw_size"}
        ]
    }

    ok, detalle = _post_to_webhook(payload)
    return ok, detalle

def construir_body_html(nombre_cliente):
    # Cuerpo completo con las tablas (riesgo, sector y subsectores)
    return f"""
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
                        <tr><th style="padding: 5px; border: 1px solid black;">Distribuidor</th><th style="padding: 5 px; border: 1px solid black;">Selección</th></tr>
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
                        <tr><th style="padding: 5px; border: 1px solid black;">Sector 0</th><th style="padding: 5 px; border: 1px solid black;">Selección</th></tr>
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

# ===== Main =====
if __name__ == '__main__':
    app.run(debug=True)





