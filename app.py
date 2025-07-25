from flask import Flask, render_template, request, redirect, session, flash
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime
from openpyxl import load_workbook
import os
import io
import threading
import base64

app = Flask(__name__)
app.secret_key = 'supersecretkey'

EMAIL_ADDRESS = 'migueladr191194@gmail.com'
EMAIL_PASSWORD = 'zvup wjjv bwas tebs'

@app.route('/', methods=['GET'])
def formulario():
    return render_template('formulario.html')

@app.route('/plantas', methods=['POST', 'GET'])
def plantas():
    if request.method == 'GET':
        flash('Por favor, rellena primero el formulario de cliente.')
        return redirect('/')
    session['form_data'] = request.form.to_dict()
    return render_template('plantas.html')

@app.route('/guardar', methods=['POST'])
def guardar():
    form_data = session.get('form_data', {})
    plantas_data = request.form.to_dict()
    data = {**form_data, **plantas_data}

    # --- GUARDAR LA FIRMA DIGITAL COMO IMAGEN ---
    firma_base64 = data.get('firma_cliente')
    firma_path = None
    if firma_base64:
        firma_data = firma_base64.split(",")[1]  # Quita el 'data:image/png;base64,'
        firma_path = f"static/firma_{data.get('nombre','cliente')}.png"
        with open(firma_path, "wb") as f:
            f.write(base64.b64decode(firma_data))

    # --- VALIDAR QUE HAYA AL MENOS UNA PLANTA ---
    hay_una_planta = False
    for i in range(1, 11):
        if plantas_data.get(f'planta_nombre_{i}'):
            hay_una_planta = True
            break

    if not hay_una_planta:
        flash('⚠️ Debes rellenar al menos los datos de una planta antes de continuar.')
        return render_template('plantas.html')

    archivo_excel_cliente = crear_excel_en_memoria(data)
    archivo_excel_plantas = crear_excel_plantas_en_memoria(data)

    threading.Thread(
        target=enviar_correo_con_dos_adjuntos,
        args=(archivo_excel_cliente, archivo_excel_plantas, firma_path, data.get('correo_comercial'), data.get('nombre'))
    ).start()

    return render_template("gracias.html")

def crear_excel_en_memoria(data):
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
        fila = 3 + i
        valores = [data.get(campo.format(i), "") for campo in campos]
        if not valores[0]:
            continue
        for col, valor in zip(columnas, valores):
            ws[f"{col}{fila}"] = valor

    excel_mem = io.BytesIO()
    wb.save(excel_mem)
    excel_mem.seek(0)
    return excel_mem


def enviar_correo_con_dos_adjuntos(archivo1, archivo2, firma_path=None, correo_comercial=None, nombre_cliente="cliente"):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    destinatarios = ['tesoreria@dimensasl.com']
    if correo_comercial:
        destinatarios.append(correo_comercial)
    msg['To'] = ', '.join(destinatarios)
    msg['Subject'] = f'Alta de cliente y plantas: {nombre_cliente}'

    # Cuerpo del correo
    body = f"""
    <html>
    <body>
    <p>Buenas,</p>
    <p>Se ha completado el alta de un nuevo cliente en el sistema: <strong>{nombre_cliente}</strong>.</p>

    <p>Adjuntamos en este correo dos archivos Excel:<br>
    - Uno con los datos generales del cliente.<br>
    - Otro con la información detallada de sus plantas.</p>
    """

    # Si hay firma, añadirla en el correo
    if firma_path:
        body += f"""
        <p>Firma digital del cliente:</p>
        <img src="cid:firma_cliente" alt="Firma cliente" style="border:1px solid #000; width:300px;">
        """

    body += """
    <p><strong><span style='color:red;'>⚠️ IMPORTANTE: REENVIAR ESTE CORREO A MIGUEL INDICANDO EL RIESGO A SOLICITAR PARA ESTE CLIENTE, SECTOR Y SUBSECTOR.</span></strong></p>
    <p>Gracias por vuestra colaboración.</p>
    <p>Un saludo,<br>Departamento de Tesorería</p>
    </body>
    </html>
    """

    msg.attach(MIMEText(body, 'html'))

    # Adjuntar Excel cliente
    part1 = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    part1.set_payload(archivo1.read())
    encoders.encode_base64(part1)
    part1.add_header('Content-Disposition', f'attachment; filename="Alta Cliente - {nombre_cliente}.xlsx"')
    msg.attach(part1)

    # Adjuntar Excel plantas
    part2 = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    part2.set_payload(archivo2.read())
    encoders.encode_base64(part2)
    part2.add_header('Content-Disposition', f'attachment; filename="Alta Plantas - {nombre_cliente}.xlsx"')
    msg.attach(part2)

    # Adjuntar firma digital si existe
    if firma_path and os.path.exists(firma_path):
        with open(firma_path, "rb") as f:
            firma = MIMEBase('image', 'png', filename="firma_cliente.png")
            firma.set_payload(f.read())
            encoders.encode_base64(firma)
            firma.add_header('Content-ID', '<firma_cliente>')
            firma.add_header('Content-Disposition', 'inline', filename="firma_cliente.png")
            msg.attach(firma)

    # Enviar correo
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print('✅ Correo con ambos archivos enviado correctamente.')
    except Exception as e:
        print(f'❌ Error al enviar correo: {e}')


if __name__ == '__main__':
    # Asegurarnos de que exista la carpeta static para guardar firmas
    if not os.path.exists("static"):
        os.makedirs("static")

    print("🚀 Servidor Flask corriendo en http://127.0.0.1:5000/")
    app.run(debug=True)




