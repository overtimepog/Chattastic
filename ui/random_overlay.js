(function() {
    const chatContainer = document.getElementById('chat-container');
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws`;
    let ws = null;
    let reconnectTimeout = null;
    
    // Track active messages for cleanup
    const activeMessages = [];
    
    // Default style values
    const defaultStyles = {
        textColor: '#ffffff',
        usernameColor: '#a0a0ff',
        fontSize: 16,
        textShadow: 'on',
        bgColor: '#000000',
        bgOpacity: 0.5,
        padding: 5,
        gap: 5,
        borderRadius: 4,
        width: 800,
        height: 600,
        bottomMargin: 10,
        randomMessageDuration: 5,
        randomAnimationDuration: 500,
        randomMaxMessages: 10
    };

    // Current styles (initialize with defaults)
    let currentStyles = {...defaultStyles};

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
                
                if (message.type === 'kick_chat_message' && message.data) {
                    addChatMessage(message.data.user, message.data.text, message.data.emotes);
                } else if (message.type === 'kick_overlay_command' && message.data) {
                    handleCommand(message.data);
                }
            } catch (error) {
                console.error('Error processing WebSocket message:', error);
            }
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        ws.onclose = (event) => {
            console.log(`WebSocket closed. Code: ${event.code}, Reason: ${event.reason}. Attempting reconnect...`);
            ws = null;
            if (!reconnectTimeout) {
                reconnectTimeout = setTimeout(connectWebSocket, 5000);
            }
        };
    }

    function addChatMessage(sender, messageText, emotes = []) {
        if (!chatContainer) return;

        const messageElement = document.createElement('div');
        messageElement.classList.add('chat-message');

        const senderElement = document.createElement('strong');
        senderElement.textContent = sender + ':';
        messageElement.appendChild(senderElement);

        // Add a space after the sender
        messageElement.appendChild(document.createTextNode(' '));

        // Process message text and replace emotes with images
        if (emotes && emotes.length > 0) {
            // Create a map of emote names to their URLs for quick lookup
            const emoteMap = {};
            emotes.forEach(emote => {
                if (emote.name && emote.url) {
                    emoteMap[emote.name] = emote.url;
                }
            });

            // Split the message by emote placeholders
            // Format is [emote:name|id] or older format [emote:name]
            const parts = messageText.split(/\\[emote:([^\\]|]+)(?:\\|[^\\]]+)?\\]/);

            for (let i = 0; i < parts.length; i++) {
                if (i % 2 === 0) {
                    // Even indices are regular text
                    if (parts[i]) {
                        messageElement.appendChild(document.createTextNode(parts[i]));
                    }
                } else {
                    // Odd indices are emote names
                    const emoteName = parts[i];
                    const emoteUrl = emoteMap[emoteName];

                    if (emoteUrl) {
                        // Create an image element for the emote
                        const img = document.createElement('img');
                        img.src = emoteUrl;
                        img.alt = emoteName;
                        img.title = emoteName;
                        img.className = 'chat-emote';
                        img.style.height = '1.2em';
                        img.style.verticalAlign = 'middle';
                        messageElement.appendChild(img);
                    } else {
                        // Fallback if emote URL not found
                        messageElement.appendChild(document.createTextNode(`[${emoteName}]`));
                    }
                }
            }
        } else {
            // No emotes, just add the text
            messageElement.appendChild(document.createTextNode(messageText));
        }

        // Position the message randomly
        positionRandomMessage(messageElement);
    }

    function positionRandomMessage(messageElement) {
        // Get viewport dimensions
        const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
        const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
        
        // Add to container first (invisible) so we can measure it
        messageElement.style.opacity = '0';
        chatContainer.appendChild(messageElement);
        
        // Get actual message dimensions
        const messageWidth = messageElement.offsetWidth;
        const messageHeight = messageElement.offsetHeight;
        
        // Calculate maximum position values
        const maxX = Math.max(0, viewportWidth - messageWidth);
        const maxY = Math.max(0, viewportHeight - messageHeight);
        
        // Generate random position
        const randomX = Math.floor(Math.random() * maxX);
        const randomY = Math.floor(Math.random() * maxY);
        
        // Apply position
        messageElement.style.left = `${randomX}px`;
        messageElement.style.top = `${randomY}px`;
        
        // Track this message
        const messageInfo = {
            element: messageElement,
            timeoutId: null
        };
        activeMessages.push(messageInfo);
        
        // Enforce max messages limit
        while (activeMessages.length > currentStyles.randomMaxMessages) {
            removeOldestMessage();
        }
        
        // Animate in
        setTimeout(() => {
            // Make visible with transition
            messageElement.classList.add('visible');
            
            // Set timeout to remove after duration
            messageInfo.timeoutId = setTimeout(() => {
                // Start fade out
                messageElement.classList.remove('visible');
                
                // Remove after animation completes
                setTimeout(() => {
                    removeMessage(messageInfo);
                }, currentStyles.randomAnimationDuration);
                
            }, currentStyles.randomMessageDuration * 1000);
        }, 10);
    }

    function removeMessage(messageInfo) {
        // Remove from DOM if still there
        if (messageInfo.element && messageInfo.element.parentNode) {
            messageInfo.element.parentNode.removeChild(messageInfo.element);
        }

        // Clear any pending timeout
        if (messageInfo.timeoutId) {
            clearTimeout(messageInfo.timeoutId);
        }

        // Remove from tracking array
        const index = activeMessages.indexOf(messageInfo);
        if (index !== -1) {
            activeMessages.splice(index, 1);
        }
    }

    function removeOldestMessage() {
        if (activeMessages.length > 0) {
            removeMessage(activeMessages[0]);
        }
    }

    function clearAllMessages() {
        // Clear all timeouts and remove elements
        activeMessages.forEach(messageInfo => {
            if (messageInfo.timeoutId) {
                clearTimeout(messageInfo.timeoutId);
            }
            if (messageInfo.element && messageInfo.element.parentNode) {
                messageInfo.element.parentNode.removeChild(messageInfo.element);
            }
        });

        // Clear the array
        activeMessages.length = 0;
    }

    // Apply styles to the chat container and messages
    function applyStyles(styles) {
        // Update document root with CSS variables
        const root = document.documentElement;

        // Apply text color
        if (styles.textColor) {
            root.style.setProperty('--chat-text-color', styles.textColor);
        }

        // Apply username color
        if (styles.usernameColor) {
            root.style.setProperty('--chat-username-color', styles.usernameColor);
        }

        // Apply font size
        if (styles.fontSize) {
            root.style.setProperty('--chat-font-size', `${styles.fontSize}px`);
        }

        // Apply text shadow
        if (styles.textShadow) {
            root.style.setProperty('--chat-text-shadow', styles.textShadow === 'on' ?
                '1px 1px 2px rgba(0, 0, 0, 0.8)' : 'none');
        }

        // Apply background color and opacity
        if (styles.bgColor && styles.bgOpacity !== undefined) {
            // Convert hex color to rgba
            const hexToRgb = (hex) => {
                const shorthandRegex = /^#?([a-f\\d])([a-f\\d])([a-f\\d])$/i;
                const fullHex = hex.replace(shorthandRegex, (m, r, g, b) => r + r + g + g + b + b);
                const result = /^#?([a-f\\d]{2})([a-f\\d]{2})([a-f\\d]{2})$/i.exec(fullHex);
                return result ? {
                    r: parseInt(result[1], 16),
                    g: parseInt(result[2], 16),
                    b: parseInt(result[3], 16)
                } : {r: 0, g: 0, b: 0};
            };

            const rgb = hexToRgb(styles.bgColor);
            const rgba = `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${styles.bgOpacity})`;
            root.style.setProperty('--chat-bg-color', rgba);
        }

        // Apply padding
        if (styles.padding !== undefined) {
            root.style.setProperty('--chat-padding', `${styles.padding}px`);
        }

        // Apply gap between messages
        if (styles.gap !== undefined) {
            root.style.setProperty('--chat-gap', `${styles.gap}px`);
        }

        // Apply border radius
        if (styles.borderRadius !== undefined) {
            root.style.setProperty('--chat-border-radius', `${styles.borderRadius}px`);
        }

        // Apply animation duration
        if (styles.randomAnimationDuration !== undefined) {
            root.style.setProperty('--random-animation-duration', `${styles.randomAnimationDuration}ms`);
        }

        // Update current styles
        currentStyles = {...currentStyles, ...styles};
        console.log('Styles applied:', currentStyles);
    }

    function handleCommand(commandData) {
        console.log('Handling command:', commandData);
        if (!chatContainer) return;

        switch (commandData.command) {
            case 'clear':
                clearAllMessages();
                console.log('Chat overlay cleared.');
                break;
            case 'set_styles':
                if (commandData.styles && typeof commandData.styles === 'object') {
                    applyStyles(commandData.styles);
                } else {
                    console.warn('Invalid styles data received:', commandData.styles);
                }
                break;
            case 'reset_styles':
                applyStyles(defaultStyles);
                console.log('Styles reset to defaults');
                break;
            default:
                console.warn('Unknown overlay command received:', commandData.command);
        }
    }

    // Apply default styles on load
    applyStyles(defaultStyles);

    // Initial connection attempt
    connectWebSocket();
})();
