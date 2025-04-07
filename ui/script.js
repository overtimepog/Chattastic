document.addEventListener('DOMContentLoaded', () => {
    const wsStatus = document.getElementById('ws-status');
    const twitchAuthStatus = document.getElementById('twitch-auth-status');
    const kickAuthStatus = document.getElementById('kick-auth-status');
    const chatMessages = document.getElementById('chat-messages');
    const allViewersList = document.getElementById('all-viewers-list');
    const selectedViewersList = document.getElementById('selected-viewers-list');
    const currentTwitchChannel = document.getElementById('current-twitch-channel');
    const currentKickChannel = document.getElementById('current-kick-channel');

    let socket;

    function connectWebSocket() {
        // Construct WebSocket URL dynamically
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws`;
        console.log(`Attempting to connect WebSocket to: ${wsUrl}`);
        socket = new WebSocket(wsUrl);

        socket.onopen = () => {
            console.log('WebSocket connection established');
            wsStatus.textContent = 'Connected';
            wsStatus.className = 'connected';
            // Request initial status upon connection
            sendMessage({ type: 'get_initial_status' });
        };

        socket.onmessage = (event) => {
            console.log('Message from server:', event.data);
            try {
                const message = JSON.parse(event.data);
                handleWebSocketMessage(message);
            } catch (error) {
                console.error('Failed to parse WebSocket message:', error);
                addChatMessage(`System: Received malformed message: ${event.data}`);
            }
        };

        socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            wsStatus.textContent = 'Error';
            wsStatus.className = 'disconnected';
        };

        socket.onclose = (event) => {
            console.log('WebSocket connection closed:', event.reason, `Code: ${event.code}`);
            wsStatus.textContent = 'Disconnected';
            wsStatus.className = 'disconnected';
            // Attempt to reconnect after a delay
            setTimeout(connectWebSocket, 5000); // Reconnect every 5 seconds
        };
    }

    function sendMessage(message) {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify(message));
        } else {
            console.error('WebSocket is not connected.');
        }
    }

    function handleWebSocketMessage(message) {
        switch (message.type) {
            case 'initial_status':
            case 'status_update':
                updateAuthStatus('twitch', message.data.twitch_authenticated);
                updateAuthStatus('kick', message.data.kick_authenticated);
                currentTwitchChannel.textContent = message.data.twitch_channel || 'None';
                currentKickChannel.textContent = message.data.kick_channel || 'None';
                break;
            case 'twitch_chat_message':
                addChatMessage(`Twitch (${message.data.channel}): ${message.data.user}: ${message.data.text}`);
                break;
            case 'kick_chat_message':
                // Use the new formatter function
                addChatMessage(formatKickMessage(message.data));
                break;
            case 'viewer_list_update':
                updateViewerList(message.data.viewers);
                break;
            case 'selected_viewers_update':
                updateSelectedViewers(message.data.selected_viewers);
                break;
            case 'error':
                 addChatMessage(`System Error: ${message.data.message}`);
                 console.error("Server Error:", message.data.message);
                 break;
            default:
                console.warn('Received unknown message type:', message.type);
                addChatMessage(`System: Received unknown message type: ${message.type}`);
        }
    }

    function updateAuthStatus(platform, isAuthenticated) {
        const element = platform === 'twitch' ? twitchAuthStatus : kickAuthStatus;
        if (element) {
            element.textContent = isAuthenticated ? 'Yes' : 'No';
            element.className = isAuthenticated ? 'authenticated' : 'not-authenticated';
        }
    }

    // New function to format Kick messages with badges
    function formatKickMessage(data) {
        let badgesHTML = '';
        // Check if identity and badges exist and are an array
        if (data.identity && Array.isArray(data.identity)) {
            data.identity.forEach(badge => {
                // Simple text representation for now. Could use icons/CSS later.
                // Common badge types: broadcaster, moderator, vip, subscriber, og
                if (badge.type) {
                    badgesHTML += `<span class="badge badge-${badge.type.toLowerCase()}">[${badge.type.toUpperCase()}]</span> `;
                }
            });
        }

        // Escape username and content to prevent XSS
        const username = escapeHTML(data.username || 'Unknown');
        const content = escapeHTML(data.content || '');
        const channel = escapeHTML(data.channel || 'kick');

        return `<p>Kick (${channel}): ${badgesHTML}<strong>${username}</strong>: ${content}</p>`;
    }

    // Helper function to escape HTML special characters
    function escapeHTML(str) {
        return str.replace(/[&<>"']/g, function (match) {
            return {
                '&': '&',
                '<': '<',
                '>': '>',
                '"': '"',
                "'": '&#39;' // Correct entity for single quote
            }[match];
        });
    }


    function addChatMessage(messageHTML) { // Changed parameter name
        const messageElement = document.createElement('div'); // Use div to allow innerHTML
        messageElement.innerHTML = messageHTML; // Set HTML content
        // Append the first child of the div (which should be the <p> tag)
        if (messageElement.firstChild) {
            chatMessages.appendChild(messageElement.firstChild);
        }
        // Scroll to the bottom
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

     function updateViewerList(viewers) {
        allViewersList.innerHTML = ''; // Clear existing list
        viewers.forEach(viewer => {
            const li = document.createElement('li');
            li.textContent = viewer; // Adjust if viewer is an object
            allViewersList.appendChild(li);
        });
    }

    function updateSelectedViewers(selectedViewers) {
        selectedViewersList.innerHTML = ''; // Clear existing list
        selectedViewers.forEach(viewer => {
            const li = document.createElement('li');
            li.textContent = viewer; // Adjust if viewer is an object
            selectedViewersList.appendChild(li);
        });
    }

    // --- Event Listeners ---
    // Authentication buttons (will redirect or open popup via backend)
    document.getElementById('auth-twitch-btn').addEventListener('click', () => {
        window.location.href = '/api/auth/twitch/login'; // Example endpoint
    });

    document.getElementById('auth-kick-btn').addEventListener('click', () => {
         window.location.href = '/api/auth/kick/login'; // Example endpoint
    });

    // Connect chat buttons
    document.getElementById('connect-twitch-chat-btn').addEventListener('click', () => {
        const channel = document.getElementById('channel-input').value;
        if (channel) {
            sendMessage({ type: 'connect_twitch_chat', data: { channel: channel } });
        } else {
            alert('Please enter a Twitch channel name.');
        }
    });

     document.getElementById('connect-kick-chat-btn').addEventListener('click', () => {
        const channel = document.getElementById('channel-input').value;
        if (channel) {
            // Clear chat messages before sending connect request
            chatMessages.innerHTML = '';
            sendMessage({ type: 'connect_kick_chat', data: { channel: channel } });
        } else {
            alert('Please enter a Kick channel name.');
        }
    });

    // Select random viewers button
    document.getElementById('select-random-viewers-btn').addEventListener('click', () => {
        const count = document.getElementById('viewer-count-select').value;
        sendMessage({ type: 'select_random_viewers', data: { count: parseInt(count, 10) } });
    });

    // Speak selected viewers button (placeholder)
    document.getElementById('speak-selected-btn').addEventListener('click', () => {
        sendMessage({ type: 'trigger_speak_selected' });
        console.log('Trigger speak selected message sent');
    });


    // Initial connection
    connectWebSocket();
});
