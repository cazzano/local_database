import sqlite3

# Path to the new database
DATABASE_PATH = "database/database.db"


def add_item(category, name, details, type, item_id=None):
    """
    Add a new item to the 'items' table.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO items (item_id, category, name, details, type)
            VALUES (?, ?, ?, ?, ?)
        """,
            (item_id, category, name, details, type),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        print("Error: Item ID already exists.")
        return False
    finally:
        conn.close()


def get_all_items():
    """
    Retrieve all items from the 'items' table.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM items")
    items = cursor.fetchall()
    conn.close()
    return items


def get_item_by_id(item_id):
    """
    Retrieve an item by its ID.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM items WHERE item_id = ?", (item_id,))
    item = cursor.fetchone()
    conn.close()
    return item


def update_item(item_id, category=None, name=None, details=None, type=None):
    """
    Update an item's details by its ID.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    try:
        if category:
            cursor.execute(
                "UPDATE items SET category = ? WHERE item_id = ?", (category, item_id)
            )
        if name:
            cursor.execute(
                "UPDATE items SET name = ? WHERE item_id = ?", (name, item_id)
            )
        if details:
            cursor.execute(
                "UPDATE items SET details = ? WHERE item_id = ?", (details, item_id)
            )
        if type:
            cursor.execute(
                "UPDATE items SET type = ? WHERE item_id = ?", (type, item_id)
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating item: {e}")
        return False
    finally:
        conn.close()


def delete_item(item_id):
    """
    Delete an item by its ID.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM items WHERE item_id = ?", (item_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting item: {e}")
        return False
    finally:
        conn.close()


def create_table_if_not_exists():
    """
    Create the 'items' table if it doesn't exist yet.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS items (
        item_id INTEGER PRIMARY KEY,
        category TEXT,
        name TEXT,
        details TEXT,
        type TEXT
    )
    ''')
    conn.commit()
    conn.close()
