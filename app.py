from flask import Flask, render_template, request, redirect, url_for, flash, session, current_app
from config import Config
import os
from werkzeug.utils import secure_filename # Para nombres de archivo seguros
from datetime import datetime, date # Importar date para manejar fechas
import re # Para validación de email
import json # NUEVA: Importa json para los filtros de Jinja2
from functools import wraps # Importar wraps para decoradores
import uuid # Importar uuid para generar nombres de archivo únicos
from sqlalchemy.exc import IntegrityError # NUEVO: Importar IntegrityError

# MODIFICADO: Importa db, bcrypt, migrate y User desde models.py
# ES CRUCIAL QUE EL MODELO USER Y LAS INSTANCIAS DE DB, BCRYPT Y MIGRATE
# SE IMPORTEN ÚNICAMENTE DESDE models.py PARA EVITAR IMPORTACIONES CIRCULARES.
# CORRECCIÓN: Eliminado 'Version' de la importación de models, ya que está definida en version.py
from models import db, bcrypt, migrate, User, Project, Note, InternationalTravel, Caminata, AbonoCaminata, caminata_participantes, Pagos, CalendarEvent, Instruction, Song, Playlist, Itinerario, AboutUs 
from contactos import contactos_bp
from perfil import perfil_bp
from proyecto import proyecto_bp
from notas import notas_bp
from intern import intern_bp
from caminatas import caminatas_bp
from pagos import pagos_bp
from calendario import calendario_bp
from instrucciones import instrucciones_bp
from player import player_bp
from itinerario import itinerario_bp
from aboutus import aboutus_bp
from rutas import rutas_bp
# CORRECCIÓN: Importa Version desde version.py donde está definida
from version import version_bp, Version 
from files import files_bp # Importa el Blueprint de Files
from btns import btns_bp # Importa el Blueprint desde btns.py (ASUMIMOS QUE btns.py EXISTE)


app = Flask(__name__, instance_relative_config=True)

# ¡IMPORTANTE! Cargar la configuración ANTES de usar app.config
app.config.from_object(Config)

# Asegurarse de que la carpeta 'instance' exista
if not os.path.exists(app.instance_path):
    os.makedirs(app.instance_path)

# Inicializar extensiones con la aplicación Flask
# ESTO DEBE IR ANTES DEL REGISTRO DE BLUEPRINTS SI LOS BLUEPRINTS DEPENDEN DE ELLOS
db.init_app(app)
bcrypt.init_app(app)
migrate.init_app(app, db)


# Configuración para subida de archivos (usando app.config directamente desde el principio)
# Asegúrate de que estas rutas sean absolutas y que el usuario que ejecuta la app tenga permisos de escritura.
# Estas rutas ya deberían estar definidas en config.py, aquí solo las aseguramos
# y creamos las carpetas si no existen.
# AHORA ESTAS LÍNEAS SE EJECUTAN DESPUÉS DE app.config.from_object(Config)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROJECT_IMAGE_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['NOTE_IMAGE_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['CAMINATA_IMAGE_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PAGOS_IMAGE_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['CALENDAR_IMAGE_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['SONGS_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PLAYLIST_COVER_UPLOAD_FOLDER'], exist_ok=True) # Asegurarse de que esta exista
os.makedirs(app.config['INSTRUCTION_ATTACHMENT_FOLDER'], exist_ok=True)
os.makedirs(app.config['MAP_FILES_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['COVERS_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['ABOUTUS_IMAGE_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_FILES_FOLDER'], exist_ok=True)


# Función auxiliar para verificar extensiones permitidas (ahora usando app.config)
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'} # Usar set literal o definir en config

# NUEVA: Función para verificar extensiones de música permitidas
def allowed_music_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'mp3', 'wav', 'ogg'} # Usar set literal o definir en config


# Adjuntando allowed_file y allowed_music_file al objeto 'app'
# Esto permite que los Blueprints accedan a ellos a través de current_app
app.allowed_file = allowed_file
app.allowed_music_file = allowed_music_file


# NUEVOS FILTROS DE JINJA2: Para formatear moneda y parsear JSON en las plantillas
@app.template_filter('format_currency')
def format_currency_filter(value):
    if value is None:
        return "N/A"
    try:
        return f"${value:,.2f}"
    except (ValueError, TypeError):
        return str(value)

@app.template_filter('from_json')
def from_json_filter(value):
    if value:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return [] # Retorna lista vacía si el JSON es inválido
    return []

# Filtro personalizado para Jinja2 para convertir a datetime
@app.template_filter('to_datetime')
def to_datetime_filter(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            # Intenta parsear diferentes formatos si es necesario
            return datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f') # Formato común de SQLAlchemy
        except ValueError:
            try:
                return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                try:
                    return datetime.strptime(value, '%Y-%m-%d')
                except ValueError:
                    # Si no se puede parsear, devuelve None o el valor original
                    return None
    return value


# DECORADORES PARA ROLES (pueden estar en un archivo de utilidades o aquí)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Por favor, inicia sesión para acceder a esta página.', 'info')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(roles):
    """
    Decorador para restringir el acceso a rutas basadas en roles.
    `roles` puede ser una cadena (un solo rol) o una lista de cadenas (múltiples roles).
    """
    if not isinstance(roles, list):
        roles = [roles]

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'logged_in' not in session or not session['logged_in']:
                flash('Por favor, inicia sesión para acceder a esta página.', 'info')
                return redirect(url_for('login'))
            
            user_role = session.get('role')
            if user_role not in roles:
                flash('No tienes permiso para acceder a esta página.', 'danger')
                return redirect(url_for('home')) # O a una página de "Acceso Denegado"
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# NUEVO: Procesador de contexto para inyectar la última versión en todas las plantillas
@app.context_processor
def inject_latest_version():
    try:
        # CORRECCIÓN: Asegurarse de que Version esté disponible en este contexto
        # Ya se importa desde version.py arriba
        latest_version = Version.query.order_by(Version.fecha_creacion.desc()).first()
        if latest_version:
            return {'latest_version_number': latest_version.numero_version}
    except Exception as e:
        # Esto es importante para manejar el caso donde la tabla Version aún no existe
        # durante el primer inicio o antes de las migraciones.
        print(f"DEBUG: Error al obtener la última versión: {e}")
    return {'latest_version_number': 'N/A'} # Valor por defecto si no hay versiones o hay un error


# LÓGICA PARA EL PRIMER SUPERUSUARIO: Se ejecuta antes de cada solicitud
@app.before_request
def check_for_first_user():
    """
    Verifica si no hay usuarios en la base de datos.
    Si no hay, la siguiente ruta de registro permitirá crear un Superuser.
    Esta bandera solo se establece una vez por instancia de la aplicación en memoria.
    """
    # Solo ejecutar si la bandera aún no se ha establecido.
    # Esto evita consultas a la DB en cada request después de la inicialización.
    # Se añade un try-except para manejar el caso de que la tabla 'user' aún no exista
    # durante el primer despliegue o después de un borrado de DB.
    if 'first_user_registration_allowed' not in current_app.config:
        with app.app_context():
            try:
                total_users = db.session.query(User).count()
                if total_users == 0:
                    current_app.config['first_user_registration_allowed'] = True
                    print("DEBUG: No se encontraron usuarios. El próximo registro será un Superuser.")
                else:
                    current_app.config['first_user_registration_allowed'] = False
                    print("DEBUG: Ya existen usuarios. Los registros serán Usuarios Regulares.")
            except Exception as e:
                # Si la tabla 'user' no existe (ej. primer inicio), asumimos que es el primer usuario
                # y permitimos el registro como Superuser.
                current_app.config['first_user_registration_allowed'] = True
                print(f"DEBUG: Error al contar usuarios (posiblemente tabla 'user' no existe): {e}. Se permitirá el registro de Superuser.")


# Rutas principales de la aplicación
@app.route('/')
@app.route('/home') # Añadido /home como ruta alternativa para la página de inicio
def home():
    # Obtener todas las caminatas (similar a como lo hace ver_caminatas en caminatas.py)
    all_caminatas = Caminata.query.order_by(Caminata.fecha.desc()).all()
    search_actividad = request.args.get('actividad')

    if search_actividad:
        caminatas = Caminata.query.filter_by(actividad=search_actividad).all()
    else:
        caminatas = Caminata.query.all()
        
    return render_template('ver_caminatas.html', caminatas=caminatas, search_actividad=search_actividad)


@app.route('/register', methods=['GET', 'POST'])
def register():
    # Opciones para los campos de selección (duplicadas aquí por si el context processor no carga a tiempo)
    provincia_opciones = ["Cartago", "Limón", "Puntarenas", "San José", "Heredia", "Guanacaste", "Alajuela"]
    tipo_sangre_opciones = ["Seleccionar Tipo", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
    actividad_opciones = ["No Aplica", "La Tribu", "Senderista", "Enfermería", "Cocina", "Confección y Diseño", "Restaurante", "Transporte Terrestre", "Transporte Acuatico", "Transporte Aereo", "Migración", "Parque Nacional", "Refugio Silvestre", "Centro de Atracción", "Lugar para Caminata", "Acarreo", "Oficina de trámite", "Primeros Auxilios", "Farmacia", "Taller", "Abogado", "Mensajero", "Tienda", "Polizas", "Aerolínea", "Guía", "Banco", "Otros"]
    capacidad_opciones = ["Seleccionar Capacidad", "Rápido", "Intermedio", "Básico", "Iniciante"]
    participacion_opciones = ["No Aplica", "Solo de La Tribu", "Constante", "Inconstante", "El Camino de Costa Rica", "Parques Nacionales", "Paseo | Recreativo", "Revisar/Eliminar"]

    if request.method == 'POST':
        username = request.form['username_registro']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        nombre = request.form['nombre']
        primer_apellido = request.form['primer_apellido']
        segundo_apellido = request.form.get('segundo_apellido')
        telefono = request.form['telefono']
        email = request.form.get('email')
        telefono_emergencia = request.form.get('telefono_emergencia')
        nombre_emergencia = request.form.get('nombre_emergencia')
        empresa = request.form.get('empresa')
        cedula = request.form.get('cedula')
        direccion = request.form.get('direccion') # Provincia
        fecha_cumpleanos_str = request.form.get('fecha_cumpleanos')
        tipo_sangre = request.form.get('tipo_sangre')
        poliza = request.form.get('poliza')
        aseguradora = request.form.get('aseguradora')
        alergias = request.form.get('alergias')
        enfermedades_cronicas = request.form.get('enfermedades_cronicas')
        actividad = request.form.get('actividad')
        capacidad = request.form.get('capacidad')
        participacion = request.form.get('participacion')

        # Validaciones
        if not (username and password and confirm_password and nombre and primer_apellido and telefono):
            flash('Por favor, completa todos los campos obligatorios.', 'danger')
            return render_template('register.html', 
                                   provincia_opciones=provincia_opciones, 
                                   tipo_sangre_opciones=tipo_sangre_opciones,
                                   actividad_opciones=actividad_opciones,
                                   capacidad_opciones=capacidad_opciones,
                                   participacion_opciones=participacion_opciones)

        if password != confirm_password:
            flash('Las contraseñas no coinciden.', 'danger')
            return render_template('register.html', 
                                   provincia_opciones=provincia_opciones, 
                                   tipo_sangre_opciones=tipo_sangre_opciones,
                                   actividad_opciones=actividad_opciones,
                                   capacidad_opciones=capacidad_opciones,
                                   participacion_opciones=participacion_opciones)

        if len(password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres.', 'danger')
            return render_template('register.html', 
                                   provincia_opciones=provincia_opciones, 
                                   tipo_sangre_opciones=tipo_sangre_opciones,
                                   actividad_opciones=actividad_opciones,
                                   capacidad_opciones=capacidad_opciones,
                                   participacion_opciones=participacion_opciones)

        if User.query.filter_by(username=username).first():
            flash('El nombre de usuario ya existe. Por favor, elige otro.', 'danger')
            return render_template('register.html', 
                                   provincia_opciones=provincia_opciones, 
                                   tipo_sangre_opciones=tipo_sangre_opciones,
                                   actividad_opciones=actividad_opciones,
                                   capacidad_opciones=capacidad_opciones,
                                   participacion_opciones=participacion_opciones)

        if email: # Solo validar email si se proporciona
            if User.query.filter_by(email=email.lower()).first():
                flash('Ese correo electrónico ya está registrado. Por favor, usa otro.', 'danger')
                return render_template('register.html', 
                                       provincia_opciones=provincia_opciones, 
                                       tipo_sangre_opciones=tipo_sangre_opciones,
                                       actividad_opciones=actividad_opciones,
                                       capacidad_opciones=capacidad_opciones,
                                       participacion_opciones=participacion_opciones)

            if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                flash('Formato de correo electrónico inválido.', 'danger')
                return render_template('register.html', 
                                       provincia_opciones=provincia_opciones, 
                                       tipo_sangre_opciones=tipo_sangre_opciones,
                                       actividad_opciones=actividad_opciones,
                                       capacidad_opciones=capacidad_opciones,
                                       participacion_opciones=participacion_opciones)
        
        # Hash de la contraseña
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # Manejo de la imagen de avatar
        avatar_url = None
        if 'avatar' in request.files:
            avatar_file = request.files['avatar']
            if avatar_file and avatar_file.filename != '':
                # Generar un nombre de archivo único
                filename = secure_filename(avatar_file.filename)
                unique_filename = str(uuid.uuid4()) + os.path.splitext(filename)[1]
                
                # Definir la ruta de guardado
                upload_folder = app.config.get('UPLOAD_FOLDER')
                if not upload_folder:
                    flash('Error de configuración: Carpeta de subida de avatares no definida.', 'danger')
                    return redirect(url_for('register'))

                os.makedirs(upload_folder, exist_ok=True)
                
                file_path = os.path.join(upload_folder, unique_filename)
                avatar_file.save(file_path)
                
                # Actualizar la URL del avatar en el usuario
                avatar_url = os.path.join('uploads', 'avatars', unique_filename).replace('\\', '/') # Ruta relativa para URL
            else:
                # Si no se sube ninguna imagen, asignar la imagen por defecto
                avatar_url = 'uploads/avatars/default.png' # Ruta a tu imagen por defecto
        else:
            # Si el campo 'avatar' no está en la solicitud (ej. si no es un formulario multipart)
            avatar_url = 'uploads/avatars/default.png' # Ruta a tu imagen por defecto


        # Convertir fecha de cumpleaños si existe
        fecha_cumpleanos = None
        if fecha_cumpleanos_str:
            try:
                fecha_cumpleanos = datetime.strptime(fecha_cumpleanos_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Formato de fecha de cumpleaños inválido. Usa YYYY-MM-DD.', 'danger')
                return render_template('register.html', 
                                       provincia_opciones=provincia_opciones, 
                                       tipo_sangre_opciones=tipo_sangre_opciones,
                                       actividad_opciones=actividad_opciones,
                                       capacidad_opciones=capacidad_opciones,
                                       participacion_opciones=participacion_opciones)
        
        # Asignar el rol por defecto de 'Usuario Regular'
        role = 'Usuario Regular'
        
        # LÓGICA CLAVE PARA ASIGNAR EL ROL DE SUPERUSUARIO AL PRIMER USUARIO
        # current_app.config.get() es importante por si la bandera no existe (ej. en desarrollo local sin before_request)
        if current_app.config.get('first_user_registration_allowed', False):
            with app.app_context(): # Asegura que la consulta a la DB se haga dentro del contexto de la app
                total_users_after_check = db.session.query(User).count()
                if total_users_after_check == 0:
                    role = 'Superuser'
                    # Desactivar la bandera inmediatamente después de que se registre el primer superuser
                    current_app.config['first_user_registration_allowed'] = False 
                    print(f"DEBUG: Registrando a {username} como Superuser (primer usuario).")
                else:
                    print(f"DEBUG: Ya existen usuarios (verificación secundaria), {username} se registrará como Usuario Regular.")
        else:
            print(f"DEBUG: 'first_user_registration_allowed' es False, {username} se registrará como Usuario Regular.")
        # FIN LÓGICA CLAVE

        new_user = User(
            username=username,
            # CORRECCIÓN: Cambiado 'password_hash' a 'password'
            password=hashed_password, 
            nombre=nombre,
            primer_apellido=primer_apellido,
            segundo_apellido=segundo_apellido,
            telefono=telefono,
            email=email.lower() if email else None,
            telefono_emergencia=telefono_emergencia,
            nombre_emergencia=nombre_emergencia,
            empresa=empresa,
            cedula=cedula,
            direccion=direccion,
            # ELIMINADO: fecha_registro=datetime.utcnow(), # SQLAlchemy lo maneja con default=datetime.utcnow
            # ELIMINADO: fecha_actualizacion=datetime.utcnow(), # SQLAlchemy lo maneja con default=datetime.utcnow
            role=role, # Asignar el rol determinado aquí
            avatar_url=avatar_url, # Guardar la URL del avatar
            fecha_cumpleanos=fecha_cumpleanos,
            tipo_sangre=tipo_sangre,
            poliza=poliza,
            aseguradora=aseguradora,
            alergias=alergias,
            enfermedades_cronicas=enfermedades_cronicas,
            actividad=actividad if actividad != "No Aplica" else None,
            capacidad=capacidad if capacidad != "Seleccionar Capacidad" else None,
            participacion=participacion if participacion != "No Aplica" else None
        )

        try:
            db.session.add(new_user)
            db.session.commit()
            flash('¡Registro exitoso! Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar el usuario: {e}', 'danger')
            current_app.logger.error(f"Error al registrar usuario {username}: {e}")
            return render_template('register.html', 
                                   provincia_opciones=provincia_opciones, 
                                   tipo_sangre_opciones=tipo_sangre_opciones,
                                   actividad_opciones=actividad_opciones,
                                   capacidad_opciones=capacidad_opciones,
                                   participacion_opciones=participacion_opciones)

    return render_template('register.html', 
                           provincia_opciones=provincia_opciones, 
                           tipo_sangre_opciones=tipo_sangre_opciones,
                           actividad_opciones=actividad_opciones,
                           capacidad_opciones=capacidad_opciones,
                           participacion_opciones=participacion_opciones)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_email = request.form['username_or_email']
        password = request.form['password']

        user = User.query.filter((User.username == username_or_email) | (User.email == username_or_email.lower())).first()

        # CORRECCIÓN: Cambiado user.password_hash a user.password
        if user and bcrypt.check_password_hash(user.password, password): 
            session['logged_in'] = True
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role # Guardar el rol en la sesión
            flash(f'¡Bienvenido, {user.username}!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Nombre de usuario, correo electrónico o contraseña incorrectos.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('logged_in', None)
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('role', None) # Eliminar el rol de la sesión
    flash('Has cerrado sesión exitosamente.', 'info')
    return redirect(url_for('login'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

# REGISTRO DE BLUEPRINTS (DEBE IR DESPUÉS DE LA INICIALIZACIÓN DE EXTENSIONES)
app.register_blueprint(contactos_bp)
app.register_blueprint(perfil_bp, url_prefix='/perfil')
app.register_blueprint(proyecto_bp)
app.register_blueprint(notas_bp)
app.register_blueprint(intern_bp, url_prefix='/intern')
app.register_blueprint(caminatas_bp, url_prefix='/caminatas')
app.register_blueprint(pagos_bp, url_prefix='/pagos')
app.register_blueprint(calendario_bp, url_prefix='/calendario')
app.register_blueprint(instrucciones_bp, url_prefix='/instrucciones')
app.register_blueprint(player_bp)
app.register_blueprint(itinerario_bp, url_prefix='/itinerario')
app.register_blueprint(aboutus_bp, url_prefix='/aboutus')
app.register_blueprint(rutas_bp, url_prefix='/rutas')
app.register_blueprint(version_bp, url_prefix='/version')
app.register_blueprint(files_bp, url_prefix='/files')
app.register_blueprint(btns_bp) # REGISTRO DEL BLUEPRINT DE BTNS


if __name__ == '__main__':
    with app.app_context(): # Usar app_context para db.create_all()
        db.create_all()
    app.run(host='0.0.0.0', debug=True, port=3030)


# Migraciones Cmder
        # set FLASK_APP=app.py     <--Crea un directorio de migraciones
        # flask db init             <--
        # $ flask db stamp head
        # $ flask db migrate
        # $ flask db migrate -m "mensaje x"
        # $ flask db upgrade
        # ERROR [flask_migrate] Error: Target database is not up to date.
        # $ flask db stamp head
        # $ flask db migrate
        # $ flask db upgrade
        # git clone https://github.com/kerm1977/MI_APP_FLASK.git
        # mysql> DROP DATABASE kenth1977$db; PYTHONANYWHATE
# -----------------------

# del db.db
# rmdir /s /q migrations
# flask db init
# flask db migrate -m "Reinitial migration with all correct models"
# flask db upgrade


# -----------------------
# Consola de pythonanywhere ante los errores de versiones
# Error: Can't locate revision identified by '143967eb40c0'

# flask db stamp head
# lask db migrate
# flask db upgrade

# Database pythonanywhere
# kenth1977$db
# DROP TABLE alembic_version;
# rm -rf migrations
# flask db init
# flask db migrate -m "Initial migration after reset"
# flask db upgrade

# 21:56 ~/LATRIBU1 (main)$ source env/Scripts/activate
# (env) 21:57 ~/LATRIBU1 (main)$ 

# Cuando se cambia de repositorio
# git remote -v
# git remote add origin <URL_DEL_REPOSITORIO>
# git remote set-url origin <NUEVA_URL_DEL_REPOSITORIO>
# git branchgit remote -v
# git push -u origin flet



# borrar base de datos y reconstruirla
# pip install PyMySQL
# SHOW TABLES;
# 21:56 ~/LATRIBU1 (main)$ source env/Scripts/activate <-- Entra al entorno virtual
# (env) 21:57 ~/LATRIBU1 (main)$
# (env) 23:30 ~/LATRIBU1 (main)$ cd /home/kenth1977/LATRIBU1
# (env) 23:31 ~/LATRIBU1 (main)$ rm -f instance/db.db
# (env) 23:32 ~/LATRIBU1 (main)$ rm -rf migrations
# (env) 23:32 ~/LATRIBU1 (main)$ flask db init
# (env) 23:33 ~/LATRIBU1 (main)$ flask db migrate -m "Initial migration with all models"
# (env) 23:34 ~/LATRIBU1 (main)$ flask db upgrade
# (env) 23:34 ~/LATRIBU1 (main)$ ls -l instance/db.db
