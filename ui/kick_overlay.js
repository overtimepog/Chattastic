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
                    addChatMessage(message.data.user, message.data.text, message.data.emotes); // Added emotes parameter
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

    // Track random mode messages for cleanup
    const randomModeMessages = [];

    function addChatMessage(sender, messageText, emotes = []) {
        if (!chatContainer) return;

        const messageElement = document.createElement('div');
        messageElement.classList.add('chat-message');

        const senderElement = document.createElement('strong');
        senderElement.textContent = sender + ':'; // Add colon after sender
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
                    // We now have emote.id available if needed for future enhancements
                }
            });

            // Split the message by emote placeholders
            // Format is [emote:name|id] or older format [emote:name]
            // Using a regex that captures the emote name but discards the ID part
            const parts = messageText.split(/\[emote:([^\]|]+)(?:\|[^\]]+)?\]/);

            for (let i = 0; i < parts.length; i++) {
                if (i % 2 === 0) {
                    // Even indices are regular text
                    if (parts[i]) {
                        messageElement.appendChild(document.createTextNode(parts[i]));
                    }
                } else {
                    // Odd indices are emote names (ID part is discarded by the regex)
                    const emoteName = parts[i];

                    const emoteUrl = emoteMap[emoteName];

                    if (emoteUrl) {
                        // Create an image element for the emote - no brackets or IDs
                        const img = document.createElement('img');
                        img.src = emoteUrl;
                        img.alt = emoteName;
                        img.title = emoteName;
                        img.className = 'chat-emote';
                        img.style.height = '1.2em'; // Set a reasonable height
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

        // Check if we're in random mode
        if (chatContainer.classList.contains('flow-random')) {
            // Position the message randomly
            addRandomMessage(messageElement);
        } else {
            // Normal flow mode
            chatContainer.appendChild(messageElement);

            // Enforce message limit
            while (chatContainer.children.length > messageLimit) {
                chatContainer.removeChild(chatContainer.firstChild);
            }
        }
    }

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
                const shorthandRegex = /^#?([a-f\d])([a-f\d])([a-f\d])$/i;
                const fullHex = hex.replace(shorthandRegex, (m, r, g, b) => r + r + g + g + b + b);
                const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(fullHex);
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

        // Apply browser source dimensions
        if (styles.width !== undefined) {
            root.style.setProperty('--chat-width', `${styles.width}px`);
        }

        if (styles.height !== undefined) {
            root.style.setProperty('--chat-height', `${styles.height}px`);
        }

        if (styles.bottomMargin !== undefined) {
            root.style.setProperty('--chat-bottom-margin', `${styles.bottomMargin}px`);
            // Also update body padding-bottom to prevent cut-off
            document.body.style.paddingBottom = `${styles.bottomMargin}px`;
        }

        // Update current styles
        currentStyles = {...currentStyles, ...styles};
        console.log('Styles applied:', currentStyles);

        // Apply dimensions to container if in upwards mode
        adjustContainerForDimensions();
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
            case 'set_layout':
                if (commandData.flow === 'upwards') {
                    chatContainer.classList.remove('flow-downwards', 'flow-random');
                    chatContainer.classList.add('flow-upwards');
                    console.log('Chat overlay layout set to upwards (new at bottom).');
                    // Apply dimension adjustments for upwards mode
                    adjustContainerForDimensions();
                    // Clear any random mode messages
                    clearRandomMessages();
                } else if (commandData.flow === 'downwards') {
                    chatContainer.classList.remove('flow-upwards', 'flow-random');
                    chatContainer.classList.add('flow-downwards');
                    // Reset any dimension-specific styles when switching to downwards mode
                    chatContainer.style.maxHeight = '';
                    chatContainer.style.overflowY = '';
                    chatContainer.style.width = '100%';
                    console.log('Chat overlay layout set to downwards (new at top).');
                    // Clear any random mode messages
                    clearRandomMessages();
                } else if (commandData.flow === 'random') {
                    chatContainer.classList.remove('flow-upwards', 'flow-downwards');
                    chatContainer.classList.add('flow-random');
                    // Reset container styles for random mode
                    chatContainer.style.maxHeight = '';
                    chatContainer.style.overflowY = '';
                    chatContainer.style.width = '100%';
                    chatContainer.style.height = '100%';
                    chatContainer.style.position = 'relative';
                    console.log('Chat overlay layout set to random placement mode.');
                    // Clear existing messages when switching to random mode
                    chatContainer.innerHTML = '';
                    randomModeMessages.length = 0; // Clear the tracking array
                } else {
                    console.warn('Invalid flow value received for set_layout:', commandData.flow);
                }
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

    // Function to add a message with random positioning
    function addRandomMessage(messageElement) {
        // Get container dimensions
        const containerWidth = currentStyles.width;
        const containerHeight = currentStyles.height;

        // Calculate maximum position values (accounting for message size)
        // We'll estimate message size based on content and styles
        const estimatedMessageWidth = Math.min(containerWidth * 0.8, 400); // Max 80% of container width or 400px
        const estimatedMessageHeight = 50; // Rough estimate

        // Calculate random position within container bounds
        const maxX = containerWidth - estimatedMessageWidth;
        const maxY = containerHeight - estimatedMessageHeight;
        const randomX = Math.floor(Math.random() * maxX);
        const randomY = Math.floor(Math.random() * maxY);

        // Style the message for absolute positioning
        messageElement.style.position = 'absolute';
        messageElement.style.left = `${randomX}px`;
        messageElement.style.top = `${randomY}px`;
        messageElement.style.maxWidth = `${estimatedMessageWidth}px`;
        messageElement.style.opacity = '0'; // Start invisible for fade-in

        // Add animation class
        messageElement.classList.add('random-message');

        // Add to container
        chatContainer.appendChild(messageElement);

        // Track this message
        const messageInfo = {
            element: messageElement,
            timeoutId: null
        };
        randomModeMessages.push(messageInfo);

        // Enforce max messages limit
        while (randomModeMessages.length > currentStyles.randomMaxMessages) {
            removeOldestRandomMessage();
        }

        // Animate in
        setTimeout(() => {
            // Fade in
            messageElement.style.transition = `opacity ${currentStyles.randomAnimationDuration}ms ease-in`;
            messageElement.style.opacity = '1';

            // Set timeout to remove after duration
            messageInfo.timeoutId = setTimeout(() => {
                // Fade out and remove
                messageElement.style.transition = `opacity ${currentStyles.randomAnimationDuration}ms ease-out`;
                messageElement.style.opacity = '0';

                // Remove after animation completes
                setTimeout(() => {
                    removeRandomMessage(messageInfo);
                }, currentStyles.randomAnimationDuration);

            }, currentStyles.randomMessageDuration * 1000); // Convert seconds to milliseconds
        }, 10); // Small delay to ensure transition works
    }

    // Function to remove a specific random message
    function removeRandomMessage(messageInfo) {
        // Remove from DOM if still there
        if (messageInfo.element && messageInfo.element.parentNode) {
            messageInfo.element.parentNode.removeChild(messageInfo.element);
        }

        // Clear any pending timeout
        if (messageInfo.timeoutId) {
            clearTimeout(messageInfo.timeoutId);
        }

        // Remove from tracking array
        const index = randomModeMessages.indexOf(messageInfo);
        if (index !== -1) {
            randomModeMessages.splice(index, 1);
        }
    }

    // Function to remove the oldest random message
    function removeOldestRandomMessage() {
        if (randomModeMessages.length > 0) {
            removeRandomMessage(randomModeMessages[0]);
        }
    }

    // Function to clear all random messages
    function clearRandomMessages() {
        // Clear all timeouts and remove elements
        randomModeMessages.forEach(messageInfo => {
            if (messageInfo.timeoutId) {
                clearTimeout(messageInfo.timeoutId);
            }
            if (messageInfo.element && messageInfo.element.parentNode) {
                messageInfo.element.parentNode.removeChild(messageInfo.element);
            }
        });

        // Clear the array
        randomModeMessages.length = 0;
    }

    // Function to adjust container based on dimensions
    function adjustContainerForDimensions() {
        // Only apply special handling for upwards flow mode
        if (chatContainer && chatContainer.classList.contains('flow-upwards')) {
            // Set max-height based on browser source height minus bottom margin
            const maxHeight = currentStyles.height - currentStyles.bottomMargin - 20; // 20px for additional padding
            chatContainer.style.maxHeight = `${maxHeight}px`;
            chatContainer.style.overflowY = 'hidden'; // Hide overflow

            // Ensure container width matches browser source width
            chatContainer.style.width = `${currentStyles.width - 20}px`; // 20px for padding

            console.log(`Adjusted container dimensions: maxHeight=${maxHeight}px, width=${currentStyles.width - 20}px`);
        }
    }

    // Apply default styles on load
    applyStyles(defaultStyles);

    // Initial connection attempt
    connectWebSocket();

})();
