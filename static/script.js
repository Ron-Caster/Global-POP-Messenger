// script.js
let currentUser = null;
let eventSource = null;
let lastMessageId = 0;
let myAnonymousName = null;

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    currentUser = document.body.dataset.username;
    if(currentUser !== 'admin') {
        getAnonymousName();
    }
    setupEventSource();
<<<<<<< HEAD
    loadInitialMessages();
    setupMessageInput();
=======
    setInterval(refreshMessages, 3000);  // Refresh messages every 3 seconds
>>>>>>> 1d28c9194f768334b172ced112c1bc271e064dcd
});

// Get user's anonymous name from server
async function getAnonymousName() {
    try {
        const response = await fetch('/get-anonymous-name');
        const data = await response.json();
        myAnonymousName = data.anonymousName;
    } catch (error) {
        console.error('Error getting anonymous name:', error);
    }
}

// Set up SSE connection for real-time messages
function setupEventSource() {
    if (eventSource) eventSource.close();
    
    eventSource = new EventSource('/stream');
    
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if(data.sender !== currentUser) {  // Don't display our own messages from SSE
            appendMessage({
                sender: data.anonymousName,
                message: data.message,
                timestamp: data.timestamp
            });
        }
    };

    eventSource.onerror = (error) => {
        console.log('SSE error:', error);
        setTimeout(setupEventSource, 3000);
    };
}

// Load initial messages when page first loads
async function loadInitialMessages() {
    try {
        const response = await fetch('/get-messages');
        const data = await response.json();
        data.messages.reverse().forEach(appendMessage);  // Show oldest first at top
        lastMessageId = data.messages.length > 0 ? data.messages[0].id : 0;
    } catch (error) {
        console.error('Failed to load messages:', error);
    }
}

// Handle message input and sending
function setupMessageInput() {
    const input = document.getElementById('messageInput');
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}

// Send message to global chat
async function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    if (!message) return;
    
    try {
        // Optimistically add our own message
        appendMessage({
            sender: myAnonymousName,
            message: message,
            timestamp: new Date().toISOString(),
            isOwn: true
        });
        
        input.value = '';
        
        await fetch('/send', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ message: message })
        });
    } catch (error) {
        console.error('Failed to send message:', error);
        alert('Failed to send message. Please try again.');
    }
}

// Add message to chat display
function appendMessage(msg) {
    const messageList = document.getElementById('messageList');
    const isOwn = msg.isOwn || msg.sender === myAnonymousName;
    
<<<<<<< HEAD
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isOwn ? 'sent' : 'received'}`;
    
    messageDiv.innerHTML = `
        <div class="message-sender">${msg.sender}</div>
        <div class="message-content">${msg.message}</div>
        <span class="timestamp">${formatTimestamp(msg.timestamp)}</span>
    `;
    
    // Add to top if loading history, else to bottom
    if(msg.isHistory) {
        messageList.insertBefore(messageDiv, messageList.firstChild);
    } else {
        messageList.appendChild(messageDiv);
        messageList.scrollTop = messageList.scrollHeight;
    }
}

// Format timestamp for display
function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
}

// Admin functions
async function deleteUser(username) {
    if(confirm(`Delete user ${username} and all their messages?`)) {
        try {
            await fetch(`/delete-user/${encodeURIComponent(username)}`, {method: 'DELETE'});
            window.location.reload();
        } catch (error) {
            console.error('Delete failed:', error);
        }
    }
}

async function deleteMessage(messageId) {
    if(confirm('Delete this message permanently?')) {
        try {
            await fetch(`/delete-message/${messageId}`, {method: 'DELETE'});
            document.querySelector(`.message-item[data-id="${messageId}"]`).remove();
        } catch (error) {
            console.error('Delete failed:', error);
        }
=======
    try {
        const messageList = document.getElementById('messageList');
        // Store current scroll position and check if was at bottom
        const wasAtBottom = messageList.scrollHeight - messageList.scrollTop === messageList.clientHeight;
        const scrollTop = messageList.scrollTop;

        const response = await fetch(`/get_user_messages/${currentUser}`);
        const data = await response.json();
        messageList.innerHTML = ''; // Clear existing messages
        
        if (data.messages.length === 0) {
            messageList.innerHTML = '<div class="info-message">No messages yet. Start the conversation!</div>';
            return;
        }
        
        // Display all messages for the selected user
        data.messages.forEach(msg => {
            const div = document.createElement('div');
            div.className = `message ${msg.direction}`;
            
            const content = document.createElement('div');
            content.textContent = msg.message;
            
            const timestamp = document.createElement('span');
            timestamp.className = 'timestamp';
            timestamp.textContent = new Date(msg.timestamp).toLocaleString();
            
            div.appendChild(content);
            div.appendChild(timestamp);
            messageList.appendChild(div);
        });
        
        // Only auto-scroll if user was already at the bottom
        if (wasAtBottom) {
            messageList.scrollTop = messageList.scrollHeight;
        } else {
            messageList.scrollTop = scrollTop;
        }
    } catch (error) {
        console.error('Failed to refresh messages:', error);
>>>>>>> 1d28c9194f768334b172ced112c1bc271e064dcd
    }
}