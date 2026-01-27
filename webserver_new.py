import sqlite3
import os
from flask import Flask, render_template

app = Flask(__name__)

class DBWrapper:
    def __init__(self, db_path):
        self.db_path = db_path

    def get_connection(self):
        # row_factory erlaubt Zugriff via Spaltennamen: row['timestamp'] statt row[0]
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row 
        return conn

    def get_all_history(self):
        try:
            with self.get_connection() as connection:
                cursor = connection.cursor()
                return cursor.execute("SELECT * FROM history ORDER BY timestamp DESC;").fetchall()
        except sqlite3.OperationalError as e:
            print(f"Datenbankfehler: {e}")
            return []

# Dynamischer Pfad (sucht die DB im selben Ordner wie das Skript)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, 'c2c1.db')
db = DBWrapper(db_path)

@app.route('/history')
def show_history():
    history_entries = db.get_all_history()
    return render_template('air_data.html', history=history_entries)

if __name__ == '__main__':
    app.run(debug=True, port=5000)