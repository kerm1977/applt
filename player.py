# player.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify # Importar current_app y jsonify
import os
# from werkzeug.utils import secure_filename # COMENTADO: Ya no usaremos secure_filename directamente
from functools import wraps # Necesario para el decorador
import re # NUEVO: Importar re para expresiones regulares

# Configuración de la carpeta para subir archivos.
# NOTA: Estas variables UPLOAD_FOLDER, ALLOWED_EXTENSIONS, etc.
# serán sobrescritas/complementadas por las configuraciones de app.py
# a través de current_app.
# Las mantenemos aquí por si este Blueprint se usara de forma independiente,
# pero la lógica principal usará las de current_app.
UPLOAD_FOLDER = 'static/uploads' # Carpeta general, pero usaremos las específicas de app.py
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'ogg', 'jpg', 'jpeg', 'png', 'gif'}
ALLOWED_MUSIC_EXTENSIONS = {'mp3', 'wav', 'ogg'} # Definido también en app.py
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif'} # NUEVO: Para carátulas

# Crea un Blueprint para las rutas relacionadas con el reproductor
player_bp = Blueprint('player', __name__)

def allowed_file(filename):
    """Verifica si la extensión del archivo es permitida (para imágenes y música)."""
    # Usar las extensiones permitidas definidas en app.py si están disponibles
    if hasattr(current_app, 'allowed_file'):
        return current_app.allowed_file(filename)
    # Fallback si no está definida en current_app (menos probable con su setup)
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_music_file(filename):
    """Verifica si la extensión del archivo de música es permitida."""
    # Usar las extensiones de música permitidas definidas en app.py si están disponibles
    if hasattr(current_app, 'allowed_music_file'):
        return current_app.allowed_music_file(filename)
    # Fallback si no está definida en current_app
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_MUSIC_EXTENSIONS

def allowed_image_file(filename):
    """Verifica si la extensión del archivo de imagen es permitida."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

# NUEVO: Función para validar caracteres especiales en el nombre del archivo
def is_valid_filename(filename):
    """
    Valida si el nombre del archivo contiene caracteres especiales no permitidos.
    Caracteres no permitidos: #<>!$%&/=?¡'"¿°|
    """
    invalid_chars_pattern = r'[#<>!$%&/=?¡\'"¿°|]'
    if re.search(invalid_chars_pattern, filename):
        return False
    return True

# NUEVO: Función para generar un nombre de archivo único
def generate_unique_filename(original_filename, upload_folder):
    """
    Genera un nombre de archivo único, manteniendo el nombre original si es posible,
    o añadiendo un número consecutivo si ya existe.
    """
    filename_base, extension = os.path.splitext(original_filename)
    counter = 1
    unique_filename = original_filename
    while os.path.exists(os.path.join(upload_folder, unique_filename)):
        unique_filename = f"{filename_base}_{counter}{extension}"
        counter += 1
    return unique_filename


# Decorador para restringir el acceso por email
def email_required(f):
    """
    Decorador para restringir el acceso a rutas basadas en correos electrónicos específicos.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        allowed_emails = ['kenth1977@gmail.com', 'jceciliano69@gmail.com']
        user_email = session.get('email') # Leer el email de la sesión usando la clave 'email'

        if user_email not in allowed_emails:
            flash('Acceso denegado. Solo usuarios autorizados pueden realizar esta acción.', 'danger')
            return redirect(url_for('player.show_player'))
        return f(*args, **kwargs)
    return decorated_function

@player_bp.route('/player', methods=['GET'])
def show_player():
    """
    Ruta para mostrar la vista principal del reproductor de música.
    Aquí es donde ver_player.html será renderizado.
    """
    # Mover la importación de modelos dentro de la función para evitar NameError
    from models import db, Song, Playlist, User

    songs_obj = Song.query.all()
    playlists_obj = Playlist.query.all()

    songs = []
    for song in songs_obj:
        # Normalizar la ruta del archivo de audio para url_for (asegurar '/')
        normalized_file_path = song.file_path
        if normalized_file_path:
            normalized_file_path = normalized_file_path.replace(os.sep, '/') # Reemplazar \ con /
            if normalized_file_path.startswith('static/'):
                normalized_file_path = normalized_file_path[len('static/'):]

        # Normalizar la ruta de la carátula para url_for (asegurar '/')
        normalized_cover_path = song.cover_image_path
        if normalized_cover_path:
            normalized_cover_path = normalized_cover_path.replace(os.sep, '/') # Reemplazar \ con /
            if normalized_cover_path.startswith('static/'):
                normalized_cover_path = normalized_cover_path[len('static/'):]

        song_data = {
            'id': song.id,
            'title': song.title,
            'artist': song.artist,
            'album': song.album,
            # Generar la URL usando url_for con la ruta normalizada
            'file_path': url_for('static', filename=normalized_file_path) if normalized_file_path else None,
            'cover_image_path': url_for('static', filename=normalized_cover_path) if normalized_cover_path else None
        }
        songs.append(song_data)
    
    # DEBUG: Imprime los datos de las canciones que se envían al frontend
    # print(f"DEBUG: Songs data sent to frontend: {songs}") # COMENTADO para reducir ruido en la consola

    playlists = []
    for playlist in playlists_obj:
        playlist_songs = []
        for song in playlist.songs:
            playlist_songs.append({
                'id': song.id,
                'title': song.title,
            })
        playlists.append({
            'id': playlist.id,
            'name': playlist.name,
            'songs': playlist_songs
        })

    user_role = session.get('role')
    user_email = session.get('email')
    print(f"User Email from session: {user_email}")
    return render_template('ver_player.html', songs=songs, playlists=playlists, user_role=user_role, user_email=user_email)

# --- Rutas y lógica para la gestión de canciones y listas de reproducción ---

@player_bp.route('/player/upload_song', methods=['GET', 'POST'])
@email_required
def upload_song():
    """
    Ruta para subir una nueva canción y su carátula.
    Solo accesible por usuarios con emails específicos.
    """
    # Mover la importación de modelos dentro de la función
    from models import db, Song

    if request.method == 'POST':
        title = request.form.get('title')
        artist = request.form.get('artist')
        album = request.form.get('album')

        audio_file = request.files.get('file')
        file_path_db = None # Ruta que se guardará en la base de datos

        # Usar current_app.config['SONGS_UPLOAD_FOLDER'] para guardar el archivo de audio
        if audio_file and audio_file.filename != '':
            # NUEVO: Validar caracteres en el nombre del archivo de audio
            if not is_valid_filename(audio_file.filename):
                flash('El nombre del archivo de audio contiene caracteres especiales no permitidos (#, <, >, !, $, %, &, /, =, ?, ¡, \', ", ¿, °, |). Por favor, renombra el archivo.', 'danger')
                return redirect(url_for('player.show_player'))

            if allowed_music_file(audio_file.filename):
                # NUEVO: Usar generate_unique_filename
                filename = generate_unique_filename(audio_file.filename, current_app.config['SONGS_UPLOAD_FOLDER'])
                # CORREGIDO: Usar current_app.config
                audio_save_path = os.path.join(current_app.config['SONGS_UPLOAD_FOLDER'], filename)
                os.makedirs(current_app.config['SONGS_UPLOAD_FOLDER'], exist_ok=True) # Asegurarse de que la carpeta exista
                audio_file.save(audio_save_path)
                # Guardar la ruta relativa a 'static/' para la DB (ej. 'uploads/songs/nombre.mp3')
                # Asegurar que la ruta guardada en la DB use '/'
                file_path_db = os.path.join('uploads', 'songs', filename).replace(os.sep, '/')
            else:
                flash('El archivo de audio no es compatible. Formatos permitidos: MP3, WAV, OGG.', 'danger')
                return redirect(url_for('player.show_player'))
        else:
            flash('El archivo de audio es obligatorio.', 'danger')
            return redirect(url_for('player.show_player'))

        cover_image_file = request.files.get('cover_image')
        cover_image_path_db = None # Ruta que se guardará en la base de datos

        # Usar current_app.config['COVERS_UPLOAD_FOLDER'] para guardar la carátula
        if cover_image_file and cover_image_file.filename != '':
            # NUEVO: Validar caracteres en el nombre del archivo de carátula
            if not is_valid_filename(cover_image_file.filename):
                flash('El nombre del archivo de carátula contiene caracteres especiales no permitidos (#, <, >, !, $, %, &, /, =, ?, ¡, \', ", ¿, °, |). Por favor, renombra el archivo.', 'danger')
                return redirect(url_for('player.show_player'))

            if allowed_file(cover_image_file.filename): # allowed_file verifica extensiones de imagen
                # NUEVO: Usar generate_unique_filename
                cover_filename = generate_unique_filename(cover_image_file.filename, current_app.config['COVERS_UPLOAD_FOLDER'])
                # CORREGIDO: Usar current_app.config
                cover_save_path = os.path.join(current_app.config['COVERS_UPLOAD_FOLDER'], cover_filename)
                os.makedirs(current_app.config['COVERS_UPLOAD_FOLDER'], exist_ok=True) # Asegurarse de que la carpeta exista
                cover_image_file.save(cover_save_path)
                # Guardar la ruta relativa a 'static/' para la DB (ej. 'uploads/covers/imagen.jpg')
                # Asegurar que la ruta guardada en la DB use '/'
                cover_image_path_db = os.path.join('uploads', 'covers', cover_filename).replace(os.sep, '/')
            else:
                flash('El archivo de carátula no es compatible. Formatos permitidos: JPG, JPEG, PNG, GIF.', 'danger')
                return redirect(url_for('player.show_player'))
        # NOTA: Si no se sube carátula, cover_image_path_db seguirá siendo None, lo cual es correcto.

        if not title:
            flash('El título es obligatorio.', 'danger')
            return redirect(url_for('player.show_player'))

        try:
            new_song = Song(title=title, artist=artist, album=album, 
                            file_path=file_path_db, # Usar la ruta para la DB
                            cover_image_path=cover_image_path_db) # Usar la ruta para la DB
            db.session.add(new_song)
            db.session.commit()
            flash(f'Canción "{title}" subida con éxito!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al subir la canción: {e}', 'danger')
            current_app.logger.error(f"Error al subir canción: {e}") # Para depuración
        return redirect(url_for('player.show_player'))
    return redirect(url_for('player.show_player'))

@player_bp.route('/player/delete_song/<int:song_id>', methods=['POST'])
@email_required
def delete_song(song_id):
    """
    Ruta para eliminar una canción.
    Solo accesible por usuarios con emails específicos.
    """
    # Mover la importación de modelos dentro de la función
    from models import db, Song

    song = Song.query.get_or_404(song_id)
    try:
        # Eliminar el archivo de audio físico
        if song.file_path:
            # Construir la ruta absoluta para el sistema de archivos (usar os.sep)
            full_audio_path = os.path.join(current_app.root_path, 'static', song.file_path.replace('/', os.sep))
            if os.path.exists(full_audio_path):
                os.remove(full_audio_path)
                print(f"Archivo de audio eliminado: {full_audio_path}")
            else:
                print(f"Advertencia: Archivo de audio no encontrado para eliminar: {full_audio_path}")

        # Eliminar el archivo de carátula físico
        if song.cover_image_path:
            # Construir la ruta absoluta para el sistema de archivos (usar os.sep)
            full_cover_path = os.path.join(current_app.root_path, 'static', song.cover_image_path.replace('/', os.sep))
            if os.path.exists(full_cover_path):
                os.remove(full_cover_path)
                print(f"Archivo de carátula eliminado: {full_cover_path}")
            else:
                print(f"Advertencia: Archivo de carátula no encontrado para eliminar: {full_cover_path}")

        db.session.delete(song)
        db.session.commit()
        flash(f'Canción "{song.title}" eliminada con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar la canción: {e}', 'danger')
        current_app.logger.error(f"Error al eliminar canción: {e}") # Para depuración
    return redirect(url_for('player.show_player'))

@player_bp.route('/player/rename_song/<int:song_id>', methods=['POST'])
# No se especificó restricción para renombrar, pero si desea, aplique @email_required
def rename_song(song_id):
    """
    Ruta para renombrar una canción.
    """
    # Mover la importación de modelos dentro de la función
    from models import db, Song

    song = Song.query.get_or_404(song_id)
    new_title = request.form.get('new_title')
    if new_title:
        try:
            song.title = new_title
            db.session.commit()
            flash(f'Canción renombrada a "{new_title}" con éxito.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al renombrar la canción: {e}', 'danger')
    else:
        flash('El nuevo título no puede estar vacío.', 'danger')
    return redirect(url_for('player.show_player'))

@player_bp.route('/player/create_playlist', methods=['POST'])
# No se especificó restricción para crear playlist, pero si desea, aplique @email_required
def create_playlist():
    """
    Ruta para crear una nueva lista de reproducción.
    """
    # Mover la importación de modelos dentro de la función
    from models import db, Playlist

    playlist_name = request.form.get('playlist_name')
    if playlist_name:
        try:
            new_playlist = Playlist(name=playlist_name)
            db.session.add(new_playlist)
            db.session.commit()
            flash(f'Lista de reproducción "{playlist_name}" creada con éxito.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear la lista de reproducción: {e}', 'danger')
    else:
        flash('El nombre de la lista de reproducción no puede estar vacío.', 'danger')
    return redirect(url_for('player.show_player'))

@player_bp.route('/player/delete_playlist/<int:playlist_id>', methods=['POST'])
# No se especificó restricción para eliminar playlist, pero si desea, aplique @email_required
def delete_playlist(playlist_id):
    """
    Ruta para eliminar una lista de reproducción.
    """
    # Mover la importación de modelos dentro de la función
    from models import db, Playlist

    playlist = Playlist.query.get_or_404(playlist_id)
    try:
        db.session.delete(playlist)
        db.session.commit()
        flash(f'Lista de reproducción "{playlist.name}" eliminada con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar la lista de reproducción: {e}', 'danger')
    return redirect(url_for('player.show_player'))

# Rutas para la carátula
@player_bp.route('/player/change_cover/<int:song_id>', methods=['POST'])
@email_required
def change_cover(song_id):
    """
    Ruta para cambiar la carátula de una canción.
    Solo accesible por usuarios con emails específicos.
    """
    # Mover la importación de modelos dentro de la función
    from models import db, Song

    song = Song.query.get_or_404(song_id)
    new_cover_image_file = request.files.get('new_cover_image')
    new_cover_path_db = None # Ruta que se guardará en la base de datos

    # Usar current_app.config['COVERS_UPLOAD_FOLDER'] para guardar la nueva carátula
    if new_cover_image_file and new_cover_image_file.filename != '':
        # NUEVO: Validar caracteres en el nombre del archivo de carátula
        if not is_valid_filename(new_cover_image_file.filename):
            flash('El nombre del archivo de carátula contiene caracteres especiales no permitidos (#, <, >, !, $, %, &, /, =, ?, ¡, \', ", ¿, °, |). Por favor, renombra el archivo.', 'danger')
            return redirect(url_for('player.show_player'))

        if allowed_file(new_cover_image_file.filename): # allowed_file verifica extensiones de imagen
            # NUEVO: Usar generate_unique_filename
            cover_filename = generate_unique_filename(new_cover_image_file.filename, current_app.config['COVERS_UPLOAD_FOLDER'])
            # CORREGIDO: Usar current_app.config
            cover_save_path = os.path.join(current_app.config['COVERS_UPLOAD_FOLDER'], cover_filename)
            os.makedirs(current_app.config['COVERS_UPLOAD_FOLDER'], exist_ok=True) # Asegurarse de que la carpeta exista
            new_cover_image_file.save(cover_save_path)
            # Guardar la ruta relativa a 'static/' para la DB (ej. 'uploads/covers/imagen.jpg')
            # Asegurar que la ruta guardada en la DB use '/'
            new_cover_path_db = os.path.join('uploads', 'covers', cover_filename).replace(os.sep, '/')
        else:
            flash('El archivo de carátula no es compatible. Formatos permitidos: JPG, JPEG, PNG, GIF.', 'danger')
            return redirect(url_for('player.show_player'))
    
    if new_cover_path_db: # Si se subió un nuevo archivo de carátula
        try:
            # Eliminar la carátula antigua si existe
            if song.cover_image_path:
                old_cover_full_path = os.path.join(current_app.root_path, 'static', song.cover_image_path.replace('/', os.sep))
                if os.path.exists(old_cover_full_path):
                    os.remove(old_cover_full_path)
                    print(f"Carátula antigua eliminada: {old_cover_full_path}")
                else:
                    print(f"Advertencia: Carátula antigua no encontrada para eliminar: {old_cover_full_path}")

            song.cover_image_path = new_cover_path_db # Actualizar la ruta en la DB
            db.session.commit()
            flash(f'Carátula de "{song.title}" actualizada con éxito.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al cambiar la carátula: {e}', 'danger')
            current_app.logger.error(f"Error al cambiar carátula: {e}") # Para depuración
    else:
        flash('No se seleccionó un nuevo archivo de carátula o el formato no es compatible.', 'danger')
    return redirect(url_for('player.show_player'))

@player_bp.route('/player/edit_cover/<int:song_id>', methods=['POST'])
@email_required
def edit_cover(song_id):
    """
    Ruta para editar la carátula de una canción (placeholder).
    Solo accesible por usuarios con emails específicos.
    """
    flash('Funcionalidad de editar carátula aún no implementada en detalle. Por favor, usa "Cambiar Carátula" para reemplazarla.', 'info')
    return redirect(url_for('player.show_player'))

@player_bp.route('/player/delete_cover/<int:song_id>', methods=['POST'])
@email_required
def delete_cover(song_id):
    """
    Ruta para eliminar la carátula de una canción.
    Solo accesible por usuarios con emails específicos.
    """
    # Mover la importación de modelos dentro de la función
    from models import db, Song

    song = Song.query.get_or_404(song_id)
    try:
        if song.cover_image_path:
            full_cover_path = os.path.join(current_app.root_path, 'static', song.cover_image_path.replace('/', os.sep))
            if os.path.exists(full_cover_path):
                os.remove(full_cover_path)
                print(f"Carátula eliminada: {full_cover_path}")
            else:
                print(f"Advertencia: Carátula no encontrada para eliminar: {full_cover_path}")

        song.cover_image_path = None # Establece la ruta de la carátula a nula en la DB
        db.session.commit()
        flash(f'Carátula de "{song.title}" eliminada con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar la carátula: {e}', 'danger')
        current_app.logger.error(f"Error al eliminar carátula: {e}") # Para depuración
    return redirect(url_for('player.show_player'))

# NUEVA RUTA: Para obtener la lista de carátulas disponibles
@player_bp.route('/player/get_available_covers', methods=['GET'])
@email_required
def get_available_covers():
    """
    Retorna una lista de rutas de archivos de carátula disponibles en el servidor.
    """
    covers_folder = current_app.config['COVERS_UPLOAD_FOLDER']
    available_covers = []
    if os.path.exists(covers_folder):
        for filename in os.listdir(covers_folder):
            if allowed_image_file(filename):
                # Construir la ruta relativa a 'static/'
                relative_path = os.path.join('uploads', 'covers', filename).replace(os.sep, '/')
                available_covers.append(url_for('static', filename=relative_path))
    return jsonify({'covers': available_covers})


@player_bp.route('/player/apply_cover_to_all', methods=['POST'])
@email_required
def apply_cover_to_all():
    """
    Aplica una carátula seleccionada (por su ruta) a todas las demás canciones.
    Solo accesible por usuarios con emails específicos.
    """
    from models import db, Song

    # Ahora esperamos la ruta de la carátula directamente
    cover_path_to_apply = request.form.get('cover_path')
    
    if not cover_path_to_apply:
        flash('Por favor, selecciona una carátula para aplicar.', 'danger')
        return redirect(url_for('player.show_player'))

    # Eliminar el prefijo '/static/' si existe para que coincida con lo que se guarda en la DB
    if cover_path_to_apply.startswith('/static/'):
        cover_path_to_apply = cover_path_to_apply[len('/static/'):]

    try:
        # Actualizar todas las canciones con esta carátula
        all_songs = Song.query.all()

        for song in all_songs:
            # Opcional: Si quieres eliminar las carátulas antiguas de las otras canciones antes de aplicar la nueva
            # Esto es un poco más complejo si la carátula antigua es compartida por otras canciones.
            # Por ahora, simplemente sobrescribiremos la referencia en la DB.
            song.cover_image_path = cover_path_to_apply
            db.session.add(song) # Re-añadir para asegurar que el ORM detecte el cambio

        db.session.commit()
        flash(f'La carátula seleccionada ha sido aplicada a todas las canciones con éxito.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error al aplicar la carátula a todas las canciones: {e}', 'danger')
        current_app.logger.error(f"Error al aplicar carátula a todas las canciones: {e}")
    
    return redirect(url_for('player.show_player'))
