# main.py
from flask import Flask
from flask_cors import CORS
#from create_db import initialize_databases
from routes import setup_routes

app = Flask(__name__)
CORS(app)

# Initialize the databases when the app starts
#initialize_databases()

# Set up the routes
setup_routes(app)

if __name__ == "__main__":
    app.run()  # This will run on port 5000
