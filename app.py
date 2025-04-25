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
        args=(archivo_excel_cliente, archivo_excel_plantas, data.get('correo_comercial'), data.get('nombre'))
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

def enviar_correo_con_dos_adjuntos(archivo1, archivo2, correo_comercial=None, nombre_cliente="cliente"):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    destinatarios = ['tesoreria@dimensasl.com']
    if correo_comercial:
        destinatarios.append(correo_comercial)
    msg['To'] = ', '.join(destinatarios)
    msg['Subject'] = f'Alta de cliente y plantas: {nombre_cliente}'

       body = f"""
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
        <!-- Tabla de Riesgo -->
        <td style="vertical-align: top;">
          <table style="border-collapse: collapse; border: 1px solid black;">
            <thead>
              <tr><th style="padding: 5px; border: 1px solid black;">Riesgo</th><th style="padding: 5px; border: 1px solid black;">Selección</th></tr>
            </thead>
            <tbody>
              {''.join(f'<tr><td style="padding:5px; border:1px solid black;">{r}</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>' for r in [0,500,1000,1500,2000,2500,3000,3500,4000,4500,5000,20000])}
              <tr><td style="padding:5px; border:1px solid black;">Otro (especificar)</td><td style="padding:5px; border:1px solid black;"><input type="text" placeholder="Escriba aquí el riesgo"></td></tr>
            </tbody>
          </table>
        </td>

        <!-- Tabla de Sector -->
        <td style="vertical-align: top;">
          <table style="border-collapse: collapse; border: 1px solid black;">
            <thead>
              <tr><th style="padding: 5px; border: 1px solid black;">Sector</th><th style="padding: 5px; border: 1px solid black;">Selección</th></tr>
            </thead>
            <tbody>
              {''.join(f'<tr><td style="padding:5px; border:1px solid black;">{s}</td><td style="padding:5px; border:1px solid black;"><input type="checkbox"></td></tr>' for s in ["Agricultura","Aguas","Alimentación","Distribuidor","Ganadería","Industrial","Piscinas","Sector0"])}
            </tbody>
          </table>
        </td>

        <!-- Tabla de Subsectores -->
        <td style="vertical-align: top;">
          <table style="border-collapse: collapse; border: 1px solid black;">
            <thead>
              <tr><th colspan="2" style="padding: 5px; border: 1px solid black;">Subsectores</th></tr>
            </thead>
            <tbody>
              <tr><td colspan="2" style="font-weight:bold; padding:5px;">Agricultura (AG)</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Agricultura</td></tr>

              <tr><td colspan="2" style="font-weight:bold; padding:5px;">Aguas (A)</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Industrial</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Potable</td></tr>

              <tr><td colspan="2" style="font-weight:bold; padding:5px;">Alimentación (AL)</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Aceituna</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Aditivos, aromas, azúcares y salsas</td></tr>

              <tr><td colspan="2" style="font-weight:bold; padding:5px;">Distribuidor (D)</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Agricultura</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Aguas</td></tr>

              <tr><td colspan="2" style="font-weight:bold; padding:5px;">Ganadería (G)</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Explotaciones Ganaderas</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Fabricación Alimentos FEED</td></tr>

              <tr><td colspan="2" style="font-weight:bold; padding:5px;">Industrial (I)</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Biodiésel</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Cemento, yeso y hormigón</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Fertilizantes y agroquímicos</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Madera</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Química básica</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Química fina / formulados</td></tr>

              <tr><td colspan="2" style="font-weight:bold; padding:5px;">Piscinas (P)</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Privada</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Pública</td></tr>

              <tr><td colspan="2" style="font-weight:bold; padding:5px;">Sector 0 (S)</td></tr>
              <tr><td colspan="2" style="padding:5px;"><input type="checkbox"> Sector 0</td></tr>
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


    msg.attach(MIMEText(body, 'html'))

    part1 = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    part1.set_payload(archivo1.read())
    encoders.encode_base64(part1)
    part1.add_header('Content-Disposition', f'attachment; filename="Alta Cliente - {nombre_cliente}.xlsx"')
    msg.attach(part1)

    part2 = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    part2.set_payload(archivo2.read())
    encoders.encode_base64(part2)
    part2.add_header('Content-Disposition', f'attachment; filename="Alta Plantas - {nombre_cliente}.xlsx"')
    msg.attach(part2)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print('✅ Correo con ambos archivos enviado correctamente.')
    except Exception as e:
        print(f'❌ Error al enviar correo: {e}')






