from flask import request, jsonify
from crud_database import (
    add_item,
    get_all_items,
    get_item_by_id,
    update_item,
    delete_item,
    create_table_if_not_exists
)
from crud_database_static import (
    add_item_static,
    get_item_static,
    update_item_static,
    delete_item_static,
    get_all_items_static,
    create_static_table_if_not_exists
)
from auto_static import get_path_for_item


def setup_routes(app):
    # Create database tables if they don't exist
    create_table_if_not_exists()
    create_static_table_if_not_exists()
    
    @app.route('/')
    def home():
        return "Welcome to the Items Database App!"

    # Item CRUD routes
    @app.route('/items/add', methods=['POST'])
    def add_item_route():
        data = request.json
        if not all(key in data for key in ['name', 'category', 'type']):
            return jsonify({"message": "Missing required fields"}), 400

        if add_item(
            data['category'],
            data['name'],
            data.get('details'),
            data['type'],
            data.get('item_id')
        ):
            # If static resources are provided, add them too
            if 'item_path' in data:
                add_item_static(
                    data.get('item_id'),
                    data.get('item_path')
                )
            return jsonify({"message": "Item added successfully"}), 201
        return jsonify({"message": "Failed to add item"}), 400

    @app.route('/items', methods=['GET'])
    def get_all_items_route():
        items = get_all_items()
        items_list = []
        for item in items:
            static_data = get_item_static(item[0])  # item[0] is item_id
            item_dict = {
                "item_id": item[0],
                "category": item[1],
                "name": item[2],
                "details": item[3],
                "type": item[4],
                "static_resources": {
                    "item_path": static_data[1] if static_data else None
                } if static_data else None
            }
            items_list.append(item_dict)
        return jsonify(items_list), 200

    @app.route('/items/<int:item_id>', methods=['GET'])
    def get_item_by_id_route(item_id):
        item = get_item_by_id(item_id)
        if not item:
            return jsonify({"message": "Item not found"}), 404

        static_data = get_item_static(item_id)
        item_dict = {
            "item_id": item[0],
            "category": item[1],
            "name": item[2],
            "details": item[3],
            "type": item[4],
            "static_resources": {
                "item_path": static_data[1] if static_data else None
            } if static_data else None
        }
        return jsonify(item_dict), 200

    @app.route('/items/update/<int:item_id>', methods=['PUT'])
    def update_item_route(item_id):
        data = request.json
        item_updated = update_item(
            item_id,
            data.get('category'),
            data.get('name'),
            data.get('details'),
            data.get('type')
        )

        # Handle static resource updates if provided
        static_updated = True
        if 'item_path' in data:
            static_updated = update_item_static(
                item_id,
                data.get('item_path')
            )

        if item_updated and static_updated:
            return jsonify({"message": "Item updated successfully"}), 200
        return jsonify({"message": "Failed to update item"}), 400

    @app.route('/items/delete/<int:item_id>', methods=['DELETE'])
    def delete_item_route(item_id):
        # Delete static resources first (if they exist)
        delete_item_static(item_id)

        if delete_item(item_id):
            return jsonify({"message": "Item and associated resources deleted successfully"}), 200
        return jsonify({"message": "Failed to delete item"}), 400

    # Static resources routes
    @app.route('/items/static', methods=['GET'])
    def get_all_items_static_route():
        static_data = get_all_items_static()
        if not static_data:
            return jsonify([]), 200

        result = []
        for data in static_data:
            result.append({
                "item_id": data[0],
                "item_path": data[1]
            })
        return jsonify(result), 200

    @app.route('/items/static/add/<int:item_id>', methods=['POST'])
    def add_item_static_route(item_id):
        data = request.json
        if add_item_static(item_id, data.get('item_path')):
            return jsonify({"message": "Static resources added successfully"}), 201
        return jsonify({"message": "Failed to add static resources"}), 400

    @app.route('/items/static/<int:item_id>', methods=['GET'])
    def get_item_static_route(item_id):
        static_data = get_item_static(item_id)
        if static_data:
            return jsonify({
                "item_id": static_data[0],
                "item_path": static_data[1]
            }), 200
        return jsonify({"message": "Static resources not found"}), 404

    @app.route('/items/static/update/<int:item_id>', methods=['PUT'])
    def update_item_static_route(item_id):
        data = request.json
        if update_item_static(item_id, data.get('item_path')):
            return jsonify({"message": "Static resources updated successfully"}), 200
        return jsonify({"message": "Failed to update static resources"}), 400

    @app.route('/items/static/delete/<int:item_id>', methods=['DELETE'])
    def delete_item_static_route(item_id):
        if delete_item_static(item_id):
            return jsonify({"message": "Static resources deleted successfully"}), 200
        return jsonify({"message": "Failed to delete static resources"}), 400
        
    # New route for automatic static content addition
    @app.route('/items/static/auto/<int:item_id>', methods=['POST'])
    def auto_add_static_route(item_id):
        # Check if the item exists
        item = get_item_by_id(item_id)
        if not item:
            return jsonify({"message": "Item not found"}), 404
            
        # Fetch the path from external API
        path = get_path_for_item(item_id)
        if not path:
            return jsonify({"message": "No matching files found in external API for this item_id"}), 404
            
        # Check if static resource already exists for this item
        existing_static = get_item_static(item_id)
        
        if existing_static:
            # Update existing static resource
            if update_item_static(item_id, path):
                return jsonify({
                    "message": "Static resources automatically updated successfully",
                    "item_id": item_id,
                    "item_path": path
                }), 200
            else:
                return jsonify({"message": "Failed to update static resources"}), 400
        else:
            # Add new static resource
            if add_item_static(item_id, path):
                return jsonify({
                    "message": "Static resources automatically added successfully",
                    "item_id": item_id,
                    "item_path": path
                }), 201
            else:
                return jsonify({"message": "Failed to add static resources"}), 400
