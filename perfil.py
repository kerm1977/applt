# En perfil.py (o donde manejes las estadísticas)
from flask import Blueprint, current_app, render_template, session, redirect, url_for, flash, request, send_file # Añadido Blueprint
from models import db, bcrypt, User, SiteStats, Caminata, Project, CalendarEvent, Note # Asegúrate de importar tus modelos y db
from sqlalchemy import func # Importar func para funciones de agregación como count
import os
from datetime import datetime, date # Importar date para manejar fechas
from werkzeug.utils import secure_filename # Importar para manejo de archivos
import shutil # Importar para copiar archivos (para backup y restore)
from functools import wraps # Importar wraps desde functools
import uuid # NUEVO: Importar uuid para generar nombres de archivo únicos

# DECORADOR PARA ROLES (Si no lo importas de app.py, puedes tenerlo aquí o en un archivo de utilidades)
def role_required(roles):
    """
    Decorador para restringir el acceso a rutas basadas en roles.
    `roles` puede ser una cadena (un solo rol) o una lista de cadenas (múltiples roles).
    """
    if not isinstance(roles, list):
        roles = [roles]

    def decorator(f):
        @wraps(f) # Importar wraps desde functools
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

perfil_bp = Blueprint('perfil', __name__, url_prefix='/perfil') # Asegúrate de que el url_prefix sea '/perfil'

# Opciones para los campos de selección, definidas aquí para ser pasadas a la plantilla
actividad_opciones = ["No Aplica", "La Tribu", "Senderista", "Enfermería", "Cocina", "Confección y Diseño", "Restaurante", "Transporte Terrestre", "Transporte Acuatico", "Transporte Aereo", "Migración", "Parque Nacional", "Refugio Silvestre", "Centro de Atracción", "Lugar para Caminata", "Acarreo", "Oficina de trámite", "Primeros Auxilios", "Farmacia", "Taller", "Abogado", "Mensajero", "Tienda", "Polizas", "Aerolínea", "Guía", "Banco", "Otros"]
capacidad_opciones = ["Seleccionar Capacidad", "Rápido", "Intermedio", "Básico", "Iniciante"]
participacion_opciones = ["No Aplica", "Solo de La Tribu", "Constante", "Inconstante", "El Camino de Costa Rica", "Parques Nacionales", "Paseo | Recreativo", "Revisar/Eliminar"]
tipo_sangre_opciones = ["Seleccionar Tipo", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
provincia_opciones = ["Cartago", "Limón", "Puntarenas", "San José", "Heredia", "Guanacaste", "Alajuela"]
role_opciones = ['Usuario Regular', 'Administrador', 'Superuser'] # Opciones de rol para el select, si es visible

@perfil_bp.route('/') # La ruta base del blueprint /perfil
@perfil_bp.route('/perfil') # También accesible por /perfil/perfil
@role_required(['Superuser', 'Usuario Regular'])
def perfil():
    user_id = session.get('user_id')
    if not user_id:
        flash('No se encontró el ID de usuario en la sesión.', 'danger')
        return redirect(url_for('login'))

    user = User.query.get(user_id)
    if not user:
        flash('Usuario no encontrado.', 'danger')
        return redirect(url_for('login'))

    avatar_url = None
    if user.avatar_url:
        # Asume que avatar_url es la ruta relativa desde static/
        avatar_url = url_for('static', filename=user.avatar_url)
    
    # current_user_role es necesario para el botón de estadísticas en perfil.html
    current_user_role = session.get('role')

    return render_template('perfil.html', user=user, avatar_url=avatar_url, current_user_role=current_user_role)

@perfil_bp.route('/editar_perfil', methods=['GET', 'POST'])
@role_required(['Superuser', 'Usuario Regular'])
def editar_perfil():
    user_id = session.get('user_id')
    if not user_id:
        flash('No se encontró el ID de usuario en la sesión.', 'danger')
        return redirect(url_for('login'))

    user = db.session.get(User, user_id)
    if not user:
        flash('Usuario no encontrado para editar.', 'danger')
        return redirect(url_for('login'))

    logged_in_user_role = session.get('role') # Obtener el rol del usuario logueado

    if request.method == 'POST':
        user.nombre = request.form['nombre']
        user.primer_apellido = request.form['primer_apellido']
        user.segundo_apellido = request.form.get('segundo_apellido')
        user.telefono = request.form['telefono']
        user.email = request.form['email']
        user.telefono_emergencia = request.form.get('telefono_emergencia')
        user.nombre_emergencia = request.form.get('nombre_emergencia')
        user.direccion = request.form.get('direccion')
        user.cedula = request.form.get('cedula')
        user.empresa = request.form.get('empresa')
        user.tipo_sangre = request.form.get('tipo_sangre')
        user.poliza = request.form.get('poliza')
        user.aseguradora = request.form.get('aseguradora')
        user.alergias = request.form.get('alergias')
        user.enfermedades_cronicas = request.form.get('enfermedades_cronicas')

        # Campos solo editables por Superuser
        if session.get('role') == 'Superuser':
            user.actividad = request.form.get('actividad')
            user.capacidad = request.form.get('capacidad')
            user.participacion = request.form.get('participacion')
            user.role = request.form.get('role') # Permitir cambiar el rol

        fecha_cumpleanos_str = request.form.get('fecha_cumpleanos')
        if fecha_cumpleanos_str:
            try:
                user.fecha_cumpleanos = datetime.strptime(fecha_cumpleanos_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Formato de fecha de cumpleaños inválido. Usa YYYY-MM-DD.', 'danger')
                # Pasa todas las opciones en caso de error
                return render_template('editar_contacto.html', user=user,
                                       actividad_opciones=actividad_opciones,
                                       capacidad_opciones=capacidad_opciones,
                                       participacion_opciones=participacion_opciones,
                                       tipo_sangre_opciones=tipo_sangre_opciones,
                                       provincia_opciones=provincia_opciones,
                                       logged_in_user_role=logged_in_user_role,
                                       role_opciones=role_opciones)

        # Manejo de la subida de avatar
        if 'avatar' in request.files:
            avatar_file = request.files['avatar']
            if avatar_file and avatar_file.filename != '':
                # Generar un nombre de archivo único
                filename = secure_filename(avatar_file.filename)
                unique_filename = str(uuid.uuid4()) + os.path.splitext(filename)[1]
                
                # Definir la ruta de guardado
                upload_folder = current_app.config.get('UPLOAD_FOLDER')
                if not upload_folder:
                    flash('Error de configuración: Carpeta de subida de avatares no definida.', 'danger')
                    # Pasa todas las opciones en caso de error
                    return render_template('editar_contacto.html', user=user,
                                           actividad_opciones=actividad_opciones,
                                           capacidad_opciones=capacidad_opciones,
                                           participacion_opciones=participacion_opciones,
                                           tipo_sangre_opciones=tipo_sangre_opciones,
                                           provincia_opciones=provincia_opciones,
                                           logged_in_user_role=logged_in_user_role,
                                           role_opciones=role_opciones)

                # Asegurarse de que el directorio exista
                os.makedirs(upload_folder, exist_ok=True)
                
                file_path = os.path.join(upload_folder, unique_filename)
                avatar_file.save(file_path)
                
                # Actualizar la URL del avatar en el usuario
                user.avatar_url = os.path.join('uploads', 'avatars', unique_filename).replace('\\', '/') # Ruta relativa para URL

        user.fecha_actualizacion = datetime.utcnow() # Actualizar fecha de actualización

        try:
            db.session.commit()
            flash('Perfil actualizado exitosamente.', 'success')
            # CORRECCIÓN: Cambiado 'perfil.ver_perfil' a 'perfil.perfil'
            return redirect(url_for('perfil.perfil'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar el perfil: {e}', 'danger')
            current_app.logger.error(f"Error al actualizar perfil del usuario {user_id}: {e}")
            # Pasa todas las opciones en caso de error
            return render_template('editar_contacto.html', user=user,
                                   actividad_opciones=actividad_opciones,
                                   capacidad_opciones=capacidad_opciones,
                                   participacion_opciones=participacion_opciones,
                                   tipo_sangre_opciones=tipo_sangre_opciones,
                                   provincia_opciones=provincia_opciones,
                                   logged_in_user_role=logged_in_user_role,
                                   role_opciones=role_opciones)

    # Si es GET request, renderiza el formulario con todas las opciones
    avatar_url = None
    if user.avatar_url:
        with current_app.app_context():
            avatar_url = url_for('static', filename=user.avatar_url)
    else:
        with current_app.app_context():
            avatar_url = url_for('static', filename='images/defaults/default_avatar.png')

    return render_template('editar_contacto.html', user=user, avatar_url=avatar_url,
                           actividad_opciones=actividad_opciones,
                           capacidad_opciones=capacidad_opciones,
                           participacion_opciones=participacion_opciones,
                           tipo_sangre_opciones=tipo_sangre_opciones,
                           provincia_opciones=provincia_opciones,
                           logged_in_user_role=logged_in_user_role,
                           role_opciones=role_opciones)

@perfil_bp.route('/change_password', methods=['GET', 'POST'])
@role_required(['Superuser', 'Usuario Regular'])
def change_password():
    user_id = session.get('user_id')
    if not user_id:
        flash('No se encontró el ID de usuario en la sesión.', 'danger')
        return redirect(url_for('login'))

    user = User.query.get(user_id)
    if not user:
        flash('Usuario no encontrado.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_new_password = request.form.get('confirm_new_password')

        if not old_password or not new_password or not confirm_new_password:
            flash('Todos los campos de contraseña son requeridos.', 'danger')
            return render_template('change_password.html', user=user)

        if not bcrypt.check_password_hash(user.password, old_password):
            flash('Contraseña actual incorrecta.', 'danger')
            return render_template('change_password.html', user=user)

        if new_password != confirm_new_password:
            flash('La nueva contraseña y la confirmación no coinciden.', 'danger')
            return render_template('change_password.html', user=user)

        if len(new_password) < 6:
            flash('La nueva contraseña debe tener al menos 6 caracteres.', 'danger')
            return render_template('change_password.html', user=user)

        try:
            user.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
            db.session.commit()
            flash('Contraseña actualizada exitosamente.', 'success')
            return redirect(url_for('perfil.perfil'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar la contraseña: {e}', 'danger')
            current_app.logger.error(f"Error al cambiar contraseña para el usuario {user_id}: {e}")
            return render_template('change_password.html', user=user)

    return render_template('change_password.html', user=user)


@perfil_bp.route('/manage_backups')
@role_required(['Superuser'])
def manage_backups():
    backup_folder = os.path.join(current_app.root_path, 'backups')
    backups = []
    if os.path.exists(backup_folder):
        for filename in os.listdir(backup_folder):
            if filename.endswith('.db'):
                filepath = os.path.join(backup_folder, filename)
                # Obtener la fecha de modificación del archivo
                mod_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                backups.append({'name': filename, 'date': mod_time})
        # Ordenar los backups por fecha de creación (más reciente primero)
        backups.sort(key=lambda x: x['date'], reverse=True)
    return render_template('manage_backups.html', backups=backups)


@perfil_bp.route('/backup_database', methods=['POST'])
@role_required(['Superuser']) # Solo Superusers pueden hacer backup
def backup_database():
    try:
        # Ruta de la base de datos actual (ahora db.db en la carpeta instance)
        db_path = os.path.join(current_app.instance_path, 'db.db')
        
        # Crear la carpeta de backups si no existe
        backup_folder = os.path.join(current_app.root_path, 'backups')
        os.makedirs(backup_folder, exist_ok=True)

        # Nombre del archivo de backup con marca de tiempo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # CORRECCIÓN: Cambiado el prefijo del nombre del archivo de backup
        backup_filename = f'db_backup_{timestamp}.db' # Nombre de backup refleja 'db.db'
        backup_filepath = os.path.join(backup_folder, backup_filename)

        # Copiar el archivo de la base de datos
        shutil.copyfile(db_path, backup_filepath)

        flash(f'Backup de la base de datos "{backup_filename}" creado exitosamente.', 'success')
        
        # Permitir la descarga directa del backup
        return send_file(backup_filepath, as_attachment=True, download_name=backup_filename)

    except Exception as e:
        flash(f'Error al crear el backup de la base de datos: {e}', 'danger')
        current_app.logger.error(f"Error al crear backup de la base de datos: {e}")
        return redirect(url_for('perfil.perfil'))

@perfil_bp.route('/restore_database', methods=['POST'])
@role_required(['Superuser']) # Solo Superusers pueden restaurar la base de datos
def restore_database():
    # Es altamente recomendable que esta operación se realice con la aplicación detenida
    # o en un entorno de mantenimiento para evitar corrupción de datos.
    # En un entorno de producción, esto requeriría un reinicio del servidor.

    # Obtener la ruta del archivo de backup desde el formulario o parámetro
    backup_filename = request.form.get('backup_filename')
    if not backup_filename:
        flash('No se especificó ningún archivo de backup para restaurar.', 'danger')
        return redirect(url_for('perfil.perfil'))

    backup_folder = os.path.join(current_app.root_path, 'backups')
    backup_filepath = os.path.join(backup_folder, backup_filename)

    # Ruta de la base de datos actual (ahora db.db en la carpeta instance)
    db_path = os.path.join(current_app.instance_path, 'db.db')

    if not os.path.exists(backup_filepath):
        flash(f'El archivo de backup "{backup_filename}" no fue encontrado.', 'danger')
        return redirect(url_for('perfil.perfil'))

    try:
        # Primero, hacer una copia de seguridad de la base de datos actual ANTES de restaurar
        # Esto es una medida de seguridad adicional
        temp_backup_filename = f'pre_restore_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
        temp_backup_filepath = os.path.join(backup_folder, temp_backup_filename)
        if os.path.exists(db_path):
            shutil.copyfile(db_path, temp_backup_filepath)
            flash(f'Se creó una copia de seguridad temporal antes de la restauración: "{temp_backup_filename}".', 'info')

        # Reemplazar la base de datos actual con el archivo de backup
        shutil.copyfile(backup_filepath, db_path)

        flash(f'Base de datos restaurada exitosamente desde "{backup_filename}".', 'success')
        flash('¡IMPORTANTE! Reinicia tu aplicación Flask para que los cambios surtan efecto.', 'warning')
        
    except Exception as e:
        flash(f'Error al restaurar la base de datos: {e}', 'danger')
        current_app.logger.error(f"Error al restaurar base de datos desde {backup_filename}: {e}")

    return redirect(url_for('perfil.perfil'))

@perfil_bp.route('/upload_database', methods=['POST'])
@role_required(['Superuser'])
def upload_database():
    if 'db_file' not in request.files:
        flash('No se encontró el archivo de la base de datos.', 'danger')
        return redirect(url_for('perfil.perfil'))

    db_file = request.files['db_file']

    if db_file.filename == '':
        flash('No se seleccionó ningún archivo.', 'danger')
        return redirect(url_for('perfil.perfil'))

    if db_file and db_file.filename.endswith('.db'):
        try:
            # Ruta de la base de datos actual (db.db en la carpeta instance)
            db_path = os.path.join(current_app.instance_path, 'db.db')

            # Opcional: hacer un backup automático antes de reemplazar
            # Esto es una buena práctica de seguridad
            backup_folder = os.path.join(current_app.root_path, 'backups')
            os.makedirs(backup_folder, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_backup_filename = f'pre_upload_backup_{timestamp}.db'
            temp_backup_filepath = os.path.join(backup_folder, temp_backup_filename)
            if os.path.exists(db_path):
                shutil.copyfile(db_path, temp_backup_filepath)
                flash(f'Se creó una copia de seguridad temporal antes de la subida: "{temp_backup_filename}".', 'info')

            # Guardar el archivo subido como db.db
            db_file.save(db_path)
            flash('Base de datos subida y reemplazada exitosamente.', 'success')
            flash('¡IMPORTANTE! Reinicia tu aplicación Flask para que los cambios surtan efecto.', 'warning')
        except Exception as e:
            flash(f'Error al subir o reemplazar la base de datos: {e}', 'danger')
            current_app.logger.error(f"Error al subir o reemplazar la base de datos: {e}")
    else:
        flash('Tipo de archivo no permitido. Solo se aceptan archivos .db', 'danger')

    return redirect(url_for('perfil.perfil'))

@perfil_bp.route('/dashboard_stats')
@role_required(['Superuser'])
def dashboard_stats():
    """
    Muestra las estadísticas del sitio, incluyendo conteos de caminatas, proyectos, eventos y notas.
    Solo accesible para Superusers.
    """
    site_stats = SiteStats.query.first()
    if not site_stats:
        site_stats = SiteStats(visits=0)
        db.session.add(site_stats)
        db.session.commit()

    total_users = db.session.query(func.count(User.id)).scalar()

    # --- NUEVAS CONSULTAS PARA OBTENER LOS CONTEOS ---
    # Conteo de Caminatas Activas
    # Asume que una caminata es "activa" si su fecha de inicio es en el futuro o hoy
    active_caminatas_count = Caminata.query.filter(Caminata.fecha >= date.today()).count()

    # Conteo total de Proyectos Creados
    total_projects_count = Project.query.count()

    # Conteo total de Eventos de Calendario Creados
    total_calendar_events_count = CalendarEvent.query.count()

    # Conteo total de Notas Creadas
    total_notes_count = Note.query.count()
    # --- FIN DE NUEVAS CONSULTAS ---

    return render_template('admin_dashboard_stats.html',
                           site_stats=site_stats,
                           total_users=total_users,
                           active_caminatas_count=active_caminatas_count,
                           total_projects_count=total_projects_count,
                           total_calendar_events_count=total_calendar_events_count,
                           total_notes_count=total_notes_count)
