from flask import Flask, render_template, request, redirect, url_for, session, Response
import sqlite3
from datetime import datetime, timedelta
import hashlib
import os
import time
import json
import threading
import random
from groq import Groq
from faker import Faker

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
    cursor.execute('''CREATE TABLE IF NOT EXISTS bot_state (
                        username TEXT PRIMARY KEY,
                        last_processed_id INTEGER NOT NULL,
                        last_response_time DATETIME)''')
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_last_response_time():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT last_response_time FROM bot_state WHERE username = ?', ('ammu',))
    result = cursor.fetchone()
    conn.close()
    return datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S') if result else None

def update_last_response_time():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''INSERT OR REPLACE INTO bot_state 
                      (username, last_processed_id, last_response_time)
                      VALUES (?, ?, ?)''', ('ammu', 0, datetime.now()))
    conn.commit()
    conn.close()

# Logging messages for conversational memory
CONVERSATION_LOG = "conversation_log.json"

def log_conversation(message, sender):
    """ Store user messages for conversation history """
    if sender == "ammu":
        return  # Ignore bot's own messages

    conversation_data = []
    if os.path.exists(CONVERSATION_LOG):
        with open(CONVERSATION_LOG, "r") as f:
            try:
                conversation_data = json.load(f)
            except json.JSONDecodeError:
                pass

    conversation_data.append({"sender": sender, "message": message, "timestamp": datetime.now().isoformat()})

    # Keep only last 50 messages for context
    conversation_data = conversation_data[-50:]

    with open(CONVERSATION_LOG, "w") as f:
        json.dump(conversation_data, f, indent=4)

def get_conversation_history():
    """ Retrieve past conversation history """
    if os.path.exists(CONVERSATION_LOG):
        with open(CONVERSATION_LOG, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def generate_response(prompt):
    """ Generate response using Groq AI """
    try:
        conversation_history = get_conversation_history()
        history_text = "\n".join([f"{msg['sender']}: {msg['message']}" for msg in conversation_history[-10:]])  # Last 10 messages

        full_prompt = f"Conversation history:\n{history_text}\n\nNow respond to this new message:\n{prompt}"

        response = client.chat.completions.create(
            messages=[{"role": "system", "content": "You are Ammu, an intelligent chatbot."},
                      {"role": "user", "content": full_prompt}],
            model="llama3-70b-8192",
            temperature=0.7,
            max_tokens=50
        )
        return response.choices[0].message.content
    except Exception as e:
        app.logger.error(f"Ammu API error: {str(e)}")
        return None

def ammu_bot():
    while True:
        try:
            last_response_time = get_last_response_time()
            now = datetime.now()

            # Only respond once every 24 hours
            if last_response_time and (now - last_response_time).total_seconds() < 86400:
                time.sleep(3600)  # Sleep for an hour before checking again
                continue

            # Check for mentions of @ammu
            conn = create_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, sender, message FROM messages WHERE message LIKE '%@ammu%' ORDER BY id DESC LIMIT 1")
            mention = cursor.fetchone()
            
            if mention:
                msg_id, sender, msg = mention
                if sender != "ammu":  # Ensure bot doesn't reply to itself
                    response = generate_response(msg)
                    if response:
                        cursor.execute("INSERT INTO messages (sender, message, timestamp, anonymous_name) VALUES (?, ?, ?, ?)",
                                       ('ammu', response, datetime.now(), 'Ammu'))
                        conn.commit()
                        update_last_response_time()  # Update last response time after replying
                        log_conversation(response, "ammu")

            conn.close()
            time.sleep(3600)  # Check again in an hour

        except Exception as e:
            app.logger.error(f"Ammu bot error: {str(e)}")
            time.sleep(3600)  # Sleep for an hour before retrying

@app.route('/send', methods=['POST'])
def send_message():
    if 'username' not in session:
        return {'status': 'error'}, 401

    sender = session['username']
    data = request.json
    message_text = data['message']

    log_conversation(message_text, sender)  # Log message for memory

    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO messages (sender, message, timestamp, anonymous_name) VALUES (?, ?, ?, ?)',
                   (sender, message_text, datetime.now(), sender))
    conn.commit()
    conn.close()
    
    return {'status': 'success'}

@app.route('/get-messages')
def get_messages():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT sender, message, timestamp FROM messages ORDER BY timestamp DESC LIMIT 100')
    messages = [{'sender': msg[0], 'message': msg[1], 'timestamp': msg[2]} for msg in cursor.fetchall()]
    conn.close()
    return {'messages': messages}

if __name__ == '__main__':
    create_tables()

    # Start Ammu bot in background
    bot_thread = threading.Thread(target=ammu_bot)
    bot_thread.daemon = True
    bot_thread.start()

    app.run(host='0.0.0.0', port=5000, debug=True)