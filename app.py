from flask import Flask, render_template, request, redirect, url_for, session, Response
import sqlite3
from datetime import datetime, timedelta
import hashlib
import os
import time
import json
import logging
from logging.handlers import RotatingFileHandler
import threading
import random
from groq import Groq
from faker import Faker
import re

app = Flask(__name__)
app.secret_key = os.urandom(24)
fake = Faker()

# Admin credentials
ADMIN_CREDENTIALS = {'username': 'admin', 'password': 'admin123'}

# Groq client for Ammu
client = Groq(api_key="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")

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
    cursor.execute('''CREATE TABLE IF NOT EXISTS bot_state (
                        username TEXT PRIMARY KEY,
                        last_processed_id INTEGER NOT NULL,
                        last_summary_time DATETIME,
                        last_bot_response_date DATE)''')
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

# Ammu AI Integration
def ammu_bot():
    system_prompt = "You are Ammu, a 21-year-old engineering student from Kerala, India. Now you are at Bengaluru, studying at IIT Bangalore. You're active in this chat group while trying to blend in according to the messages."
    
    def get_last_processed_id():
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute('''SELECT last_processed_id, last_summary_time, last_bot_response_date FROM bot_state 
                        WHERE username = ?''', ('ammu',))
        result = cursor.fetchone()
        conn.close()
        if result:
            return result[0], datetime.strptime(result[1], '%Y-%m-%d %H:%M:%S.%f') if result[1] else None, result[2] if result[2] else None
        return 0, None, None

    def update_bot_state(last_id, last_time, last_bot_response_date):
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute('''INSERT OR REPLACE INTO bot_state 
                        (username, last_processed_id, last_summary_time, last_bot_response_date)
                        VALUES (?, ?, ?, ?)''', 
                     ('ammu', last_id, last_time, last_bot_response_date))
        conn.commit()
        conn.close()

    def generate_response(prompt):
        try:
            response = client.chat.completions.create(
                messages=[{"role": "system", "content": system_prompt},
                         {"role": "user", "content": prompt}],
                model="llama3-70b-8192",
                temperature=0.7,
                max_tokens=50
            )
            return response.choices[0].message.content
        except Exception as e:
            app.logger.error(f"Ammu API error: {str(e)}")
            return None

    def get_chat_context():
        conn = create_connection()
        cursor = conn.cursor()
        cursor.execute('''SELECT message FROM messages 
                        ORDER BY timestamp DESC LIMIT 20''')
        messages = [msg[0] for msg in cursor.fetchall()]
        conn.close()
        return "Recent chat:\n" + "\n".join(messages[-5:])

    while True:
        try:
            last_id, last_summary, last_bot_response_date = get_last_processed_id()
            now = datetime.now()
            
            # Check mentions
            conn = create_connection()
            cursor = conn.cursor()
            cursor.execute('''SELECT id, sender, message FROM messages
                            WHERE id > ? AND message LIKE '%@ammu%' 
                            ORDER BY id ASC''', (last_id,))
            mentions = cursor.fetchall()
            
            for msg in mentions:
                # Generate response
                response = generate_response(f"Respond to this message: {msg[2]}")
                if response and (last_bot_response_date is None or (now - datetime.strptime(last_bot_response_date, "%Y-%m-%d")).days >= 1):
                    # Send response
                    cursor.execute('''INSERT INTO messages 
                                    (sender, message, timestamp, anonymous_name)
                                    VALUES (?, ?, ?, ?)''',
                                 ('ammu', response, datetime.now(), get_anonymous_name('ammu')))
                    conn.commit()
                    app.logger.info(f"Ammu responded to message {msg[0]}")
                    last_bot_response_date = now.date().strftime('%Y-%m-%d')
                
                last_id = msg[0]
            
            # Periodic summary (every 5 minutes)
            if not last_summary or (now - last_summary) > timedelta(minutes=5):
                context = get_chat_context()
                prompt = f"Generate an engaging message based on this chat:\n{context}"
                response = generate_response(prompt)
                
                if response:
                    cursor.execute('''INSERT INTO messages 
                                    (sender, message, timestamp, anonymous_name)
                                    VALUES (?, ?, ?, ?)''',
                                 ('ammu', response, datetime.now(), get_anonymous_name('ammu')))
                    conn.commit()
                    app.logger.info("Ammu posted periodic message")
                
                update_bot_state(last_id, now, last_bot_response_date)
            
            conn.close()
            time.sleep(15)
            
        except Exception as e:
            app.logger.error(f"Ammu bot error: {str(e)}")
            time.sleep(30)

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
    # Start Ammu bot
    bot_thread = threading.Thread(target=ammu_bot)
    bot_thread.daemon = True
    bot_thread.start()
    app.run(host='0.0.0.0', port=5000, debug=True)