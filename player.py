# player.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
import os
from functools import wraps
import re

# --- INICIO DE LA CORRECCIÓN: DECORADOR DE ROL DEFINIDO LOCALMENTE ---

def role_required(roles):
    """
    Decorador para restringir el acceso a rutas basadas en roles.
    `roles` puede ser una cadena (un solo rol) o una lista de cadenas (múltiples roles).
    Esta es una copia local para evitar la importación circular desde app.py.
    """
    if not isinstance(roles, list):
        roles = [roles]

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'logged_in' not in session or not session['logged_in']:
                flash('Por favor, inicia sesión para acceder a esta página.', 'info')
                # Redirige a la página de inicio de sesión general
                return redirect(url_for('login'))
            
            user_role = session.get('role')
            if user_role not in roles:
                flash('No tienes permiso para acceder a esta página.', 'danger')
                # Redirige al reproductor si no tiene permiso
                return redirect(url_for('player.show_player')) 
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- FIN DE LA CORRECCIÓN ---


# Configuración de la carpeta para subir archivos.
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'ogg', 'jpg', 'jpeg', 'png', 'gif'}
ALLOWED_MUSIC_EXTENSIONS = {'mp3', 'wav', 'ogg'}
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif'}

# Crea un Blueprint para las rutas relacionadas con el reproductor
player_bp = Blueprint('player', __name__)

def allowed_file(filename):
    """Verifica si la extensión del archivo es permitida (para imágenes y música)."""
    if hasattr(current_app, 'allowed_file'):
        return current_app.allowed_file(filename)
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_music_file(filename):
    """Verifica si la extensión del archivo de música es permitida."""
    if hasattr(current_app, 'allowed_music_file'):
        return current_app.allowed_music_file(filename)
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_MUSIC_EXTENSIONS

def allowed_image_file(filename):
    """Verifica si la extensión del archivo de imagen es permitida."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def is_valid_filename(filename):
    """
    Valida si el nombre del archivo contiene caracteres especiales no permitidos.
    """
    invalid_chars_pattern = r'[#<>!$%&/=?¡\'"¿°|]'
    if re.search(invalid_chars_pattern, filename):
        return False
    return True

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

@player_bp.route('/player', methods=['GET'])
def show_player():
    """
    Ruta para mostrar la vista principal del reproductor de música.
    """
    from models import db, Song, Playlist, User

    songs_obj = Song.query.all()
    playlists_obj = Playlist.query.all()

    songs = []
    for song in songs_obj:
        normalized_file_path = song.file_path
        if normalized_file_path:
            normalized_file_path = normalized_file_path.replace(os.sep, '/')
            if normalized_file_path.startswith('static/'):
                normalized_file_path = normalized_file_path[len('static/'):]

        normalized_cover_path = song.cover_image_path
        if normalized_cover_path:
            normalized_cover_path = normalized_cover_path.replace(os.sep, '/')
            if normalized_cover_path.startswith('static/'):
                normalized_cover_path = normalized_cover_path[len('static/'):]

        song_data = {
            'id': song.id,
            'title': song.title,
            'artist': song.artist,
            'album': song.album,
            'file_path': url_for('static', filename=normalized_file_path) if normalized_file_path else None,
            'cover_image_path': url_for('static', filename=normalized_cover_path) if normalized_cover_path else None
        }
        songs.append(song_data)

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
    return render_template('ver_player.html', songs=songs, playlists=playlists, user_role=user_role, user_email=user_email)

# --- Rutas y lógica para la gestión de canciones ---

@player_bp.route('/player/upload_song', methods=['POST'])
@role_required('Superuser')
def upload_song():
    """
    Ruta para subir una nueva canción y su carátula.
    Solo accesible por Superusuarios.
    """
    from models import db, Song

    title = request.form.get('title')
    artist = request.form.get('artist')
    album = request.form.get('album')
    audio_file = request.files.get('file')
    cover_image_file = request.files.get('cover_image')

    if not title or not audio_file or audio_file.filename == '':
        flash('El título y el archivo de audio son obligatorios.', 'danger')
        return redirect(url_for('player.show_player'))

    if not is_valid_filename(audio_file.filename):
        flash('El nombre del archivo de audio contiene caracteres no permitidos.', 'danger')
        return redirect(url_for('player.show_player'))

    if not allowed_music_file(audio_file.filename):
        flash('Formato de archivo de audio no permitido.', 'danger')
        return redirect(url_for('player.show_player'))

    filename = generate_unique_filename(audio_file.filename, current_app.config['SONGS_UPLOAD_FOLDER'])
    audio_save_path = os.path.join(current_app.config['SONGS_UPLOAD_FOLDER'], filename)
    os.makedirs(current_app.config['SONGS_UPLOAD_FOLDER'], exist_ok=True)
    audio_file.save(audio_save_path)
    file_path_db = os.path.join('uploads', 'songs', filename).replace(os.sep, '/')

    cover_image_path_db = None
    if cover_image_file and cover_image_file.filename != '':
        if not is_valid_filename(cover_image_file.filename):
            flash('El nombre del archivo de carátula contiene caracteres no permitidos.', 'danger')
            return redirect(url_for('player.show_player'))
        if allowed_image_file(cover_image_file.filename):
            cover_filename = generate_unique_filename(cover_image_file.filename, current_app.config['COVERS_UPLOAD_FOLDER'])
            cover_save_path = os.path.join(current_app.config['COVERS_UPLOAD_FOLDER'], cover_filename)
            os.makedirs(current_app.config['COVERS_UPLOAD_FOLDER'], exist_ok=True)
            cover_image_file.save(cover_save_path)
            cover_image_path_db = os.path.join('uploads', 'covers', cover_filename).replace(os.sep, '/')
        else:
            flash('Formato de archivo de carátula no permitido.', 'danger')
            return redirect(url_for('player.show_player'))

    try:
        new_song = Song(
            title=title, 
            artist=artist, 
            album=album, 
            file_path=file_path_db,
            cover_image_path=cover_image_path_db
        )
        db.session.add(new_song)
        db.session.commit()
        flash(f'Canción "{title}" subida con éxito!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al subir la canción: {e}', 'danger')
        current_app.logger.error(f"Error al subir canción: {e}")
    return redirect(url_for('player.show_player'))


@player_bp.route('/player/delete_song/<int:song_id>', methods=['POST'])
@role_required('Superuser')
def delete_song(song_id):
    """
    Ruta para eliminar una canción.
    Solo accesible por Superusuarios.
    """
    from models import db, Song

    song = Song.query.get_or_404(song_id)
    try:
        if song.file_path:
            full_audio_path = os.path.join(current_app.root_path, 'static', song.file_path.replace('/', os.sep))
            if os.path.exists(full_audio_path):
                os.remove(full_audio_path)

        if song.cover_image_path:
            full_cover_path = os.path.join(current_app.root_path, 'static', song.cover_image_path.replace('/', os.sep))
            if os.path.exists(full_cover_path):
                os.remove(full_cover_path)

        db.session.delete(song)
        db.session.commit()
        flash(f'Canción "{song.title}" eliminada con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar la canción: {e}', 'danger')
        current_app.logger.error(f"Error al eliminar canción: {e}")
    return redirect(url_for('player.show_player'))


@player_bp.route('/player/change_cover/<int:song_id>', methods=['POST'])
@role_required('Superuser')
def change_cover(song_id):
    """
    Ruta para cambiar la carátula de una canción.
    Solo accesible por Superusuarios.
    """
    from models import db, Song

    song = Song.query.get_or_404(song_id)
    new_cover_image_file = request.files.get('new_cover_image')

    if not new_cover_image_file or new_cover_image_file.filename == '':
        flash('No se seleccionó un nuevo archivo de carátula.', 'danger')
        return redirect(url_for('player.show_player'))

    if not is_valid_filename(new_cover_image_file.filename):
        flash('El nombre del archivo de carátula contiene caracteres no permitidos.', 'danger')
        return redirect(url_for('player.show_player'))

    if not allowed_image_file(new_cover_image_file.filename):
        flash('Formato de archivo de carátula no permitido.', 'danger')
        return redirect(url_for('player.show_player'))

    # Eliminar la carátula antigua si existe
    if song.cover_image_path:
        old_cover_full_path = os.path.join(current_app.root_path, 'static', song.cover_image_path.replace('/', os.sep))
        if os.path.exists(old_cover_full_path):
            os.remove(old_cover_full_path)

    # Guardar la nueva carátula
    cover_filename = generate_unique_filename(new_cover_image_file.filename, current_app.config['COVERS_UPLOAD_FOLDER'])
    cover_save_path = os.path.join(current_app.config['COVERS_UPLOAD_FOLDER'], cover_filename)
    os.makedirs(current_app.config['COVERS_UPLOAD_FOLDER'], exist_ok=True)
    new_cover_image_file.save(cover_save_path)
    new_cover_path_db = os.path.join('uploads', 'covers', cover_filename).replace(os.sep, '/')

    try:
        song.cover_image_path = new_cover_path_db
        db.session.commit()
        flash(f'Carátula de "{song.title}" actualizada con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cambiar la carátula: {e}', 'danger')
        current_app.logger.error(f"Error al cambiar carátula: {e}")
    
    return redirect(url_for('player.show_player'))


@player_bp.route('/player/delete_cover/<int:song_id>', methods=['POST'])
@role_required('Superuser')
def delete_cover(song_id):
    """
    Ruta para eliminar la carátula de una canción.
    Solo accesible por Superusuarios.
    """
    from models import db, Song

    song = Song.query.get_or_404(song_id)
    try:
        if song.cover_image_path:
            full_cover_path = os.path.join(current_app.root_path, 'static', song.cover_image_path.replace('/', os.sep))
            if os.path.exists(full_cover_path):
                os.remove(full_cover_path)
            song.cover_image_path = None
            db.session.commit()
            flash(f'Carátula de "{song.title}" eliminada con éxito.', 'success')
        else:
            flash(f'La canción "{song.title}" no tenía una carátula para eliminar.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar la carátula: {e}', 'danger')
        current_app.logger.error(f"Error al eliminar carátula: {e}")
    return redirect(url_for('player.show_player'))


@player_bp.route('/player/get_available_covers', methods=['GET'])
@role_required('Superuser')
def get_available_covers():
    """
    Retorna una lista de rutas de archivos de carátula disponibles en el servidor.
    """
    covers_folder = current_app.config['COVERS_UPLOAD_FOLDER']
    available_covers = []
    if os.path.exists(covers_folder):
        for filename in os.listdir(covers_folder):
            if allowed_image_file(filename):
                relative_path = os.path.join('uploads', 'covers', filename).replace(os.sep, '/')
                available_covers.append(url_for('static', filename=relative_path))
    return jsonify({'covers': available_covers})


@player_bp.route('/player/apply_cover_to_all', methods=['POST'])
@role_required('Superuser')
def apply_cover_to_all():
    """
    Aplica una carátula seleccionada a todas las demás canciones.
    Solo accesible por Superusuarios.
    """
    from models import db, Song

    cover_path_to_apply = request.form.get('cover_path')
    
    if not cover_path_to_apply:
        flash('Por favor, selecciona una carátula para aplicar.', 'danger')
        return redirect(url_for('player.show_player'))

    if cover_path_to_apply.startswith(url_for('static', filename='')):
        cover_path_to_apply = cover_path_to_apply[len(url_for('static', filename='')):]

    try:
        all_songs = Song.query.all()
        for song in all_songs:
            song.cover_image_path = cover_path_to_apply
        db.session.commit()
        flash('La carátula seleccionada ha sido aplicada a todas las canciones con éxito.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al aplicar la carátula a todas las canciones: {e}', 'danger')
        current_app.logger.error(f"Error al aplicar carátula a todas las canciones: {e}")
    
    return redirect(url_for('player.show_player'))
