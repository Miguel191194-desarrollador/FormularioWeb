from flask import Flask, render_template, request, redirect, session, flash
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Necesario para mantener la sesión entre páginas

# Configuración de email
EMAIL_ADDRESS = 'tesoreria@dimensasl.com'
EMAIL_PASSWORD = 'Ma.3618d.'

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

    # Enviar correo de aviso
    enviar_correo_aviso()

    # Mensaje de éxito
    flash('Formulario enviado correctamente.')
    return redirect('/')

def enviar_correo_aviso():
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = EMAIL_ADDRESS  # Aquí defines a quién quieres enviar el aviso
    msg['Subject'] = 'Nuevo formulario de alta de cliente recibido'

    body = 'Se ha recibido un nuevo formulario de alta de cliente.'
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP('smtp.office365.com', 587) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f'Error enviando el correo: {e}')

if __name__ == '__main__':
    # Cambiado para que funcione en Render
    app.run(host='0.0.0.0', port=10000)
