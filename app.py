from flask import Flask, render_template, request, redirect, session, flash
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime
from openpyxl import load_workbook
import os

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Configuración de email
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

    # Crear Excel desde plantilla
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'Alta_Cliente_{timestamp}.xlsx'
    file_path = os.path.join('formularios_guardados', filename)
    os.makedirs("formularios_guardados", exist_ok=True)

    crear_excel_desde_plantilla(data, file_path)

    # Enviar correo con adjunto
    enviar_correo_aviso(file_path, form_data.get('correo_comercial'))

    flash('Formulario enviado correctamente.')
    return redirect('/')


def crear_excel_desde_plantilla(data, output_path):
    wb = load_workbook("Copia de Alta de Cliente.xlsx")
    ws = wb["FICHA CLIENTE"]

    # Mapeo de campos del formulario a celdas del Excel
    ws["B3"] = data.get("forma_pago")
    ws["B4"] = data.get("nombre")
    ws["B5"] = data.get("nif")
    ws["D5"] = data.get("telefono_general")
    ws["B6"] = data.get("email_general")
    ws["D6"] = data.get("web")
    ws["B7"] = data.get("direccion")
    ws["D7"] = data.get("cp")
    ws["B8"] = data.get("poblacion")
    ws["D8"] = data.get("provincia")
    ws["D13"] = data.get("otra_forma_pago")

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

    wb.save(output_path)


def enviar_correo_aviso(file_path, comercial_email=None):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    destinatarios = ['tesoreria@dimensasl.com']
    if comercial_email:
        destinatarios.append(comercial_email)
    msg['To'] = ', '.join(destinatarios)
    msg['Subject'] = 'Nuevo formulario de alta de cliente recibido'

    body = 'Se ha recibido un nuevo formulario de alta de cliente. Se adjunta el archivo Excel con la plantilla rellenada.'
    msg.attach(MIMEText(body, 'plain'))

    try:
        with open(file_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(file_path)}')
            msg.attach(part)
    except Exception as e:
        print(f'Error adjuntando el archivo: {e}')

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print('Correo enviado correctamente.')
    except Exception as e:
        print(f'Error enviando el correo: {e}')


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)


