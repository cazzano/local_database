import sqlite3

# Path to the static resources database
DATABASE_STATIC_PATH = "database/database_static.db"


def add_item_static(item_id, picture_url=None, download_url=None):
    """
    Add static resources for an item to the 'item_static' table.
    """
    conn = sqlite3.connect(DATABASE_STATIC_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO item_static (item_id, picture_url, download_url)
            VALUES (?, ?, ?)
        """,
            (item_id, picture_url, download_url),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # If record exists, try to update instead
        try:
            cursor.execute(
                """
                UPDATE item_static 
                SET picture_url = ?, download_url = ? 
                WHERE item_id = ?
            """,
                (picture_url, download_url, item_id),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error updating static resource: {e}")
            return False
    except Exception as e:
        print(f"Error adding static resource: {e}")
        return False
    finally:
        conn.close()


def get_item_static(item_id):
    """
    Retrieve static resources for an item by its ID.
    """
    conn = sqlite3.connect(DATABASE_STATIC_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM item_static WHERE item_id = ?", (item_id,))
    static_data = cursor.fetchone()
    conn.close()
    return static_data


def get_all_items_static():
    """
    Retrieve all static resources from the 'item_static' table.
    """
    conn = sqlite3.connect(DATABASE_STATIC_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM item_static")
    static_data = cursor.fetchall()
    conn.close()
    return static_data


def update_item_static(item_id, picture_url=None, download_url=None):
    """
    Update static resources for an item by its ID.
    """
    conn = sqlite3.connect(DATABASE_STATIC_PATH)
    cursor = conn.cursor()
    try:
        # Check if record exists
        cursor.execute("SELECT 1 FROM item_static WHERE item_id = ?", (item_id,))
        if cursor.fetchone():
            # Update existing record
            if picture_url is not None:
                cursor.execute(
                    "UPDATE item_static SET picture_url = ? WHERE item_id = ?",
                    (picture_url, item_id),
                )
            if download_url is not None:
                cursor.execute(
                    "UPDATE item_static SET download_url = ? WHERE item_id = ?",
                    (download_url, item_id),
                )
        else:
            # Insert new record
            cursor.execute(
                """
                INSERT INTO item_static (item_id, picture_url, download_url)
                VALUES (?, ?, ?)
            """,
                (item_id, picture_url, download_url),
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating static resource: {e}")
        return False
    finally:
        conn.close()


def delete_item_static(item_id):
    """
    Delete static resources for an item by its ID.
    """
    conn = sqlite3.connect(DATABASE_STATIC_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM item_static WHERE item_id = ?", (item_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting static resource: {e}")
        return False
    finally:
        conn.close()


def create_static_table_if_not_exists():
    """
    Create the 'item_static' table if it doesn't exist yet.
    """
    conn = sqlite3.connect(DATABASE_STATIC_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS item_static (
        item_id INTEGER PRIMARY KEY,
        picture_url TEXT,
        download_url TEXT,
        FOREIGN KEY (item_id) REFERENCES items (item_id)
    )
    ''')
    conn.commit()
    conn.close()
