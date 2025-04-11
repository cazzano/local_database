from flask import Flask, request, jsonify, send_from_directory, send_file
from werkzeug.utils import secure_filename
import os
import magic
import time
from functools import wraps
import logging
from flask_cors import CORS
import zipfile
import io
import shutil
import threading
import tempfile
import requests
from werkzeug.serving import is_running_from_reloader

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure base upload directory
DB_FOLDER = 'db'
ITEMS_API_URL = 'http://localhost:5000/items'

# Create base directory if it doesn't exist
os.makedirs(DB_FOLDER, exist_ok=True)

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 * 1024  # 100GB max file size
ALLOWED_EXTENSIONS = {
    'image': {'png', 'jpg', 'jpeg', 'gif', 'webp'},
    'video': {'mp4', 'mov', 'avi', 'mkv', 'webm'},
    'audio': {'mp3', 'wav', 'ogg', 'flac'},
    'document': {'pdf', 'doc', 'docx', 'txt', 'rtf'},
    'archive': {'zip', 'rar', '7z', 'tar', 'gz'},
    'code': {'py', 'js', 'html', 'css', 'java', 'cpp', 'c', 'h', 'php'},
    'txt': {'txt'},
    # Add more types as needed
}

# Rate limiting configuration
RATE_LIMIT = 100  # requests
RATE_TIME = 3600  # seconds (1 hour)
request_history = {}

# Backup/Restore configuration
BACKUP_CHUNK_SIZE = 5 * 1024 * 1024  # 5MB chunks for backup streaming
RESTORE_TEMP_DIR = 'restore_temp'
MAX_RETRIES = 3
TIMEOUT = 180  # 3 minutes timeout for operations
active_operations = {}  # Track ongoing backup/restore operations

# Cache for item metadata to reduce API calls
items_cache = {
    'timestamp': 0,
    'data': []
}
CACHE_TTL = 60  # Cache time-to-live in seconds


def fetch_items():
    """Fetch items from the API with caching"""
    current_time = time.time()
    
    # Return cached data if still valid
    if current_time - items_cache['timestamp'] < CACHE_TTL and items_cache['data']:
        return items_cache['data']
    
    try:
        response = requests.get(ITEMS_API_URL, timeout=10)
        if response.status_code == 200:
            items = response.json()
            # Update cache
            items_cache['timestamp'] = current_time
            items_cache['data'] = items
            return items
        else:
            logger.error(f"Failed to fetch items: {response.status_code}")
            # Return cached data if available, even if expired
            if items_cache['data']:
                return items_cache['data']
            return []
    except Exception as e:
        logger.error(f"Error fetching items: {e}")
        # Return cached data if available, even if expired
        if items_cache['data']:
            return items_cache['data']
        return []


def get_item_by_id(item_id):
    """Get item details by ID"""
    items = fetch_items()
    for item in items:
        if item.get('item_id') == item_id:
            return item
    return None


def ensure_directory_exists(category, item_type):
    """Ensure that the directory for a given category and type exists"""
    if not category or not item_type:
        return False
    
    directory = os.path.join(DB_FOLDER, category, item_type)
    os.makedirs(directory, exist_ok=True)
    return directory


def get_file_path(item_id=None, category=None, item_type=None, filename=None):
    """Determine the file path based on item_id or direct category/type/filename"""
    # If item_id is provided, lookup item details
    if item_id is not None:
        item = get_item_by_id(int(item_id))
        if not item:
            return None, "Item not found"
        
        category = item.get('category')
        item_type = item.get('type')
        
        if not category or not item_type:
            return None, "Item missing category or type"
    
    # If direct category/type is provided
    if category and item_type:
        directory = ensure_directory_exists(category, item_type)
        if filename:
            return os.path.join(directory, secure_filename(filename)), None
        return directory, None
    
    return None, "Missing category or type information"


def is_valid_file_type(file, item_type):
    """Validate file type using magic numbers"""
    try:
        mime = magic.from_buffer(file.read(1024), mime=True)
        file.seek(0)  # Reset file pointer

        # Basic mime type validation
        mime_types_map = {
            'image': ['image/'],
            'video': ['video/'],
            'audio': ['audio/'],
            'document': ['application/pdf', 'application/msword', 'application/vnd.openxmlformats', 'text/plain'],
            'archive': ['application/zip', 'application/x-rar', 'application/x-7z', 'application/gzip'],
            'code': ['text/'],
            'txt': ['text/plain'],
            # Add more mappings as needed
        }
        
        valid_mimes = mime_types_map.get(item_type, [])
        if not valid_mimes:  # If no validation defined, allow any file
            return True
            
        return any(mime.startswith(prefix) for prefix in valid_mimes)
    except Exception as e:
        logger.error(f"Error checking file type: {e}")
        return False


def allowed_file(filename, item_type):
    """Check if the file extension is allowed for the given type"""
    if '.' not in filename:
        return False
    
    ext = filename.rsplit('.', 1)[1].lower()
    allowed_exts = ALLOWED_EXTENSIONS.get(item_type)
    
    # If no specific extensions defined for the type, allow any extension
    if allowed_exts is None:
        return True
        
    return ext in allowed_exts


def rate_limit(f):
    """Rate limiting decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ip = request.remote_addr
        current_time = time.time()

        # Clean up old requests
        request_history[ip] = [t for t in request_history.get(ip, [])
                               if current_time - t < RATE_TIME]

        if len(request_history.get(ip, [])) >= RATE_LIMIT:
            return jsonify({'error': 'Rate limit exceeded'}), 429

        request_history.setdefault(ip, []).append(current_time)
        return f(*args, **kwargs)
    return decorated_function


def handle_file_operation(operation, file=None, filename=None, item_id=None, category=None, item_type=None):
    """Common file operation handler with dynamic path support"""
    try:
        if operation == 'list':
            # If category and type are provided, list files in that directory
            if category and item_type:
                directory, error = get_file_path(category=category, item_type=item_type)
                if error:
                    return jsonify({'error': error}), 400
                
                if not os.path.exists(directory):
                    return jsonify([])
                
                files = os.listdir(directory)
                files_with_urls = [{
                    'filename': file,
                    'url': f'/files/{category}/{item_type}/{file}',
                    'size': os.path.getsize(os.path.join(directory, file)),
                    'modified': os.path.getmtime(os.path.join(directory, file))
                } for file in files if os.path.isfile(os.path.join(directory, file))]
                return jsonify(files_with_urls)
            
            # If item_id is provided, get its category and type then list
            elif item_id:
                item = get_item_by_id(int(item_id))
                if not item:
                    return jsonify({'error': 'Item not found'}), 404
                
                directory, error = get_file_path(category=item['category'], item_type=item['type'])
                if error:
                    return jsonify({'error': error}), 400
                
                if not os.path.exists(directory):
                    return jsonify([])
                
                files = os.listdir(directory)
                files_with_urls = [{
                    'filename': file,
                    'url': f'/files/{item["category"]}/{item["type"]}/{file}',
                    'size': os.path.getsize(os.path.join(directory, file)),
                    'modified': os.path.getmtime(os.path.join(directory, file))
                } for file in files if os.path.isfile(os.path.join(directory, file))]
                return jsonify(files_with_urls)
            
            # List all categories and types (directory structure)
            else:
                structure = {}
                if not os.path.exists(DB_FOLDER):
                    return jsonify([])
                
                for category_name in os.listdir(DB_FOLDER):
                    category_path = os.path.join(DB_FOLDER, category_name)
                    if os.path.isdir(category_path):
                        structure[category_name] = []
                        for type_name in os.listdir(category_path):
                            type_path = os.path.join(category_path, type_name)
                            if os.path.isdir(type_path):
                                structure[category_name].append(type_name)
                
                return jsonify(structure)

        elif operation in ['upload', 'update']:
            if not file:
                return jsonify({'error': 'No file provided'}), 400

            original_filename = secure_filename(filename or file.filename)
            if not original_filename:
                return jsonify({'error': 'Invalid filename'}), 400
            
            # Determine file path
            if item_id:
                # Get item details from API
                item = get_item_by_id(int(item_id))
                if not item:
                    return jsonify({'error': 'Item not found'}), 404
                
                category = item.get('category')
                item_type = item.get('type')
            
            # Validate file type and extension
            if not allowed_file(original_filename, item_type):
                return jsonify({'error': f'File extension not allowed for type {item_type}'}), 400

            if not is_valid_file_type(file, item_type):
                return jsonify({'error': 'Invalid file content for specified type'}), 400
            
            # Get the path where the file should be saved
            file_path, error = get_file_path(
                category=category,
                item_type=item_type,
                filename=original_filename
            )
            
            if error:
                return jsonify({'error': error}), 400
            
            # Save the file
            file.save(file_path)

            return jsonify({
                'message': f'File {"updated" if operation == "update" else "uploaded"} successfully',
                'url': f'/files/{category}/{item_type}/{original_filename}'
            }), 200 if operation == 'update' else 201

        elif operation == 'delete':
            # Handle deletion by filename
            if filename:
                # Determine file path
                if item_id:
                    # Get item details from API
                    item = get_item_by_id(int(item_id))
                    if not item:
                        return jsonify({'error': 'Item not found'}), 404
                    
                    category = item.get('category')
                    item_type = item.get('type')
                
                file_path, error = get_file_path(
                    category=category,
                    item_type=item_type,
                    filename=secure_filename(filename)
                )
                
                if error:
                    return jsonify({'error': error}), 400
                
                if not os.path.exists(file_path):
                    return jsonify({'error': 'File not found'}), 404

                os.remove(file_path)
                return jsonify({'message': 'File deleted successfully'}), 200
            
            # Handle deletion of all files for an item
            elif item_id:
                # Get item details from API
                item = get_item_by_id(int(item_id))
                if not item:
                    return jsonify({'error': 'Item not found'}), 404
                
                directory, error = get_file_path(
                    category=item.get('category'),
                    item_type=item.get('type')
                )
                
                if error:
                    return jsonify({'error': error}), 400
                
                # Get all files in the directory
                if not os.path.exists(directory):
                    return jsonify({'error': f'No files found for item_id {item_id}'}), 404
                
                files = os.listdir(directory)
                deleted_files = []
                
                # Iterate through files to find those belonging to this item
                # You may need to define a naming convention or metadata to associate files with items
                for file in files:
                    file_path = os.path.join(directory, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        deleted_files.append(file)
                
                if not deleted_files:
                    return jsonify({'error': f'No files found for item_id {item_id}'}), 404
                
                return jsonify({
                    'message': 'Files deleted successfully',
                    'deleted_files': deleted_files
                }), 200
            else:
                return jsonify({'error': 'Neither filename nor item_id provided'}), 400

    except Exception as e:
        logger.error(f"Error in file operation: {e}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


# File serving route
@app.route('/files/<category>/<item_type>/<filename>')
@rate_limit
def serve_file(category, item_type, filename):
    directory = os.path.join(DB_FOLDER, category, item_type)
    if not os.path.exists(directory):
        return jsonify({'error': 'Directory not found'}), 404
    
    response = send_from_directory(directory, secure_filename(filename))
    response.headers['Cache-Control'] = 'public, max-age=3600'  # 1 hour cache
    return response


# Main file operations endpoint
@app.route('/files', methods=['GET', 'POST', 'DELETE', 'PUT'])
@rate_limit
def handle_files():
    item_id = request.args.get('item_id')
    category = request.args.get('category')
    item_type = request.args.get('type')
    filename = request.args.get('filename')
    
    if request.method == 'GET':
        return handle_file_operation('list', item_id=item_id, category=category, item_type=item_type)

    elif request.method == 'POST':
        return handle_file_operation(
            'upload',
            file=request.files.get('file'),
            filename=filename,
            item_id=item_id,
            category=category,
            item_type=item_type
        )

    elif request.method == 'DELETE':
        return handle_file_operation(
            'delete',
            filename=filename,
            item_id=item_id,
            category=category,
            item_type=item_type
        )

    elif request.method == 'PUT':
        return handle_file_operation(
            'update',
            file=request.files.get('file'),
            filename=filename,
            item_id=item_id,
            category=category,
            item_type=item_type
        )


# Backward compatibility routes for existing code
@app.route('/pictures', methods=['GET', 'POST', 'DELETE', 'PUT'])
@rate_limit
def handle_pictures():
    """Legacy endpoint for pictures - maps to image type"""
    item_id = request.args.get('item_id')
    book_id = request.args.get('book_id')  # For backward compatibility
    filename = request.args.get('filename')
    
    # Use book_id as item_id if provided (for backward compatibility)
    if book_id and not item_id:
        item_id = book_id
    
    if request.method == 'GET':
        # For backward compatibility, list all image files across categories
        all_images = []
        if os.path.exists(DB_FOLDER):
            for category in os.listdir(DB_FOLDER):
                category_path = os.path.join(DB_FOLDER, category)
                if os.path.isdir(category_path) and os.path.exists(os.path.join(category_path, 'image')):
                    image_path = os.path.join(category_path, 'image')
                    files = os.listdir(image_path)
                    files_info = [{
                        'filename': file,
                        'url': f'/files/{category}/image/{file}',
                        'size': os.path.getsize(os.path.join(image_path, file)),
                        'modified': os.path.getmtime(os.path.join(image_path, file))
                    } for file in files if os.path.isfile(os.path.join(image_path, file))]
                    all_images.extend(files_info)
        return jsonify(all_images)

    elif request.method == 'POST':
        if item_id:
            return handle_file_operation(
                'upload',
                file=request.files.get('file'),
                filename=filename,
                item_id=item_id
            )
        else:
            # Default category/type for backward compatibility
            return handle_file_operation(
                'upload',
                file=request.files.get('file'),
                filename=filename,
                category='Default',
                item_type='image'
            )

    elif request.method == 'DELETE':
        if item_id:
            return handle_file_operation(
                'delete',
                filename=filename,
                item_id=item_id
            )
        else:
            # For backward compatibility, try to find the file in any image directory
            if not filename:
                return jsonify({'error': 'No filename provided'}), 400
            
            secure_name = secure_filename(filename)
            deleted = False
            
            for category in os.listdir(DB_FOLDER):
                category_path = os.path.join(DB_FOLDER, category)
                if os.path.isdir(category_path) and os.path.exists(os.path.join(category_path, 'image')):
                    file_path = os.path.join(category_path, 'image', secure_name)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        deleted = True
                        break
            
            if deleted:
                return jsonify({'message': 'File deleted successfully'}), 200
            else:
                return jsonify({'error': 'File not found'}), 404

    elif request.method == 'PUT':
        if item_id:
            return handle_file_operation(
                'update',
                file=request.files.get('file'),
                filename=filename,
                item_id=item_id
            )
        else:
            # Default category/type for backward compatibility
            return handle_file_operation(
                'update',
                file=request.files.get('file'),
                filename=filename,
                category='Default',
                item_type='image'
            )


@app.route('/downloads', methods=['GET', 'POST', 'DELETE', 'PUT'])
@rate_limit
def handle_downloads():
    """Legacy endpoint for downloads - maps to document type"""
    item_id = request.args.get('item_id')
    book_id = request.args.get('book_id')  # For backward compatibility
    filename = request.args.get('filename')
    
    # Use book_id as item_id if provided (for backward compatibility)
    if book_id and not item_id:
        item_id = book_id
    
    if request.method == 'GET':
        # For backward compatibility, list all document files across categories
        all_documents = []
        if os.path.exists(DB_FOLDER):
            for category in os.listdir(DB_FOLDER):
                category_path = os.path.join(DB_FOLDER, category)
                if os.path.isdir(category_path):
                    for doc_type in ['document', 'archive', 'txt']:
                        doc_path = os.path.join(category_path, doc_type)
                        if os.path.exists(doc_path):
                            files = os.listdir(doc_path)
                            files_info = [{
                                'filename': file,
                                'url': f'/files/{category}/{doc_type}/{file}',
                                'size': os.path.getsize(os.path.join(doc_path, file)),
                                'modified': os.path.getmtime(os.path.join(doc_path, file))
                            } for file in files if os.path.isfile(os.path.join(doc_path, file))]
                            all_documents.extend(files_info)
        return jsonify(all_documents)

    elif request.method == 'POST':
        if item_id:
            return handle_file_operation(
                'upload',
                file=request.files.get('file'),
                filename=filename,
                item_id=item_id
            )
        else:
            # Determine the document type based on file extension
            file = request.files.get('file')
            if not file:
                return jsonify({'error': 'No file provided'}), 400
                
            original_filename = secure_filename(filename or file.filename)
            if not original_filename:
                return jsonify({'error': 'Invalid filename'}), 400
                
            ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
            
            if ext in ALLOWED_EXTENSIONS['archive']:
                item_type = 'archive'
            elif ext in ALLOWED_EXTENSIONS['document']:
                item_type = 'document'
            elif ext in ALLOWED_EXTENSIONS['txt']:
                item_type = 'txt'
            else:
                item_type = 'document'  # Default
                
            return handle_file_operation(
                'upload',
                file=file,
                filename=original_filename,
                category='Default',
                item_type=item_type
            )

    elif request.method == 'DELETE':
        if item_id:
            return handle_file_operation(
                'delete',
                filename=filename,
                item_id=item_id
            )
        else:
            # For backward compatibility, try to find the file in any document directory
            if not filename:
                return jsonify({'error': 'No filename provided'}), 400
            
            secure_name = secure_filename(filename)
            deleted = False
            
            for category in os.listdir(DB_FOLDER):
                category_path = os.path.join(DB_FOLDER, category)
                if not os.path.isdir(category_path):
                    continue
                    
                for doc_type in ['document', 'archive', 'txt']:
                    doc_path = os.path.join(category_path, doc_type)
                    if os.path.exists(doc_path):
                        file_path = os.path.join(doc_path, secure_name)
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            deleted = True
                            break
                if deleted:
                    break
            
            if deleted:
                return jsonify({'message': 'File deleted successfully'}), 200
            else:
                return jsonify({'error': 'File not found'}), 404

    elif request.method == 'PUT':
        if item_id:
            return handle_file_operation(
                'update',
                file=request.files.get('file'),
                filename=filename,
                item_id=item_id
            )
        else:
            # Determine the document type based on file extension
            file = request.files.get('file')
            if not file:
                return jsonify({'error': 'No file provided'}), 400
                
            original_filename = secure_filename(filename or file.filename)
            if not original_filename:
                return jsonify({'error': 'Invalid filename'}), 400
                
            ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
            
            if ext in ALLOWED_EXTENSIONS['archive']:
                item_type = 'archive'
            elif ext in ALLOWED_EXTENSIONS['document']:
                item_type = 'document'
            elif ext in ALLOWED_EXTENSIONS['txt']:
                item_type = 'txt'
            else:
                item_type = 'document'  # Default
                
            return handle_file_operation(
                'update',
                file=file,
                filename=original_filename,
                category='Default',
                item_type=item_type
            )


# Enhanced Backup Endpoint
@app.route('/backup', methods=['GET'])
@rate_limit
def backup_db():
    """Create a zip file containing all files in the db directory with support for slow connections"""
    try:
        # Check if client wants to stream the backup or start an async operation
        stream_mode = request.args.get('stream', 'true').lower() == 'true'

        if stream_mode:
            # Original streaming approach
            memory_file = io.BytesIO()

            with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(DB_FOLDER):
                    for file in files:
                        file_path = os.path.join(root, file)
                        zf.write(file_path, arcname=file_path)

            memory_file.seek(0)

            response = send_file(
                memory_file,
                mimetype='application/zip',
                as_attachment=True,
                download_name='db_backup.zip'
            )
            # Set timeout and chunked transfer encoding
            response.headers['Transfer-Encoding'] = 'chunked'
            return response
        else:
            # Async approach for slow connections
            operation_id = generate_operation_id()
            active_operations[operation_id] = {
                'type': 'backup',
                'status': 'in_progress',
                'start_time': time.time()
            }

            # Start backup process in a separate thread
            thread = threading.Thread(
                target=create_backup_archive,
                args=(operation_id,)
            )
            thread.daemon = True
            thread.start()

            return jsonify({
                'message': 'Backup operation started',
                'operation_id': operation_id,
                'status_url': f'/operation/{operation_id}'
            }), 202

    except Exception as e:
        logger.error(f"Error initiating backup: {e}")
        return jsonify({'error': f'Failed to create backup: {str(e)}'}), 500


# Enhanced Restore Endpoint
@app.route('/restore', methods=['POST'])
@rate_limit
def restore_db():
    """Restore db folder from a zip file with support for slow connections"""
    try:
        # Check for chunk mode or full upload
        chunk_mode = request.args.get('chunk', 'false').lower() == 'true'
        operation_id = request.args.get('operation_id')

        # Full file upload (may fail with slow connections)
        if not chunk_mode:
            if 'file' not in request.files:
                return jsonify({'error': 'No file provided'}), 400

            file = request.files['file']
            if not file.filename.endswith('.zip'):
                return jsonify({'error': 'File must be a zip archive'}), 400

            # Create a new operation
            operation_id = generate_operation_id()
            active_operations[operation_id] = {
                'type': 'restore',
                'status': 'in_progress',
                'start_time': time.time()
            }

            # Save the uploaded file to a temporary location
            temp_path = os.path.join(
                tempfile.gettempdir(), f'restore_{operation_id}.zip')
            file.save(temp_path)

            # Process the restore in a separate thread
            thread = threading.Thread(
                target=process_restore_archive,
                args=(operation_id, temp_path)
            )
            thread.daemon = True
            thread.start()

            return jsonify({
                'message': 'Restore operation started',
                'operation_id': operation_id,
                'status_url': f'/operation/{operation_id}'
            }), 202

        # Chunked upload handling
        else:
            # Ensure we have an operation ID
            if not operation_id:
                # Start a new chunked upload
                operation_id = generate_operation_id()
                chunk_dir = os.path.join(
                    tempfile.gettempdir(), f'restore_chunks_{operation_id}')
                os.makedirs(chunk_dir, exist_ok=True)

                active_operations[operation_id] = {
                    'type': 'restore_chunked',
                    'status': 'receiving_chunks',
                    'start_time': time.time(),
                    'chunk_dir': chunk_dir,
                    'chunks_received': 0,
                    'total_chunks': int(request.headers.get('X-Total-Chunks', '0'))
                }

                return jsonify({
                    'message': 'Chunked restore initialized',
                    'operation_id': operation_id,
                    'status_url': f'/operation/{operation_id}'
                }), 202

            # Process an existing chunked upload
            if operation_id not in active_operations:
                return jsonify({'error': 'Invalid operation ID'}), 400

            # Get operation info
            op_info = active_operations[operation_id]

            # Handle chunk upload
            if 'file' not in request.files:
                return jsonify({'error': 'No chunk provided'}), 400

            chunk = request.files['file']
            chunk_number = int(request.args.get('chunk_number', '0'))
            chunk_path = os.path.join(
                op_info['chunk_dir'], f'chunk_{chunk_number}')

            # Save the chunk
            chunk.save(chunk_path)
            op_info['chunks_received'] += 1


# Check if all chunks received
                if op_info['chunks_received'] >= op_info['total_chunks']:
                    # Combine chunks
                    combined_path = os.path.join(
                        tempfile.gettempdir(), f'restore_{operation_id}.zip')
                    with open(combined_path, 'wb') as outfile:
                        for i in range(op_info['total_chunks']):
                            chunk_path = os.path.join(
                                op_info['chunk_dir'], f'chunk_{i}')
                            with open(chunk_path, 'rb') as infile:
                                outfile.write(infile.read())

                    # Update status
                    op_info['status'] = 'processing'

                    # Process the combined file
                    thread = threading.Thread(
                        target=process_restore_archive,
                        args=(operation_id, combined_path)
                    )
                    thread.daemon = True
                    thread.start()

                    # Clean up chunk directory
                    shutil.rmtree(op_info['chunk_dir'], ignore_errors=True)

                    return jsonify({
                        'message': 'All chunks received, processing restore',
                        'operation_id': operation_id,
                        'status_url': f'/operation/{operation_id}'
                    }), 200

                # Not all chunks received yet
                return jsonify({
                    'message': f'Chunk {chunk_number} received',
                    'operation_id': operation_id,
                    'chunks_received': op_info['chunks_received'],
                    'total_chunks': op_info['total_chunks']
                }), 200

    except Exception as e:
        logger.error(f"Error in restore operation: {e}")
        return jsonify({'error': f'Failed to restore: {str(e)}'}), 500


# Operation Status Endpoint
@app.route('/operation/<operation_id>', methods=['GET'])
@rate_limit
def operation_status(operation_id):
    """Check the status of a backup or restore operation"""
    if operation_id not in active_operations:
        return jsonify({'error': 'Operation not found'}), 404

    op_info = active_operations[operation_id]

    # If operation is completed and it's a backup, return the file
    if op_info['type'] == 'backup' and op_info['status'] == 'completed' and request.args.get('download', 'false').lower() == 'true':
        if os.path.exists(op_info['file_path']):
            return send_file(
                op_info['file_path'],
                mimetype='application/zip',
                as_attachment=True,
                download_name='db_backup.zip'
            )

    # Return the operation status
    result = {
        'operation_id': operation_id,
        'type': op_info['type'],
        'status': op_info['status'],
        'start_time': op_info['start_time'],
        'elapsed_time': time.time() - op_info['start_time']
    }

    # Add operation-specific information
    if op_info['type'] == 'restore_chunked' and op_info['status'] == 'receiving_chunks':
        result.update({
            'chunks_received': op_info['chunks_received'],
            'total_chunks': op_info['total_chunks'],
            'progress': (op_info['chunks_received'] / op_info['total_chunks']) * 100 if op_info['total_chunks'] > 0 else 0
        })

    # Add error information if available
    if 'error' in op_info:
        result['error'] = op_info['error']

    # Clean up completed operations after some time
    if op_info['status'] in ['completed', 'failed'] and (time.time() - op_info['start_time']) > 3600:
        # Remove temporary files
        if op_info['type'] == 'backup' and 'file_path' in op_info and os.path.exists(op_info['file_path']):
            os.remove(op_info['file_path'])

        # Schedule for removal from active_operations
        # We don't remove it immediately to allow the client to check the status
        def cleanup_operation():
            if operation_id in active_operations:
                del active_operations[operation_id]

        # Remove after 5 minutes
        threading.Timer(300, cleanup_operation).start()

    return jsonify(result)


# Helper Functions from the original code
def generate_operation_id():
    """Generate a unique operation ID"""
    return str(int(time.time() * 1000))


def create_backup_archive(operation_id):
    """Create a zip archive of the db directory"""
    try:
        # Path for the backup file
        backup_path = os.path.join(
            tempfile.gettempdir(), f'db_backup_{operation_id}.zip')

        # Create the zip file
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Walk through all directories in the db folder
            for root, dirs, files in os.walk(DB_FOLDER):
                for file in files:
                    # Get the full file path
                    file_path = os.path.join(root, file)
                    # Add file to zip with its relative path
                    zf.write(file_path, arcname=file_path)

        # Update operation status
        active_operations[operation_id]['status'] = 'completed'
        active_operations[operation_id]['file_path'] = backup_path

        logger.info(f"Backup {operation_id} completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error creating backup {operation_id}: {e}")
        active_operations[operation_id]['status'] = 'failed'
        active_operations[operation_id]['error'] = str(e)
        return False


def process_restore_archive(operation_id, zip_path):
    """Process a restore operation from a zip file"""
    try:
        # Create a backup of the current db folder first
        backup_folder = f'db_backup_before_restore_{operation_id}'
        if os.path.exists(backup_folder):
            shutil.rmtree(backup_folder)

        # Backup current structure if it exists
        if os.path.exists(DB_FOLDER):
            shutil.copytree(DB_FOLDER, backup_folder)

            # Empty the current db folder without deleting the folder structure
            for root, dirs, files in os.walk(DB_FOLDER):
                for f in files:
                    os.remove(os.path.join(root, f))

        # Extract the zip file to the db folder
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.namelist():
                # Only extract files that start with 'db/'
                if member.startswith(f'{DB_FOLDER}/'):
                    zip_ref.extract(member, '.')

        # Update operation status
        active_operations[operation_id]['status'] = 'completed'

        # Clean up temporary files
        if os.path.exists(zip_path):
            os.remove(zip_path)

        logger.info(f"Restore {operation_id} completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error restoring backup {operation_id}: {e}")
        active_operations[operation_id]['status'] = 'failed'
        active_operations[operation_id]['error'] = str(e)

        # Try to restore from backup if something went wrong
        try:
            if os.path.exists(backup_folder):
                if os.path.exists(DB_FOLDER):
                    shutil.rmtree(DB_FOLDER)
                shutil.copytree(backup_folder, DB_FOLDER)
        except Exception as restore_error:
            logger.error(f"Error restoring from backup: {restore_error}")

        return False


# Add a new endpoint to rebuild/sync the directory structure from API
@app.route('/sync-structure', methods=['POST'])
@rate_limit
def sync_structure():
    """Sync the file structure with the items from the API"""
    try:
        # Get all items from the API
        items = fetch_items()
        if not items:
            return jsonify({'error': 'Failed to fetch items from API'}), 500

        # Create directories for each category/type
        created_dirs = []
        for item in items:
            category = item.get('category')
            item_type = item.get('type')

            if category and item_type:
                directory = ensure_directory_exists(category, item_type)
                created_dirs.append(f"{category}/{item_type}")

        return jsonify({
            'message': 'Directory structure synced successfully',
            'created_directories': created_dirs
        }), 200
    except Exception as e:
        logger.error(f"Error syncing directory structure: {e}")
        return jsonify({'error': f'Failed to sync structure: {str(e)}'}), 500


# Cleanup function that used to be @app.before_first_request
def cleanup_temp_files():
    """Clean up any temporary files from previous runs"""
    if not is_running_from_reloader():
        temp_dir = tempfile.gettempdir()
        for filename in os.listdir(temp_dir):
            if filename.startswith(('db_backup_', 'restore_')):
                try:
                    file_path = os.path.join(temp_dir, filename)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path, ignore_errors=True)
                except Exception as e:
                    logger.error(
                        f"Error cleaning up temp file {filename}: {e}")


# Execute the cleanup function at startup
with app.app_context():
    cleanup_temp_files()


# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(413)
def too_large_error(error):
    return jsonify({'error': 'File too large'}), 413


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    app.run(debug=False, port=3000)  # Set debug=False for production
