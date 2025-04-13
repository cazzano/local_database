import os
import re

def sanitize_filename(name):
    """
    Sanitize a filename by removing invalid characters and replacing spaces with underscores
    """
    # Remove any invalid filename characters
    sanitized = re.sub(r'[\\/*?:"<>|]', '', name)
    # Replace spaces with underscores
    sanitized = sanitized.replace(' ', '_')
    # Remove any other potentially problematic characters
    sanitized = re.sub(r'[^\w\-\.]', '', sanitized)
    # Ensure the filename isn't empty after sanitization
    if not sanitized:
        sanitized = "unnamed_file"
    return sanitized

def rename_file_based_on_item_details(file_path, item_details):
    """
    Rename a file based on the name in item_details without changing the extension
    
    Args:
        file_path (str): Original file path
        item_details (dict): Dictionary containing item details with 'name' key
        
    Returns:
        str: New file path after renaming
    """
    if not item_details or 'name' not in item_details:
        return file_path
    
    # Extract directory and filename from path
    directory = os.path.dirname(file_path)
    original_filename = os.path.basename(file_path)
    
    # Get file extension
    _, file_extension = os.path.splitext(original_filename)
    
    # Get item name and sanitize it for use as a filename
    item_name = item_details.get('name')
    sanitized_name = sanitize_filename(item_name)
    
    # Create new filename with the original extension
    new_filename = f"{sanitized_name}{file_extension}"
    
    # Create the new file path
    new_file_path = os.path.join(directory, new_filename)
    
    # If the new path already exists, add a numeric suffix
    counter = 1
    while os.path.exists(new_file_path):
        new_filename = f"{sanitized_name}_{counter}{file_extension}"
        new_file_path = os.path.join(directory, new_filename)
        counter += 1
    
    # Perform the actual file renaming
    try:
        os.rename(file_path, new_file_path)
        return new_file_path
    except OSError as e:
        print(f"Error renaming file: {e}")
        return file_path
