import os
import shutil
import zipfile
import io
from werkzeug.utils import secure_filename
from datetime import datetime
import requests

def ensure_directory_exists(directory):
    """Create directory if it doesn't exist"""
    if not os.path.exists(directory):
        os.makedirs(directory)

def extract_zip_folder(zip_file, destination_path):
    """Extract a ZIP file to the destination path"""
    # Create a ZipFile object from the uploaded file
    zip_obj = zipfile.ZipFile(zip_file)
    
    # Extract all contents to the destination path
    zip_obj.extractall(destination_path)
    
    # Close the zip file
    zip_obj.close()
    
    # Return list of all extracted files
    extracted_files = []
    for root, dirs, files in os.walk(destination_path):
        for file in files:
            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, destination_path)
            extracted_files.append(relative_path)
    
    return extracted_files

def process_folder_files(files, destination_path):
    """Process multiple files that represent a folder structure"""
    uploaded_files = []
    
    for file_obj in files:
        # Get the file path from the webkitRelativePath attribute
        if not hasattr(file_obj, 'filename') or not file_obj.filename:
            continue
            
        # Handle directory structure from HTML directory upload
        # The path might be like "folder/subfolder/file.txt"
        file_path = file_obj.filename
        
        # Create directory structure if needed
        dir_name = os.path.dirname(os.path.join(destination_path, file_path))
        if dir_name:
            ensure_directory_exists(dir_name)
            
        # Save the file
        full_path = os.path.join(destination_path, file_path)
        file_obj.save(full_path)
        uploaded_files.append(file_path)
    
    return uploaded_files

def copy_folder_contents(source_folder, destination_folder):
    """Copy a folder and all its contents to the destination folder"""
    # Ensure destination directory exists
    ensure_directory_exists(destination_folder)
    
    # Copy all contents
    copied_files = []
    for item in os.listdir(source_folder):
        source_item = os.path.join(source_folder, item)
        dest_item = os.path.join(destination_folder, item)
        
        if os.path.isdir(source_item):
            # Recursively copy subdirectories
            sub_copied = copy_folder_contents(source_item, dest_item)
            copied_files.extend(sub_copied)
        else:
            # Copy file
            shutil.copy2(source_item, dest_item)
            copied_files.append(dest_item)
    
    return copied_files

def update_static_resource(item_id, file_path, api_static_url, file_view_prepath):
    """Update static resource for a file"""
    try:
        # Append prepath to the relative path
        static_resource_path = f"{file_view_prepath}{file_path}"
        
        # Record the file path in the static resources
        static_resource = {
            "item_path": static_resource_path
        }
        response = requests.put(f"{api_static_url}/update/{item_id}", json=static_resource)
        return response.status_code == 200, static_resource_path
    except requests.RequestException as e:
        # Log the error but continue since the file is already saved
        print(f"Failed to update static resource: {e}")
        return False, None

def process_folder_upload(folder_data, item_id, upload_folder, item_details, api_static_url, file_view_prepath):
    """Process the uploaded folder based on the upload type"""
    if not item_details:
        return {"error": f"Could not get details for item ID: {item_id}"}, 404
    
    # Extract category and type from item details
    category = item_details.get('category')
    file_type = item_details.get('type')
    
    if not category or not file_type:
        return {"error": "Invalid item details: missing category or type"}, 400
    
    # Create directory structure
    dir_path = os.path.join(upload_folder, category, file_type)
    ensure_directory_exists(dir_path)
    
    # Create a unique subfolder for this upload (using timestamp)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    item_name = item_details.get('name', '').replace(' ', '_').lower()
    folder_name = f"{item_name}_{item_id}_{timestamp}"
    folder_path = os.path.join(dir_path, folder_name)
    ensure_directory_exists(folder_path)
    
    uploaded_files = []
    processed_files = []
    
    # Process based on upload type
    if 'zip_file' in folder_data:
        # Extract the zip file
        zip_file = folder_data['zip_file']
        extracted_files = extract_zip_folder(zip_file, folder_path)
        
        for file_path in extracted_files:
            full_path = os.path.join(folder_path, file_path)
            relative_path = os.path.relpath(full_path, upload_folder)
            
            # Update static resource
            success, static_path = update_static_resource(item_id, relative_path, api_static_url, file_view_prepath)
            
            uploaded_files.append({
                "file_path": relative_path,
                "static_path": static_path,
                "updated": success
            })
            
        processed_files = extracted_files
            
    elif 'folder_files' in folder_data:
        # Process directory upload from browser
        folder_files = folder_data['folder_files']
        processed_files = process_folder_files(folder_files, folder_path)
        
        for file_path in processed_files:
            full_path = os.path.join(folder_path, file_path)
            relative_path = os.path.relpath(full_path, upload_folder)
            
            # Update static resource
            success, static_path = update_static_resource(item_id, relative_path, api_static_url, file_view_prepath)
            
            uploaded_files.append({
                "file_path": relative_path,
                "static_path": static_path,
                "updated": success
            })
    
    return {
        "success": True,
        "message": f"Folder uploaded successfully for item {item_id}",
        "folder_path": os.path.relpath(folder_path, upload_folder),
        "files": uploaded_files,
        "files_count": len(uploaded_files),
        "item_details": item_details
    }, 200
