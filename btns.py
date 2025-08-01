# btns.py
import json
import os
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify

# Crea un Blueprint para organizar las rutas relacionadas con los botones.
btns_bp = Blueprint('btns', __name__)

# Define el nombre del archivo donde se guardará la configuración del botón.
# Este archivo se creará en la misma carpeta que btns.py.
CONFIG_FILE = 'button_config.json'

def load_button_config():
    """
    Carga la configuración del botón desde el archivo JSON.
    Si el archivo no existe o está corrupto, devuelve una configuración por defecto.
    """
    default_config = {"link": "#", "visibility_state": "all", "is_visible": True}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            try:
                config = json.load(f)
                # Asegura que visibility_state sea correctamente establecido
                if 'visibility' in config: # Maneja la antigua clave 'visibility'
                    config['visibility_state'] = config.pop('visibility')
                if 'visibility_state' not in config: # Por defecto si falta
                    config['visibility_state'] = 'all'

                # Determina is_visible basado en visibility_state
                config['is_visible'] = (config['visibility_state'] != 'disabled')
                
                return config
            except json.JSONDecodeError:
                print(f"Advertencia: El archivo {CONFIG_FILE} está corrupto. Usando configuración por defecto.")
                return default_config
    return default_config

def save_button_config(config):
    """
    Guarda la configuración del botón en el archivo JSON.
    """
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4) # indent=4 para una mejor legibilidad del JSON

@btns_bp.route('/crear_btns', methods=['GET', 'POST'])
def crear_btns():
    """
    Maneja la lógica para el formulario de configuración del botón.
    - GET: Muestra el formulario con la configuración actual.
    - POST: Procesa el envío del formulario, guarda la nueva configuración y redirige.
    """
    config = load_button_config() # Carga la configuración actual para pre-rellenar el formulario
    if request.method == 'POST':
        # Obtiene los valores del formulario. Si no se encuentran, usa valores por defecto.
        link = request.form.get('enlace', '#')
        visibility_state = request.form.get('visibilidad', 'all')
        
        # Determina is_visible basado en la visibilidad_state seleccionada
        is_visible = (visibility_state != 'disabled')

        # Crea el nuevo diccionario de configuración
        new_config = {"link": link, "visibility_state": visibility_state, "is_visible": is_visible}
        save_button_config(new_config) # Guarda la nueva configuración

        # Muestra un mensaje flash de éxito al usuario
        flash('Configuración del botón guardada con éxito!', 'success')
        # Redirige para evitar el reenvío del formulario al actualizar la página
        return redirect(url_for('btns.crear_btns'))
    # Renderiza la plantilla del formulario, pasando la configuración actual
    return render_template('crear_btns.html', config=config)

@btns_bp.route('/get_btn_config') # Renombrado a /get_btn_config para coincidir con tu frontend
def get_btn_config():
    """
    Endpoint API para que el frontend obtenga la configuración actual del botón.
    Devuelve la configuración como una respuesta JSON.
    """
    # Carga la configuración y la devuelve.
    # load_button_config ya asegura que 'is_visible' y 'visibility_state' estén presentes.
    return jsonify(load_button_config())

@btns_bp.route('/get_session_status')
def get_session_status():
    """
    Endpoint API para que el frontend obtenga el estado actual de la sesión del usuario.
    Esto simula si el usuario está logueado y si es un superusuario.
    """
    return jsonify({
        "logged_in": session.get('logged_in', False), # True si 'logged_in' está en sesión y es True, False en caso contrario
        "is_superuser": session.get('is_superuser', False) # True si 'is_superuser' está en sesión y es True, False en caso contrario
    })

# --- Simulación de Autenticación/Roles de Usuario ---
# Estas rutas son solo para demostración y simulan el inicio y cierre de sesión.
# En una aplicación real, tendrías un sistema de autenticación completo (ej. con Flask-Login).
@btns_bp.route('/login/<role>')
def login(role):
    """
    Simula el inicio de sesión de un usuario con un rol específico.
    Borra la sesión actual y establece las variables de sesión según el rol.
    """
    session.clear() # Limpia todas las variables de sesión anteriores

    if role == 'regular':
        session['logged_in'] = True
        session['is_superuser'] = False
        flash('Has iniciado sesión como Usuario Regular.', 'info')
    elif role == 'superuser':
        session['logged_in'] = True
        session['is_superuser'] = True
        flash('Has iniciado sesión como Superusuario.', 'info')
    else: # Cualquier otro rol o 'logout'
        session['logged_in'] = False
        session['is_superuser'] = False
        flash('Has cerrado sesión.', 'info')
    # Redirige a la página principal para ver el efecto en el botón
    return redirect(url_for('btns.index'))

@btns_bp.route('/index')
def index():
    """
    Ruta para la página principal que contendrá el botón flotante.
    Simplemente renderiza la plantilla base.html.
    """
    # Aquí podrías pasar información de sesión si la necesitas en base.html directamente
    return render_template('base.html')
