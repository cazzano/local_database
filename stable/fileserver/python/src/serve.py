from flask import send_from_directory, abort, Response
import os
import mimetypes
import zipfile
from io import BytesIO
import pathlib

def get_mimetype(file_path):
    """Get MIME type for a file"""
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or 'application/octet-stream'

def setup_file_serving(app, base_dir='db'):
    """Setup routes for serving files from the database directory"""
    
    @app.route('/files/download/<path:file_path>', methods=['GET'])
    def download_file(file_path):
        """Serve a specific file for download"""
        try:
            # Sanitize the path to prevent directory traversal attacks
            safe_path = os.path.normpath(file_path)
            if safe_path.startswith('..'):
                abort(403)  # Forbidden
                
            full_path = os.path.join(base_dir, safe_path)
            
            # Check if the file exists
            if not os.path.isfile(full_path):
                abort(404)  # Not found
                
            directory = os.path.dirname(full_path)
            filename = os.path.basename(full_path)
            
            # Get the mime type for the file
            mime_type = get_mimetype(full_path)
            
            return send_from_directory(
                directory, 
                filename, 
                as_attachment=True,
                mimetype=mime_type
            )
        except Exception as e:
            return {"error": str(e)}, 500
    
    @app.route('/files/view/<path:file_path>', methods=['GET'])
    def view_file(file_path):
        """Serve a specific file for viewing in browser"""
        try:
            # Properly handle the file path
            # Sanitize the path to prevent directory traversal attacks
            safe_path = os.path.normpath(file_path)
            if safe_path.startswith('..'):
                abort(403)  # Forbidden
                
            full_path = os.path.join(base_dir, safe_path)
            
            # Check if the file exists
            if not os.path.isfile(full_path):
                abort(404, f"File not found: {full_path}")  # Not found with details
                
            # Get the directory and filename separately
            directory = os.path.dirname(full_path)
            filename = os.path.basename(full_path)
            
            # Get the mime type for the file
            mime_type = get_mimetype(full_path)
            
            # Use send_from_directory with absolute path
            return send_from_directory(
                directory, 
                filename, 
                as_attachment=False,
                mimetype=mime_type
            )
        except Exception as e:
            return {"error": str(e)}, 500
    
    @app.route('/files/download-folder/<path:folder_path>', methods=['GET'])
    def download_folder(folder_path):
        """Create and download a zip archive of a folder"""
        try:
            # Sanitize the path to prevent directory traversal attacks
            safe_path = os.path.normpath(folder_path)
            if safe_path.startswith('..'):
                abort(403)  # Forbidden
                
            full_path = os.path.join(base_dir, safe_path)
            
            # Check if the folder exists
            if not os.path.isdir(full_path):
                abort(404)  # Not found
                
            # Create a BytesIO object to store the zip file
            memory_file = BytesIO()
            
            with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Walk through the directory
                for root, dirs, files in os.walk(full_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # Calculate the relative path from the requested folder
                        arcname = os.path.relpath(file_path, full_path)
                        zipf.write(file_path, arcname)
            
            # Reset the file pointer to the beginning
            memory_file.seek(0)
            
            # Determine the zip file name (use the folder name)
            folder_name = os.path.basename(full_path)
            zip_filename = f"{folder_name}.zip"
            
            return Response(
                memory_file.getvalue(),
                mimetype='application/zip',
                headers={
                    'Content-Disposition': f'attachment; filename={zip_filename}'
                }
            )
        except Exception as e:
            return {"error": str(e)}, 500
    
    @app.route('/files/browse', methods=['GET'])
    @app.route('/files/browse/<path:folder_path>', methods=['GET'])
    def browse_files(folder_path=''):
        """Browse files and folders in the database directory"""
        try:
            # Sanitize the path to prevent directory traversal attacks
            safe_path = os.path.normpath(folder_path)
            if safe_path.startswith('..'):
                abort(403)  # Forbidden
                
            full_path = os.path.join(base_dir, safe_path)
            
            # Check if the path exists
            if not os.path.exists(full_path):
                abort(404, f"Path not found: {full_path}")  # Not found with details
                
            if os.path.isfile(full_path):
                # If it's a file, redirect to view_file
                return view_file(folder_path)
                
            # If it's a directory, list the contents
            items = []
            
            # Add parent directory link (if not at root)
            if folder_path:
                parent_path = os.path.dirname(folder_path)
                items.append({
                    "name": "..",  # Parent directory
                    "path": parent_path,
                    "type": "directory",
                    "size": 0,
                    "is_parent": True
                })
            
            # List all files and directories
            for item in os.listdir(full_path):
                item_path = os.path.join(full_path, item)
                rel_path = os.path.join(folder_path, item) if folder_path else item
                
                item_info = {
                    "name": item,
                    "path": rel_path,
                    "type": "directory" if os.path.isdir(item_path) else "file",
                    "size": os.path.getsize(item_path) if os.path.isfile(item_path) else 0,
                    "is_parent": False
                }
                
                # Add file extension for files
                if os.path.isfile(item_path):
                    item_info["extension"] = os.path.splitext(item)[1][1:].lower()
                    item_info["mimetype"] = get_mimetype(item_path)
                
                items.append(item_info)
            
            # Sort items by type (directories first) and then by name
            items.sort(key=lambda x: (0 if x.get("is_parent") else (1 if x["type"] == "directory" else 2), x["name"]))
            
            return {
                "current_path": folder_path,
                "items": items,
                "total": len(items)
            }
        except Exception as e:
            return {"error": str(e)}, 500
