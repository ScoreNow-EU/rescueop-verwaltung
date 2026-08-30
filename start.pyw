import webbrowser
import os
import sys

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()

webbrowser.open('http://127.0.0.1:5000')
app.run(host='127.0.0.1', port=5000, debug=True)
