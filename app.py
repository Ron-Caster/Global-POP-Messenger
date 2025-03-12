from flask import Flask, render_template, request, redirect, url_for, session, Response
import sqlite3
from datetime import datetime
import hashlib
import os

import threading
from faker import Faker

app = Flask(__name__)
app.secret_key = os.urandom(24)
fake = Faker()

# Admin credentials
ADMIN_CREDENTIALS = {'username': 'admin', 'password': 'admin123'}
=======
import time
import json
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Set up logging
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(level=logging.INFO)
handler = RotatingFileHandler(
    'logs/app.log', 
    maxBytes=1024 * 1024,  # 1MB
    backupCount=5
)
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
app.logger.addHandler(handler)

# Database functions
def create_connection():
    conn = sqlite3.connect('messages.db', check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def create_tables():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE,
                        password TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sender TEXT,
                        message TEXT,
                        timestamp DATETIME,
                        anonymous_name TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS anonymous_mapping (
                        username TEXT PRIMARY KEY,
                        anonymous_name TEXT)''')
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_anonymous_name(username):
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT anonymous_name FROM anonymous_mapping WHERE username = ?", (username,))
    result = cursor.fetchone()
    if not result:
        anon_name = fake.first_name() + str(random.randint(100,999))
        cursor.execute("INSERT INTO anonymous_mapping VALUES (?, ?)", (username, anon_name))
        conn.commit()
        return anon_name
    return result[0]

# Routes
@app.route('/')
def home():
    if 'username' in session:
        return redirect(url_for('global_chat'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == ADMIN_CREDENTIALS['username'] and password == ADMIN_CREDENTIALS['password']:
            session['username'] = 'admin'
            return redirect(url_for('admin_dashboard'))
            
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?",
                      (username, hash_password(password)))
        user = cursor.fetchone()
        conn.close()
        if user:
            session['username'] = username
            get_anonymous_name(username)
            return redirect(url_for('global_chat'))
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = create_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                           (username, hash_password(password)))
            conn.commit()
            session['username'] = username
            get_anonymous_name(username)
            return redirect(url_for('global_chat'))
        except sqlite3.IntegrityError:
            return render_template('signup.html', error='Username already exists')
        finally:
            conn.close()
    return render_template('signup.html')

@app.route('/global-chat')
def global_chat():
=======
@app.route('/stream')
def stream():
    username = request.args.get('username')
    if not username:
        app.logger.error(f"Stream request without username")
        return {'status': 'error', 'message': 'Username is required'}, 400

    def event_stream():
        last_id = 0
        while True:
            try:
                conn = create_connection()
                cursor = conn.cursor()
                cursor.execute('''SELECT id, sender, receiver, message, timestamp FROM messages
                                WHERE id > ? AND (receiver = ? OR sender = ?)
                                ORDER BY timestamp ASC''',
                             (last_id, username, username))
                messages = cursor.fetchall()
                conn.close()

                for msg in messages:
                    last_id = msg[0]
                    data = {
                        'sender': msg[1],
                        'receiver': msg[2],
                        'message': msg[3],
                        'timestamp': msg[4]
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                time.sleep(0.5)
            except Exception as e:
                app.logger.error(f"Stream error for user {username}: {str(e)}")
                time.sleep(1)

    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        }
    )

@app.route('/get_user_messages/<username>')
def get_user_messages(username):
    if 'username' not in session:
        return {'status': 'error'}, 401
    user = session['username']
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''SELECT sender, receiver, message, timestamp FROM messages
                    WHERE (receiver = ? AND sender = ?)
                    OR (receiver = ? AND sender = ?)
                    ORDER BY timestamp ASC''', 
                 (user, username, username, user))
    messages = [{
        'sender': msg[0],
        'receiver': msg[1],
        'message': msg[2],
        'timestamp': msg[3],
        'direction': 'sent' if msg[0] == user else 'received'
    } for msg in cursor.fetchall()]
    conn.close()
    return {'messages': messages}

@app.route('/messages')
def messaging():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('global_chat.html', username=session['username'])

@app.route('/send', methods=['POST'])
def send_message():
    if 'username' not in session:
        return {'status': 'error'}, 401
        
    sender = session['username']
    data = request.json
    anon_name = get_anonymous_name(sender)
    
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO messages (sender, message, timestamp, anonymous_name)
                    VALUES (?, ?, ?, ?)''',
                 (sender, data['message'], datetime.now(), anon_name))
    conn.commit()
    conn.close()
    return {'status': 'success'}

@app.route('/get-messages')
def get_messages():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''SELECT anonymous_name, message, timestamp FROM messages
                    ORDER BY timestamp DESC LIMIT 100''')
    messages = [{
        'sender': msg[0],
        'message': msg[1],
        'timestamp': msg[2]
    } for msg in cursor.fetchall()]
    conn.close()
    return {'messages': messages}

# Admin routes
@app.route('/admin')
def admin_dashboard():
    if 'username' not in session or session['username'] != 'admin':
        return redirect(url_for('login'))
    
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users")
    users = [u[0] for u in cursor.fetchall()]
    cursor.execute("SELECT id, sender, message, timestamp FROM messages")
    messages = cursor.fetchall()
    conn.close()
    
    return render_template('admin_dashboard.html', users=users, messages=messages)

@app.route('/delete-user/<username>')
def delete_user(username):
    if 'username' not in session or session['username'] != 'admin':
        return redirect(url_for('login'))
    
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username = ?", (username,))
    cursor.execute("DELETE FROM messages WHERE sender = ?", (username,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/delete-message/<int:msg_id>')
def delete_message(msg_id):
    if 'username' not in session or session['username'] != 'admin':
        return redirect(url_for('login'))
    
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE id = ?", (msg_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    create_tables()

    # Create default admin user
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''INSERT OR IGNORE INTO users 
                    (username, password) VALUES (?, ?)''',
                 ('admin', hash_password('admin123')))
    conn.commit()
    conn.close()
=======
    app.logger.info('Application startup: Database tables created')
    # Run with standard Flask development server
    app.run(host='0.0.0.0', port=5000, debug=True)
