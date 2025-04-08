(function() {
    const chatContainer = document.getElementById('chat-container');
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws`;
    let ws = null;
    let reconnectTimeout = null;
    let messageLimit = 15; // Default message limit

    function connectWebSocket() {
        if (reconnectTimeout) {
            clearTimeout(reconnectTimeout);
            reconnectTimeout = null;
        }

        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
            console.log('WebSocket is already open or connecting.');
            return;
        }

        ws = new WebSocket(wsUrl);
        console.log('Attempting WebSocket connection...');

        ws.onopen = () => {
            console.log('WebSocket connection established.');
            // Clear any previous reconnect timer
            if (reconnectTimeout) {
                clearTimeout(reconnectTimeout);
                reconnectTimeout = null;
            }
        };

        ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                // console.log('Received message:', message); // For debugging

                if (message.type === 'kick_chat_message' && message.data) { // Changed type check
                    addChatMessage(message.data.user, message.data.text); // Changed data fields
                } else if (message.type === 'kick_overlay_command' && message.data) {
                    handleCommand(message.data);
                }
            } catch (error) {
                console.error('Error processing WebSocket message:', error);
            }
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            // Don't attempt immediate reconnect here, onclose will handle it
        };

        ws.onclose = (event) => {
            console.log(`WebSocket closed. Code: ${event.code}, Reason: ${event.reason}. Attempting reconnect...`);
            ws = null; // Ensure ws object is cleared
            // Schedule reconnection attempt
            if (!reconnectTimeout) {
                reconnectTimeout = setTimeout(connectWebSocket, 5000); // Try again in 5 seconds
            }
        };
    }

    function addChatMessage(sender, messageText) {
        if (!chatContainer) return;

        const messageElement = document.createElement('div');
        messageElement.classList.add('chat-message');

        const senderElement = document.createElement('strong');
        senderElement.textContent = sender + ':'; // Add colon after sender

        // Sanitize message text slightly (prevent basic HTML injection)
        const messageTextNode = document.createTextNode(' ' + messageText); // Add space after sender

        messageElement.appendChild(senderElement);
        messageElement.appendChild(messageTextNode);

        chatContainer.appendChild(messageElement);

        // Scroll to bottom (optional, might not be needed if OBS source scrolls)
        // chatContainer.scrollTop = chatContainer.scrollHeight;

        // Enforce message limit
        while (chatContainer.children.length > messageLimit) {
            chatContainer.removeChild(chatContainer.firstChild);
        }
    }

    function handleCommand(commandData) {
        console.log('Handling command:', commandData);
        if (!chatContainer) return; // Ensure container exists

        switch (commandData.command) {
            case 'clear':
                if (chatContainer) {
                    chatContainer.innerHTML = ''; // Clear all messages
                    console.log('Chat overlay cleared.');
                }
                break;
            case 'set_limit':
                if (typeof commandData.limit === 'number' && commandData.limit > 0) {
                    messageLimit = commandData.limit;
                    console.log(`Chat overlay message limit set to: ${messageLimit}`);
                    // Enforce new limit immediately
                    if (chatContainer) {
                        while (chatContainer.children.length > messageLimit) {
                            chatContainer.removeChild(chatContainer.firstChild);
                        }
                    }
                } else {
                    console.warn('Invalid limit value received:', commandData.limit);
                }
                break;
            // Removed duplicated default case here
            case 'set_layout':
                if (commandData.flow === 'upwards') {
                    chatContainer.classList.remove('flow-downwards');
                    chatContainer.classList.add('flow-upwards');
                    console.log('Chat overlay layout set to upwards (new at bottom).');
                } else if (commandData.flow === 'downwards') {
                    chatContainer.classList.remove('flow-upwards');
                    chatContainer.classList.add('flow-downwards');
                    console.log('Chat overlay layout set to downwards (new at top).');
                } else {
                    console.warn('Invalid flow value received for set_layout:', commandData.flow);
                }
                break;
            default:
                console.warn('Unknown overlay command received:', commandData.command);
        }
    }

    // Initial connection attempt
    connectWebSocket();

})();
