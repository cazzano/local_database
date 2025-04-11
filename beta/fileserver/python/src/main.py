from flask import Flask, request, jsonify
import os
import requests
import json

app = Flask(__name__)

# Base directory to store uploaded files
UPLOAD_FOLDER = 'db'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# API endpoint for items
API_BASE_URL = 'http://localhost:5000/items'

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
    
    # Create a map for faster lookup based on category and type
    category_type_map = {}
    for item_id, item in all_items.items():
        category = item.get('category')
        file_type = item.get('type')
        if category and file_type:
            # Multiple items might have the same category and type
            if (category, file_type) not in category_type_map:
                category_type_map[(category, file_type)] = []
            category_type_map[(category, file_type)].append(item_id)
    
    for root, dirs, files in os.walk(UPLOAD_FOLDER):
        for file in files:
            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, UPLOAD_FOLDER)
            
            # Parse the path to find the category and type
            path_parts = relative_path.split(os.sep)
            if len(path_parts) >= 2:
                category = path_parts[0]
                file_type = path_parts[1]
                
                # Get all potential matching item IDs
                matching_item_ids = category_type_map.get((category, file_type), [])
                
                # If multiple matches exist, we need a more specific rule
                # For now, include all potential matches
                if matching_item_ids:
                    all_files.append({
                        "path": relative_path,
                        "possible_item_ids": matching_item_ids,
                        # Use the first match as the primary item_id
                        "item_id": matching_item_ids[0] if matching_item_ids else None
                    })
                else:
                    all_files.append({
                        "path": relative_path,
                        "item_id": None
                    })
            else:
                # For files that don't match the expected structure
                all_files.append({
                    "path": relative_path,
                    "item_id": None
                })
    
    return jsonify({
        "files": all_files,
        "total": len(all_files)
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
