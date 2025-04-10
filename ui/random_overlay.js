(function() {
    const chatContainer = document.getElementById('chat-container');
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws`;
    let ws = null;
    let reconnectTimeout = null;

    // Track active messages for cleanup
    const activeMessages = [];

    // Track displayed message IDs to prevent duplicates
    const displayedMessageIds = new Set();

    // Message queue for pending messages
    const messageQueue = [];

    // Maximum number of messages to keep in history
    const MAX_MESSAGE_HISTORY = 200;

    // Maximum attempts to find non-overlapping position
    const MAX_PLACEMENT_ATTEMPTS = 50;

    // Margin between messages (in pixels) to prevent them from being too close
    const MESSAGE_MARGIN = 10;

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
        randomMaxMessages: 10,
        debugMode: false // Set to true to visualize message boundaries
    };

    // Current styles (initialize with defaults)
    let currentStyles = {...defaultStyles};

    // Process the next message from the queue
    function processNextMessage() {
        // If there are no messages in the queue, do nothing
        if (messageQueue.length === 0) return;

        // Get the next message from the queue
        const message = messageQueue.shift();

        // Display the message
        displayChatMessage(message.user, message.text, message.emotes);
    }

    // Display a chat message in the overlay
    function displayChatMessage(sender, messageText, emotes = []) {
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
            const parts = messageText.split(/\[emote:([^\]|]+)(?:\|[^\]]+)?\]/);

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
                    // Generate a unique ID for the message if not provided
                    const messageId = message.data.id ||
                        `${message.data.user}_${message.data.text}_${message.data.timestamp || Date.now()}`;

                    // Only process if we haven't shown this message before
                    if (!displayedMessageIds.has(messageId)) {
                        // Add to our tracking set
                        displayedMessageIds.add(messageId);

                        // Add to queue for processing
                        messageQueue.push({
                            id: messageId,
                            user: message.data.user,
                            text: message.data.text,
                            emotes: message.data.emotes,
                            timestamp: message.data.timestamp || Date.now()
                        });

                        // Process the next message from queue
                        processNextMessage();

                        // Limit the size of our tracking set to prevent memory issues
                        if (displayedMessageIds.size > MAX_MESSAGE_HISTORY) {
                            // Convert to array, remove oldest entries, convert back to set
                            const idsArray = Array.from(displayedMessageIds);
                            displayedMessageIds.clear();
                            idsArray.slice(-MAX_MESSAGE_HISTORY).forEach(id => displayedMessageIds.add(id));
                        }
                    }
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

    // Legacy function for backward compatibility
    function addChatMessage(sender, messageText, emotes = []) {
        // Generate a unique ID for the message
        const messageId = `${sender}_${messageText}_${Date.now()}`;

        // Only process if we haven't shown this message before
        if (!displayedMessageIds.has(messageId)) {
            // Add to our tracking set
            displayedMessageIds.add(messageId);

            // Display the message directly
            displayChatMessage(sender, messageText, emotes);
        }
    }

    // Check if two rectangles overlap
    function doRectanglesOverlap(rect1, rect2) {
        // Check if one rectangle is to the left of the other
        if (rect1.x + rect1.width < rect2.x || rect2.x + rect2.width < rect1.x) {
            return false;
        }

        // Check if one rectangle is above the other
        if (rect1.y + rect1.height < rect2.y || rect2.y + rect2.height < rect1.y) {
            return false;
        }

        // If neither of the above conditions is true, the rectangles overlap
        return true;
    }

    // Check if a position overlaps with any active message
    function checkForOverlap(x, y, width, height) {
        // Add margin to the rectangle to ensure messages aren't too close
        const newRect = {
            x: x - MESSAGE_MARGIN,
            y: y - MESSAGE_MARGIN,
            width: width + (MESSAGE_MARGIN * 2),
            height: height + (MESSAGE_MARGIN * 2)
        };

        for (const messageInfo of activeMessages) {
            if (!messageInfo.rect) continue; // Skip if no rect info

            if (doRectanglesOverlap(newRect, messageInfo.rect)) {
                return true; // Overlap detected
            }
        }

        return false; // No overlap
    }

    // Find a non-overlapping position for a new message
    function findNonOverlappingPosition(width, height, maxX, maxY) {
        // First strategy: Try completely random positions
        for (let attempt = 0; attempt < Math.min(20, MAX_PLACEMENT_ATTEMPTS); attempt++) {
            const x = Math.floor(Math.random() * maxX);
            const y = Math.floor(Math.random() * maxY);

            if (!checkForOverlap(x, y, width, height)) {
                return { x, y }; // Found a non-overlapping position
            }
        }

        // Second strategy: Try to place in quadrants with fewer messages
        // Divide the screen into quadrants and count messages in each
        const quadrants = [
            { x: 0, y: 0, count: 0 },                  // Top-left
            { x: maxX / 2, y: 0, count: 0 },            // Top-right
            { x: 0, y: maxY / 2, count: 0 },            // Bottom-left
            { x: maxX / 2, y: maxY / 2, count: 0 }      // Bottom-right
        ];

        // Count messages in each quadrant
        for (const messageInfo of activeMessages) {
            if (!messageInfo.rect) continue;

            const rect = messageInfo.rect;
            const centerX = rect.x + rect.width / 2;
            const centerY = rect.y + rect.height / 2;

            // Determine which quadrant this message is in
            const quadrantIndex = (centerX >= maxX / 2 ? 1 : 0) + (centerY >= maxY / 2 ? 2 : 0);
            quadrants[quadrantIndex].count++;
        }

        // Sort quadrants by message count (ascending)
        quadrants.sort((a, b) => a.count - b.count);

        // Try positions in the least crowded quadrants first
        for (const quadrant of quadrants) {
            const quadWidth = maxX / 2;
            const quadHeight = maxY / 2;

            // Try several positions within this quadrant
            for (let attempt = 0; attempt < 10; attempt++) {
                const x = Math.floor(quadrant.x + Math.random() * (quadWidth - width));
                const y = Math.floor(quadrant.y + Math.random() * (quadHeight - height));

                if (!checkForOverlap(x, y, width, height)) {
                    return { x, y }; // Found a non-overlapping position
                }
            }
        }

        // Third strategy: Grid-based approach with minimal overlap
        console.log('Could not find non-overlapping position, trying grid approach');

        // Create a grid of potential positions and check each one
        const gridSize = 5; // 5x5 grid
        const cellWidth = maxX / gridSize;
        const cellHeight = maxY / gridSize;

        let bestPosition = { x: 0, y: 0 };
        let minOverlapCount = Number.MAX_SAFE_INTEGER;

        // Try each cell in the grid
        for (let i = 0; i < gridSize; i++) {
            for (let j = 0; j < gridSize; j++) {
                const x = Math.floor(i * cellWidth);
                const y = Math.floor(j * cellHeight);

                // Count how many overlaps this position has
                let overlapCount = 0;
                const testRect = { x, y, width, height };

                for (const messageInfo of activeMessages) {
                    if (!messageInfo.rect) continue;
                    if (doRectanglesOverlap(testRect, messageInfo.rect)) {
                        overlapCount++;
                    }
                }

                // If this position has fewer overlaps, use it
                if (overlapCount < minOverlapCount) {
                    minOverlapCount = overlapCount;
                    bestPosition = { x, y };

                    // If we found a position with no overlaps, use it immediately
                    if (overlapCount === 0) {
                        return bestPosition;
                    }
                }
            }
        }

        // Add some randomness to the best position to avoid stacking
        bestPosition.x += Math.floor(Math.random() * 20) - 10;
        bestPosition.y += Math.floor(Math.random() * 20) - 10;

        // Ensure the position is within bounds
        bestPosition.x = Math.max(0, Math.min(maxX, bestPosition.x));
        bestPosition.y = Math.max(0, Math.min(maxY, bestPosition.y));

        return bestPosition;
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

        // Find a position that doesn't overlap with existing messages
        const position = findNonOverlappingPosition(messageWidth, messageHeight, maxX, maxY);

        // Apply position
        messageElement.style.left = `${position.x}px`;
        messageElement.style.top = `${position.y}px`;

        // Track this message with its position and dimensions
        const messageInfo = {
            element: messageElement,
            timeoutId: null,
            rect: {
                x: position.x,
                y: position.y,
                width: messageWidth,
                height: messageHeight
            }
        };
        activeMessages.push(messageInfo);

        // If debug mode is enabled, visualize the message boundaries
        if (currentStyles.debugMode) {
            // Create a debug outline element
            const debugOutline = document.createElement('div');
            debugOutline.classList.add('debug-outline');
            debugOutline.style.position = 'absolute';
            debugOutline.style.left = `${position.x - MESSAGE_MARGIN}px`;
            debugOutline.style.top = `${position.y - MESSAGE_MARGIN}px`;
            debugOutline.style.width = `${messageWidth + (MESSAGE_MARGIN * 2)}px`;
            debugOutline.style.height = `${messageHeight + (MESSAGE_MARGIN * 2)}px`;
            debugOutline.style.border = '1px dashed rgba(255, 0, 0, 0.5)';
            debugOutline.style.pointerEvents = 'none'; // Don't interfere with mouse events
            debugOutline.style.zIndex = '9'; // Below the actual message
            chatContainer.appendChild(debugOutline);

            // Store reference to the debug outline for cleanup
            messageInfo.debugElement = debugOutline;
        }

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

        // Remove debug outline if it exists
        if (messageInfo.debugElement && messageInfo.debugElement.parentNode) {
            messageInfo.debugElement.parentNode.removeChild(messageInfo.debugElement);
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
            case 'toggle_debug':
                // Toggle debug mode
                const newDebugMode = !currentStyles.debugMode;
                applyStyles({ debugMode: newDebugMode });
                console.log('Debug mode ' + (newDebugMode ? 'enabled' : 'disabled'));
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
