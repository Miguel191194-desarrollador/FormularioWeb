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

    # Crear Excel (solo con campos esenciales por ahora)
    archivo_excel = crear_excel_en_memoria(data)

    # Enviar en segundo plano
    threading.Thread(target=enviar_correo_con_adjunto, args=(archivo_excel, data.get('correo_comercial'), data.get('nombre'))).start()

    return render_template("gracias.html")

def crear_excel_en_memoria(data):
    wb = load_workbook("Copia de Alta de Cliente.xlsx")
    ws = wb["FICHA CLIENTE"]

    # ⚠️ Solo campos básicos por ahora
    ws["B3"] = data.get("forma_pago")
    ws["B4"] = data.get("nombre")
    ws["B5"] = data.get("nif")
    ws["D5"] = data.get("telefono_general")
    ws["B6"] = data.get("email_general")

    excel_mem = io.BytesIO()
    wb.save(excel_mem)
    excel_mem.seek(0)
    return excel_mem

def enviar_correo_con_adjunto(archivo_memoria, correo_comercial=None, nombre_cliente="cliente"):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    destinatarios = ['tesoreria@dimensasl.com']
    if correo_comercial:
        destinatarios.append(correo_comercial)
    msg['To'] = ', '.join(destinatarios)
    msg['Subject'] = f'Nuevo alta de cliente: {nombre_cliente}'

    body = 'Adjunto encontrarás la ficha de alta del cliente rellenada.'
    msg.attach(MIMEText(body, 'plain'))

    part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    part.set_payload(archivo_memoria.read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="Alta Cliente - {nombre_cliente}.xlsx"')
    msg.attach(part)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print('✅ Correo enviado correctamente.')
    except Exception as e:
        print(f'❌ Error al enviar correo: {e}')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)




