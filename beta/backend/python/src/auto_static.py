import requests
import json

def fetch_file_info_by_item_id(item_id):
    """
    Fetch file information from external API for the given item_id
    """
    try:
        response = requests.get('http://localhost:3000/files')
        if response.status_code == 200:
            data = response.json()
            # Filter files by item_id
            matching_files = [file for file in data.get('files', []) if file.get('item_id') == item_id]
            return matching_files
        else:
            print(f"Error fetching from external API: Status code {response.status_code}")
            return []
    except Exception as e:
        print(f"Exception when fetching file info: {str(e)}")
        return []

def get_path_for_item(item_id, add_prepath=True):
    """
    Get the file path for a specific item_id from the external API
    
    Parameters:
    - item_id: The ID of the item to fetch
    - add_prepath: If True, prepends "http://localhost:3000/files/view/" to the path
    
    Returns:
    - The complete path with prepath if add_prepath is True, otherwise the original path
    """
    files = fetch_file_info_by_item_id(item_id)
    if files:
        # Get the path of the first matching file
        original_path = files[0].get('path')
        
        # Return the path with prepath if add_prepath is True
        if add_prepath and original_path:
            return f"http://localhost:3000/files/view/{original_path}"
        return original_path
    return None
