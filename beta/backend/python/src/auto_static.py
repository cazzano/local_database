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

def get_path_for_item(item_id):
    """
    Get the file path for a specific item_id from the external API
    """
    files = fetch_file_info_by_item_id(item_id)
    if files:
        # Return the path of the first matching file
        return files[0].get('path')
    return None
