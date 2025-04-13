from flask import Flask, request, jsonify, render_template
import os
import requests
import json
import re
import tarfile
import shutil
from io import BytesIO
from datetime import datetime
from difflib import SequenceMatcher
from serve import setup_file_serving
from auto_rename import rename_file_based_on_item_details
from upload_folder import process_folder_upload

app = Flask(__name__)

# Base directory to store uploaded files
UPLOAD_FOLDER = 'db'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# API endpoint for items
API_BASE_URL = 'http://localhost:5000/items'
API_STATIC_URL = 'http://localhost:5000/items/static'

# URL prepath for file viewing
FILE_VIEW_PREPATH = 'http://localhost:3000/files/view/'

def get_item_details(item_id):
    """Fetch item details from the API based on item ID"""
    try:
        response = requests.get(f"{API_BASE_URL}/{item_id}")
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except requests.RequestException:
        return None

def get_all_items():
    """Function to get all available items from the API"""
    try:
        response = requests.get(API_BASE_URL)
        if response.status_code == 200:
            # Convert the list of items to a dictionary with item_id as key
            items_list = response.json()
            items_dict = {item['item_id']: item for item in items_list}
            return items_dict
        else:
            return {}
    except requests.RequestException:
        return {}

def get_all_static_resources():
    """Function to get all static resources from the API"""
    try:
        response = requests.get(API_STATIC_URL)
        if response.status_code == 200:
            # Convert the list to a dictionary with item_id as key
            static_list = response.json()
            static_dict = {item['item_id']: item for item in static_list}
            return static_dict
        else:
            return {}
    except requests.RequestException:
        return {}

def calculate_filename_similarity(filename, item_name):
    """Calculate similarity between filename and item name"""
    # Remove file extension and convert to lowercase
    filename_base = os.path.splitext(filename)[0].lower()
    item_name_lower = item_name.lower()
    
    # Calculate similarity ratio
    return SequenceMatcher(None, filename_base, item_name_lower).ratio()

def predict_item_id(file_path, file_name, items_dict, static_resources):
    """
    Enhanced prediction of item_id based on multiple factors:
    1. Check if file path matches any stored static resource paths
    2. Match based on category, type, and name similarity
    3. Use filename pattern matching if available
    """
    # First check if the file path is already registered in static resources
    for item_id, resource in static_resources.items():
        resource_path = resource.get('item_path')
        if resource_path:
            # Strip the prepath if it exists in the stored path
            if resource_path.startswith(FILE_VIEW_PREPATH):
                resource_path = resource_path[len(FILE_VIEW_PREPATH):]
            
            if file_path in resource_path:
                return item_id
    
    # Parse path components
    path_parts = file_path.split(os.sep)
    if len(path_parts) < 2:
        return None
    
    category = path_parts[0]
    file_type = path_parts[1]
    
    # Filter items by category and type
    candidates = []
    for item_id, item in items_dict.items():
        if item.get('category') == category and item.get('type') == file_type:
            # Calculate name similarity
            similarity = calculate_filename_similarity(file_name, item.get('name', ''))
            
            # Extract item_id from filename if it matches pattern like "item_123" or "123_something"
            id_in_filename = None
            filename_base = os.path.splitext(file_name)[0]
            
            # Try to extract item_id from filename using common patterns
            id_patterns = [
                r'item[_-]?(\d+)',  # matches "item_123", "item-123", "item123"
                r'(\d+)[_-]',        # matches "123_something", "123-something"
                r'^(\d+)$'           # matches just the number itself
            ]
            
            for pattern in id_patterns:
                match = re.search(pattern, filename_base)
                if match:
                    try:
                        id_in_filename = int(match.group(1))
                        # If we found an ID that matches an actual item_id, give it high priority
                        if id_in_filename == item_id:
                            similarity += 0.5  # Boost similarity for ID match
                    except ValueError:
                        pass
            
            # Check item details for additional clues
            details = item.get('details', '')
            if details and isinstance(details, str):
                # If details contain any portion of the filename or vice versa
                if file_name.lower() in details.lower() or any(part.lower() in file_name.lower() for part in details.lower().split()):
                    similarity += 0.3  # Boost for details match
            
            candidates.append((item_id, similarity))
    
    # Sort candidates by similarity score
    candidates.sort(key=lambda x: x[1], reverse=True)
    
    # Return the item_id with highest similarity if we have candidates
    if candidates:
        return candidates[0][0]
    
    return None

@app.route('/items/<int:item_id>', methods=['GET'])
def get_items(item_id):
    """Mock API endpoint to return item details based on ID"""
    # In a real scenario, this would directly call the external API
    # We'll keep it here for demonstration purposes
    items = get_all_items()
    
    if item_id in items:
        return jsonify(items[item_id])
    else:
        return jsonify({"error": "Item not found"}), 404

@app.route('/upload/<int:item_id>', methods=['POST'])
def upload_file(item_id):
    """Upload file for a specific item ID"""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    # Get item details from the API
    item_details = get_item_details(item_id)
    
    if not item_details:
        return jsonify({"error": f"Could not get details for item ID: {item_id}"}), 404
    
    # Extract category and type from item details
    category = item_details.get('category')
    file_type = item_details.get('type')
    
    if not category or not file_type:
        return jsonify({"error": "Invalid item details: missing category or type"}), 400
    
    # Create directory structure
    dir_path = os.path.join(UPLOAD_FOLDER, category, file_type)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    
    # Save the file with original name first
    original_file_path = os.path.join(dir_path, file.filename)
    file.save(original_file_path)
    
    # Rename the file according to item details name
    renamed_file_path = rename_file_based_on_item_details(original_file_path, item_details)
    
    # Get the new relative path after renaming
    relative_path = os.path.relpath(renamed_file_path, UPLOAD_FOLDER)
    
    try:
        # Append prepath to the relative path
        static_resource_path = f"{FILE_VIEW_PREPATH}{relative_path}"
        
        # Record the file path in the static resources
        static_resource = {
            "item_path": static_resource_path
        }
        requests.put(f"{API_STATIC_URL}/update/{item_id}", json=static_resource)
    except requests.RequestException as e:
        # Log the error but continue since the file is already saved
        print(f"Failed to update static resource: {e}")
    
    return jsonify({
        "success": True,
        "message": f"File uploaded and renamed successfully for item {item_id}",
        "original_filename": file.filename,
        "new_filename": os.path.basename(renamed_file_path),
        "path": renamed_file_path,
        "static_path": f"{FILE_VIEW_PREPATH}{relative_path}",
        "item_details": item_details
    })

@app.route('/upload-folder/<int:item_id>', methods=['POST'])
def upload_folder(item_id):
    """Upload a folder for a specific item ID"""
    # Check if it's a ZIP upload
    if 'zip_file' in request.files:
        zip_file = request.files['zip_file']
        if zip_file.filename == '':
            return jsonify({"error": "No selected ZIP file"}), 400
        
        # Get item details from the API
        item_details = get_item_details(item_id)
        
        # Process the folder upload
        result, status_code = process_folder_upload(
            {'zip_file': zip_file}, 
            item_id, 
            UPLOAD_FOLDER, 
            item_details, 
            API_STATIC_URL, 
            FILE_VIEW_PREPATH
        )
        
        return jsonify(result), status_code
    
    # Check if it's a directory upload with multiple files
    elif request.files.getlist('folder_files'):
        folder_files = request.files.getlist('folder_files')
        if not folder_files or len(folder_files) == 0:
            return jsonify({"error": "No folder files uploaded"}), 400
        
        # Get item details from the API
        item_details = get_item_details(item_id)
        
        # Process the folder upload
        result, status_code = process_folder_upload(
            {'folder_files': folder_files}, 
            item_id, 
            UPLOAD_FOLDER, 
            item_details, 
            API_STATIC_URL, 
            FILE_VIEW_PREPATH
        )
        
        return jsonify(result), status_code
    else:
        return jsonify({"error": "No folder or ZIP file provided"}), 400

@app.route('/upload-folder-direct/<int:item_id>', methods=['POST'])
def upload_folder_direct(item_id):
    """Upload a folder directly using curl with tar streaming"""
    # Get item details from the API
    item_details = get_item_details(item_id)
    if not item_details:
        return jsonify({"error": f"Could not get details for item ID: {item_id}"}), 404
    
    # Extract category and type from item details
    category = item_details.get('category')
    file_type = item_details.get('type')
    
    if not category or not file_type:
        return jsonify({"error": "Invalid item details: missing category or type"}), 400
    
    # Create base directory structure
    base_dir_path = os.path.join(UPLOAD_FOLDER, category, file_type)
    if not os.path.exists(base_dir_path):
        os.makedirs(base_dir_path)
    
    # Create a unique subfolder for this upload (using timestamp)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    item_name = item_details.get('name', '').replace(' ', '_').lower()
    folder_name = f"{item_name}_{item_id}_{timestamp}"
    folder_path = os.path.join(base_dir_path, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    
    try:
        # Create a temporary directory to extract files first
        temp_extract_dir = os.path.join(base_dir_path, f"temp_{timestamp}")
        os.makedirs(temp_extract_dir, exist_ok=True)
        
        # Open tar stream from request data
        tar_stream = BytesIO(request.data)
        tar = tarfile.open(fileobj=tar_stream, mode='r|*')  # Auto-detect compression
        
        # Extract all files to temporary directory
        tar.extractall(path=temp_extract_dir)
        tar.close()
        
        # Find the actual target folder in the extracted content
        # We assume the last directory in the path is the one we want to keep
        # For example, from "/home/cazzano/starter", we want just "starter"
        uploaded_files = []
        source_folders = []
        
        # Scan the temp directory to find all top-level directories
        for item in os.listdir(temp_extract_dir):
            item_path = os.path.join(temp_extract_dir, item)
            if os.path.isdir(item_path):
                source_folders.append(item_path)
        
        # If we have exactly one top-level directory, assume it's the source folder
        if len(source_folders) == 1:
            source_dir = source_folders[0]
            
            # Now find the actual target folder by traversing the directory structure
            current_dir = source_dir
            found_target = False
            
            # Keep traversing until we find a directory with multiple files/subdirectories
            # or reach a leaf directory
            while not found_target:
                contents = os.listdir(current_dir)
                
                # If there's only one subdirectory and no files, continue traversing
                if len(contents) == 1:
                    next_item = os.path.join(current_dir, contents[0])
                    if os.path.isdir(next_item):
                        current_dir = next_item
                    else:
                        # Hit a file, use the parent directory
                        found_target = True
                else:
                    # Found a directory with multiple items or no items
                    found_target = True
            
            # Move the contents of the final target directory to our destination
            for item in os.listdir(current_dir):
                src_path = os.path.join(current_dir, item)
                dest_path = os.path.join(folder_path, item)
                
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dest_path)
                else:
                    shutil.copy2(src_path, dest_path)
        else:
            # If we have multiple or no top-level directories, just copy everything
            for item in os.listdir(temp_extract_dir):
                src_path = os.path.join(temp_extract_dir, item)
                dest_path = os.path.join(folder_path, item)
                
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dest_path)
                else:
                    shutil.copy2(src_path, dest_path)
        
        # Clean up temporary directory
        shutil.rmtree(temp_extract_dir)
        
        # Track uploaded files and update static resources
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, UPLOAD_FOLDER)
                
                # Update static resource
                try:
                    static_resource_path = f"{FILE_VIEW_PREPATH}{relative_path}"
                    static_resource = {
                        "item_path": static_resource_path
                    }
                    response = requests.put(f"{API_STATIC_URL}/update/{item_id}", json=static_resource)
                    success = response.status_code == 200
                except requests.RequestException:
                    success = False
                
                uploaded_files.append({
                    "file_path": relative_path,
                    "static_path": static_resource_path if success else None,
                    "updated": success
                })
        
        return jsonify({
            "success": True,
            "message": f"Folder uploaded successfully for item {item_id}",
            "folder_path": os.path.relpath(folder_path, UPLOAD_FOLDER),
            "files": uploaded_files,
            "files_count": len(uploaded_files),
            "item_details": item_details
        })
    
    except Exception as e:
        # Clean up temporary directory if it exists
        temp_extract_dir = os.path.join(base_dir_path, f"temp_{timestamp}")
        if os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir)
            
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "Failed to process uploaded folder"
        }), 400

@app.route('/upload-form/<int:item_id>', methods=['GET'])
def upload_form(item_id):
    """Render an HTML form for direct folder upload"""
    return render_template('upload_form.html', item_id=item_id)

@app.route('/files', methods=['GET'])
def list_files():
    """List all uploaded files with their paths and corresponding item_ids"""
    all_files = []
    all_items = get_all_items()
    static_resources = get_all_static_resources()
    
    for root, dirs, files in os.walk(UPLOAD_FOLDER):
        for file in files:
            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, UPLOAD_FOLDER)
            
            # Use enhanced prediction to determine the item_id
            item_id = predict_item_id(relative_path, file, all_items, static_resources)
            
            file_info = {
                "path": relative_path,
                "file_name": file,
                "item_id": item_id
            }
            
            # If we have a predicted item_id, add item details for reference
            if item_id and item_id in all_items:
                file_info["item_name"] = all_items[item_id].get('name')
                file_info["category"] = all_items[item_id].get('category')
                file_info["type"] = all_items[item_id].get('type')
            
            all_files.append(file_info)
    
    return jsonify({
        "files": all_files,
        "total": len(all_files)
    })

@app.route('/sync-static-resources', methods=['POST'])
def sync_static_resources():
    """
    Synchronize all files with static resources, ensuring they all have the prepath
    """
    all_files = []
    updated_count = 0
    all_items = get_all_items()
    static_resources = get_all_static_resources()
    
    for root, dirs, files in os.walk(UPLOAD_FOLDER):
        for file in files:
            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, UPLOAD_FOLDER)
            
            # Use enhanced prediction to determine the item_id
            item_id = predict_item_id(relative_path, file, all_items, static_resources)
            
            if item_id:
                # Append prepath to the relative path
                static_resource_path = f"{FILE_VIEW_PREPATH}{relative_path}"
                
                try:
                    # Update static resource with prepath
                    static_resource = {
                        "item_path": static_resource_path
                    }
                    response = requests.put(f"{API_STATIC_URL}/update/{item_id}", json=static_resource)
                    
                    if response.status_code == 200:
                        updated_count += 1
                        all_files.append({
                            "path": relative_path,
                            "item_id": item_id,
                            "static_path": static_resource_path,
                            "status": "updated"
                        })
                    else:
                        all_files.append({
                            "path": relative_path,
                            "item_id": item_id,
                            "status": "update_failed",
                            "error": response.text
                        })
                except requests.RequestException as e:
                    all_files.append({
                        "path": relative_path,
                        "item_id": item_id,
                        "status": "error",
                        "error": str(e)
                    })
            else:
                all_files.append({
                    "path": relative_path,
                    "status": "no_item_id"
                })
    
    return jsonify({
        "success": True,
        "message": f"Synchronized {updated_count} static resources with prepath",
        "files": all_files,
        "total": len(all_files),
        "updated": updated_count
    })

# Setup file serving routes
setup_file_serving(app, UPLOAD_FOLDER)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
