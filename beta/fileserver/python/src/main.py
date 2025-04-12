from flask import Flask, request, jsonify
import os
import requests
import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from serve import setup_file_serving

app = Flask(__name__)

# Base directory to store uploaded files
UPLOAD_FOLDER = 'db'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# API endpoint for items
API_BASE_URL = 'http://localhost:5000/items'
API_STATIC_URL = 'http://localhost:5000/items/static'

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
        if resource.get('item_path') and file_path in resource['item_path']:
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
    
    # Save the file
    file_path = os.path.join(dir_path, file.filename)
    file.save(file_path)
    
    # Update static resource in the items API
    relative_path = os.path.relpath(file_path, UPLOAD_FOLDER)
    try:
        # Record the file path in the static resources
        static_resource = {
            "item_path": relative_path
        }
        requests.put(f"{API_STATIC_URL}/update/{item_id}", json=static_resource)
    except requests.RequestException as e:
        # Log the error but continue since the file is already saved
        print(f"Failed to update static resource: {e}")
    
    return jsonify({
        "success": True,
        "message": f"File uploaded successfully for item {item_id}",
        "path": file_path,
        "item_details": item_details
    })

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

# Setup file serving routes
setup_file_serving(app, UPLOAD_FOLDER)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
