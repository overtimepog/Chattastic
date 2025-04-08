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
                if (message.data.raffle_entries_count !== undefined) {
                    document.getElementById('raffle-entries-count').textContent = `Raffle Entries: ${message.data.raffle_entries_count}`;
                }
                break;
            case 'twitch_chat_message':
                addChatMessage(`Twitch (${message.data.channel}): ${message.data.user}: ${message.data.text}`);
                break;
            case 'kick_chat_message':
                // Use the new formatter function
                const formattedMessage = formatKickMessage(message.data);
                addChatMessage(formattedMessage);
                console.log('Formatted Kick message:', formattedMessage); // Debug log
                break;
            case 'viewer_list_update':
                updateViewerList(message.data.viewers);
                break;
            case 'selected_viewers_update':
                updateSelectedViewers(message.data.selected_viewers);
                break;
            case 'kick_chat_connected': // Add handler for connection confirmation
                addChatMessage(`System: Connected to Kick chat for ${escapeHTML(message.data.channel || 'Unknown')}`);
                // Optionally update a status indicator if needed
                currentKickChannel.textContent = message.data.channel || 'None'; // Update channel display
                break;
            case 'raffle_entry':
                addChatMessage(`System: ${escapeHTML(message.data.user)} entered the raffle from ${message.data.platform}. Total entries: ${message.data.total_entries}`);
                document.getElementById('raffle-entries-count').textContent = `Raffle Entries: ${message.data.total_entries}`;
                break;
            case 'raffle_entries_cleared':
                addChatMessage(`System: Raffle entries cleared. Total entries: 0`);
                document.getElementById('raffle-entries-count').textContent = 'Raffle Entries: 0';
                break;
            case 'error':
                 addChatMessage(`System Error: ${message.data.message}`);
                 console.error("Server Error:", message.data.message);
                 break;
            case 'kick_overlay_message': // Intentionally ignore this type in the main UI
                 console.log('Ignoring kick_overlay_message in main UI.');
                 break;
            default:
                console.warn('Received unknown message type:', message.type);
                addChatMessage(`System: Received unknown message type: ${escapeHTML(message.type)}`); // Escape type just in case
        }
    }

    function updateAuthStatus(platform, isAuthenticated) {
        const element = platform === 'twitch' ? twitchAuthStatus : kickAuthStatus;
        if (element) {
            element.textContent = isAuthenticated ? 'Yes' : 'No';
            element.className = isAuthenticated ? 'authenticated' : 'not-authenticated';
        }
    }

    // Function to format Kick messages with badges and emotes
    function formatKickMessage(data) {
        console.log('Formatting Kick message:', data); // Debug log

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

        // Escape username to prevent XSS
        const username = escapeHTML(data.user || 'Unknown'); // Use data.user
        const channel = escapeHTML(data.channel || 'kick');

        // Process content with emotes
        let contentHTML = '';
        const messageText = data.text || '';
        const emotes = data.emotes || [];

        console.log('Message text:', messageText); // Debug log
        console.log('Emotes:', emotes); // Debug log

        if (emotes && emotes.length > 0) {
            // Create a map of emote names to their URLs for quick lookup
            const emoteMap = {};
            emotes.forEach(emote => {
                if (emote.name && emote.url) {
                    emoteMap[emote.name] = emote.url;
                    console.log(`Mapped emote: ${emote.name} -> ${emote.url} (ID: ${emote.id || 'none'})`); // Debug log
                }
            });

            // Split the message by emote placeholders
            // Format is [emote:name|id] or older format [emote:name]
            // Using a regex that captures the emote name but discards the ID part
            const parts = messageText.split(/\[emote:([^\]|]+)(?:\|[^\]]+)?\]/);
            console.log('Split parts:', parts); // Debug log

            for (let i = 0; i < parts.length; i++) {
                if (i % 2 === 0) {
                    // Even indices are regular text
                    if (parts[i]) {
                        contentHTML += escapeHTML(parts[i]);
                    }
                } else {
                    // Odd indices are emote names (ID part is discarded by the regex)
                    const emoteName = parts[i];

                    const emoteUrl = emoteMap[emoteName];
                    console.log(`Processing emote: ${emoteName}, URL: ${emoteUrl}`); // Debug log

                    if (emoteUrl) {
                        // Create an image element for the emote - no brackets or IDs
                        contentHTML += `<img src="${emoteUrl}" alt="${escapeHTML(emoteName)}" title="${escapeHTML(emoteName)}" class="chat-emote" style="height: 1.2em; vertical-align: middle;">`;
                    } else {
                        // Fallback if emote URL not found
                        contentHTML += `[${escapeHTML(emoteName)}]`;
                    }
                }
            }
        } else {
            // No emotes, just escape the text
            contentHTML = escapeHTML(messageText);
        }

        console.log('Final content HTML:', contentHTML); // Debug log
        return `<p>Kick (${channel}): ${badgesHTML}<strong>${username}</strong>: ${contentHTML}</p>`;
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
        const useRaffle = document.getElementById('raffle-mode').checked;

        // Determine which platform to use based on current connections
        let platform = 'twitch'; // Default to twitch
        if (currentKickChannel.textContent !== 'None') {
            platform = 'kick';
        }

        sendMessage({
            type: 'select_random_viewers',
            data: {
                count: parseInt(count, 10),
                use_raffle: useRaffle,
                platform: platform
            }
        });

        // Log the selection request
        console.log(`Selecting ${count} viewers from ${platform} using ${useRaffle ? 'raffle' : 'random'} mode`);
    });

    // Clear raffle entries button
    document.getElementById('clear-raffle-entries-btn').addEventListener('click', () => {
        sendMessage({ type: 'clear_raffle_entries' });
        console.log('Clear raffle entries message sent');
    });

    // Speak selected viewers button (placeholder)
    document.getElementById('speak-selected-btn').addEventListener('click', () => {
        sendMessage({ type: 'trigger_speak_selected' });
        console.log('Trigger speak selected message sent');
    });

    // --- Kick Overlay Control Listeners ---
    const clearKickOverlayBtn = document.getElementById('clear-kick-overlay-btn');
    const setKickOverlayLimitBtn = document.getElementById('set-kick-overlay-limit-btn');
    const kickOverlayLimitInput = document.getElementById('kick-overlay-limit-input');

    if (clearKickOverlayBtn) {
        clearKickOverlayBtn.addEventListener('click', () => {
            console.log('Sending clear overlay command...');
            sendMessage({ type: 'control_kick_overlay', data: { action: 'clear' } });
        });
    } else {
        console.error('Clear Kick Overlay button not found');
    }

    if (setKickOverlayLimitBtn && kickOverlayLimitInput) {
        setKickOverlayLimitBtn.addEventListener('click', () => {
            const limit = parseInt(kickOverlayLimitInput.value, 10);
            if (!isNaN(limit) && limit > 0) {
                console.log(`Sending set overlay limit command: ${limit}`);
                sendMessage({ type: 'control_kick_overlay', data: { action: 'set_limit', value: limit } });
            } else {
                console.error('Invalid limit value entered.');
                alert('Please enter a valid positive number for the message limit.');
            }
        });
    } else {
        console.error('Set Kick Overlay Limit button or input not found');
    }

    // Message Flow Radio Buttons
    const flowRadios = document.querySelectorAll('input[name="kick-overlay-flow"]');
    flowRadios.forEach(radio => {
        radio.addEventListener('change', (event) => {
            if (event.target.checked) {
                const flowDirection = event.target.value;
                console.log(`Sending set overlay layout command: flow=${flowDirection}`);
                sendMessage({ type: 'control_kick_overlay', data: { action: 'set_layout', flow: flowDirection } });

                // Show/hide random mode settings based on selected flow
                if (randomModeSettings) {
                    randomModeSettings.style.display = flowDirection === 'random' ? 'block' : 'none';
                }
            }
        });
    });

    // Initialize random mode settings visibility
    if (randomModeSettings) {
        const randomFlowSelected = document.getElementById('flow-random') && document.getElementById('flow-random').checked;
        randomModeSettings.style.display = randomFlowSelected ? 'block' : 'none';
    }

    // Show Overlay URL Button
    const showUrlBtn = document.getElementById('show-overlay-url-btn');
    const urlDisplay = document.getElementById('overlay-url-display');

    if (showUrlBtn && urlDisplay) {
        showUrlBtn.addEventListener('click', () => {
            const overlayUrl = `http://${window.location.host}/kick-overlay`;
            urlDisplay.textContent = overlayUrl;
            urlDisplay.style.display = 'block'; // Make it visible
        });
    } else {
        console.error('Show Overlay URL button or display element not found');
    }

    // --- Overlay Appearance Customization ---
    // Get all the customization controls
    const textColorInput = document.getElementById('overlay-text-color');
    const usernameColorInput = document.getElementById('overlay-username-color');
    const fontSizeInput = document.getElementById('overlay-font-size');
    const textShadowSelect = document.getElementById('overlay-text-shadow');
    const bgColorInput = document.getElementById('overlay-bg-color');
    const bgOpacityInput = document.getElementById('overlay-bg-opacity');
    const bgOpacityValue = document.getElementById('overlay-bg-opacity-value');
    const paddingInput = document.getElementById('overlay-padding');
    const gapInput = document.getElementById('overlay-gap');
    const borderRadiusInput = document.getElementById('overlay-border-radius');
    const widthInput = document.getElementById('overlay-width');
    const heightInput = document.getElementById('overlay-height');
    const bottomMarginInput = document.getElementById('overlay-bottom-margin');
    const applyStylesBtn = document.getElementById('apply-overlay-styles-btn');
    const resetStylesBtn = document.getElementById('reset-overlay-styles-btn');

    // Random mode settings
    const randomModeSettings = document.getElementById('random-mode-settings');
    const randomMessageDuration = document.getElementById('random-message-duration');
    const randomAnimationDuration = document.getElementById('random-animation-duration');
    const randomMaxMessages = document.getElementById('random-max-messages');

    // Update the opacity value display when the slider changes
    if (bgOpacityInput && bgOpacityValue) {
        bgOpacityInput.addEventListener('input', () => {
            bgOpacityValue.textContent = bgOpacityInput.value;
        });
    }

    // Apply styles button
    if (applyStylesBtn) {
        applyStylesBtn.addEventListener('click', () => {
            // Collect all the style values
            const styles = {
                textColor: textColorInput ? textColorInput.value : '#ffffff',
                usernameColor: usernameColorInput ? usernameColorInput.value : '#a0a0ff',
                fontSize: fontSizeInput ? parseInt(fontSizeInput.value, 10) : 16,
                textShadow: textShadowSelect ? textShadowSelect.value : 'on',
                bgColor: bgColorInput ? bgColorInput.value : '#000000',
                bgOpacity: bgOpacityInput ? parseFloat(bgOpacityInput.value) : 0.5,
                padding: paddingInput ? parseInt(paddingInput.value, 10) : 5,
                gap: gapInput ? parseInt(gapInput.value, 10) : 5,
                borderRadius: borderRadiusInput ? parseInt(borderRadiusInput.value, 10) : 4,
                // Add browser source dimensions
                width: widthInput ? parseInt(widthInput.value, 10) : 800,
                height: heightInput ? parseInt(heightInput.value, 10) : 600,
                bottomMargin: bottomMarginInput ? parseInt(bottomMarginInput.value, 10) : 10,
                // Add random mode settings
                randomMessageDuration: randomMessageDuration ? parseInt(randomMessageDuration.value, 10) : 5,
                randomAnimationDuration: randomAnimationDuration ? parseInt(randomAnimationDuration.value, 10) : 500,
                randomMaxMessages: randomMaxMessages ? parseInt(randomMaxMessages.value, 10) : 10
            };

            console.log('Applying overlay styles:', styles);
            sendMessage({
                type: 'control_kick_overlay',
                data: {
                    action: 'set_styles',
                    styles: styles
                }
            });
        });
    } else {
        console.error('Apply Overlay Styles button not found');
    }

    // Reset styles button
    if (resetStylesBtn) {
        resetStylesBtn.addEventListener('click', () => {
            // Reset all inputs to their default values
            if (textColorInput) textColorInput.value = '#ffffff';
            if (usernameColorInput) usernameColorInput.value = '#a0a0ff';
            if (fontSizeInput) fontSizeInput.value = '16';
            if (textShadowSelect) textShadowSelect.value = 'on';
            if (bgColorInput) bgColorInput.value = '#000000';
            if (bgOpacityInput) {
                bgOpacityInput.value = '0.5';
                if (bgOpacityValue) bgOpacityValue.textContent = '0.5';
            }
            if (paddingInput) paddingInput.value = '5';
            if (gapInput) gapInput.value = '5';
            if (borderRadiusInput) borderRadiusInput.value = '4';
            // Reset browser source dimensions
            if (widthInput) widthInput.value = '800';
            if (heightInput) heightInput.value = '600';
            if (bottomMarginInput) bottomMarginInput.value = '10';

            // Reset random mode settings
            if (randomMessageDuration) randomMessageDuration.value = '5';
            if (randomAnimationDuration) randomAnimationDuration.value = '500';
            if (randomMaxMessages) randomMaxMessages.value = '10';

            // Send reset command to server
            console.log('Resetting overlay styles to defaults');
            sendMessage({
                type: 'control_kick_overlay',
                data: {
                    action: 'reset_styles'
                }
            });
        });
    } else {
        console.error('Reset Overlay Styles button not found');
    }
    // --- End Overlay Appearance Customization ---

    // --- End Kick Overlay Control Listeners ---

    // Initial connection
    connectWebSocket();
});
