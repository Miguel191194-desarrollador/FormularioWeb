from flask import Flask, render_template, request, redirect, session, flash
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Necesario para mantener la sesión entre páginas

# Configuración de email
EMAIL_ADDRESS = 'migueladr191194@gmail.com'  # Tu correo ✅
EMAIL_PASSWORD = 'zvup wjjv bwas tebs'  # Tu contraseña ✅

# Ruta donde se guardarán los Excel generados
SAVE_FOLDER = 'formularios_guardados'
os.makedirs(SAVE_FOLDER, exist_ok=True)

@app.route('/', methods=['GET'])
def formulario():
    return render_template('formulario.html')

@app.route('/plantas', methods=['POST', 'GET'])
def plantas():
    if request.method == 'GET':
        print("Acceso directo GET a /plantas, redirigiendo a /")
        flash('Por favor, rellena primero el formulario de cliente.')
        return redirect('/')

    # Guardamos los datos de la primera página en sesión
    session['form_data'] = request.form.to_dict()
    print("Datos recibidos en formulario inicial:", session['form_data'])
    return render_template('plantas.html')

@app.route('/guardar', methods=['POST'])
def guardar():
    # Recuperamos los datos de la sesión y de las plantas
    form_data = session.get('form_data', {})
    plantas_data = request.form.to_dict()

    # Unimos todos los datos
    data = {**form_data, **plantas_data}

    # Guardar en Excel
    df = pd.DataFrame([data])
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_path = os.path.join(SAVE_FOLDER, f'alta_cliente_{timestamp}.xlsx')
    df.to_excel(file_path, index=False)

    # Enviar correo de aviso con adjunto
    enviar_correo_aviso(file_path)

    # Mensaje de éxito
    flash('Formulario enviado correctamente.')
    return redirect('/')

def enviar_correo_aviso(file_path):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = tesoreria@dimensasl.com  # Puedes añadir más correos si quieres
    msg['Subject'] = 'Nuevo formulario de alta de cliente recibido'

    body = 'Se ha recibido un nuevo formulario de alta de cliente. Se adjunta el archivo Excel.'
    msg.attach(MIMEText(body, 'plain'))

    # Adjuntar el archivo Excel
    try:
        with open(file_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(file_path)}')
            msg.attach(part)
    except Exception as e:
        print(f'Error adjuntando el archivo: {e}')

    # Enviar el correo
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print('Correo enviado correctamente.')
    except Exception as e:
        print(f'Error enviando el correo: {e}')

if __name__ == '__main__':
    # Cambiado para que funcione en Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

