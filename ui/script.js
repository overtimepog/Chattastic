document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM content loaded, initializing UI elements');

    // Get UI elements
    const wsStatus = document.getElementById('ws-status');
    const twitchAuthStatus = document.getElementById('twitch-auth-status');
    const kickAuthStatus = document.getElementById('kick-auth-status');
    const chatMessages = document.getElementById('chat-messages');
    const allViewersList = document.getElementById('all-viewers-list');
    const selectedViewersList = document.getElementById('selected-viewers-list');
    const currentTwitchChannel = document.getElementById('current-twitch-channel');
    const currentKickChannel = document.getElementById('current-kick-channel');
    const raffleEntriesCount = document.getElementById('raffle-entries-count');

    let socket;

    // Connect to WebSocket
    function connectWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws`;
        console.log(`Connecting to WebSocket: ${wsUrl}`);

        try {
            socket = new WebSocket(wsUrl);

            socket.onopen = () => {
                console.log('WebSocket connected');
                if (wsStatus) {
                    wsStatus.textContent = 'Connected';
                    wsStatus.className = 'connected';
                }

                // Request initial status
                setTimeout(() => {
                    console.log('Requesting initial status');
                    sendMessage({ type: 'get_initial_status' });
                }, 500);
            };

            socket.onmessage = (event) => {
                // Only log non-screenshot messages to avoid console spam
                if (!event.data.includes('screenshot_update')) {
                    console.log('Received message:', event.data);
                }
                try {
                    const message = JSON.parse(event.data);
                    handleMessage(message);
                } catch (error) {
                    console.error('Error parsing message:', error);
                    console.error('Raw message data:', event.data);
                }
            };

            socket.onerror = (error) => {
                console.error('WebSocket error:', error);
                if (wsStatus) {
                    wsStatus.textContent = 'Error';
                    wsStatus.className = 'disconnected';
                }
            };

            socket.onclose = () => {
                console.log('WebSocket closed');
                if (wsStatus) {
                    wsStatus.textContent = 'Disconnected';
                    wsStatus.className = 'disconnected';
                }

                // Try to reconnect
                setTimeout(connectWebSocket, 5000);
            };
        } catch (error) {
            console.error('Error creating WebSocket:', error);
        }
    }

    // Send message to server
    function sendMessage(message) {
        if (socket && socket.readyState === WebSocket.OPEN) {
            const messageStr = JSON.stringify(message);
            console.log('Sending message:', messageStr);
            socket.send(messageStr);
        } else {
            console.error('WebSocket not connected');
        }
    }

    // Handle incoming messages
    function handleMessage(message) {
        // Only log non-screenshot messages to avoid console spam
        if (message.type !== 'screenshot_update') {
            console.log('Handling message:', message);
        }

        switch (message.type) {
            case 'initial_status':
            case 'status_update':
                handleStatusUpdate(message.data);
                break;

            case 'twitch_chat_message':
                addChatMessage(`Twitch (${message.data.channel}): ${message.data.user}: ${message.data.text}`);
                break;

            case 'kick_chat_message':
                const formattedMessage = formatKickMessage(message.data);
                addChatMessage(formattedMessage);
                break;

            case 'viewer_list_update':
                updateViewerList(message.data.viewers);
                break;

            case 'selected_viewers_update':
                updateSelectedViewers(message.data.selected_viewers);
                break;

            case 'kick_chat_connected':
                addChatMessage(`System: Connected to Kick chat for ${escapeHTML(message.data.channel || 'Unknown')}`);
                if (currentKickChannel) {
                    currentKickChannel.textContent = message.data.channel || 'None';
                }
                break;

            case 'raffle_entry':
                addChatMessage(`System: ${escapeHTML(message.data.user)} entered the raffle from ${message.data.platform}. Total entries: ${message.data.total_entries}`);
                if (raffleEntriesCount) {
                    raffleEntriesCount.textContent = `Raffle Entries: ${message.data.total_entries}`;
                }
                break;

            case 'raffle_entries_cleared':
                addChatMessage(`System: Raffle entries cleared. Total entries: 0`);
                if (raffleEntriesCount) {
                    raffleEntriesCount.textContent = 'Raffle Entries: 0';
                }
                break;

            case 'screenshot_update':
                // Handle screenshot updates
                updateDesktopScreenshot(message.data);
                break;

            case 'error':
                addChatMessage(`System Error: ${message.data.message}`);
                console.error('Server error:', message.data.message);
                break;

            default:
                console.warn('Unknown message type:', message.type);
                break;
        }
    }

    // Handle status updates
    function handleStatusUpdate(data) {
        console.log('Status update:', data);

        // Update Twitch status
        if (twitchAuthStatus) {
            const twitchAuth = Boolean(data.twitch_authenticated);
            twitchAuthStatus.textContent = twitchAuth ? 'Yes' : 'No';
            twitchAuthStatus.className = twitchAuth ? 'authenticated' : 'not-authenticated';
        }

        // Update Kick status
        if (kickAuthStatus) {
            const kickAuth = Boolean(data.kick_authenticated);
            kickAuthStatus.textContent = kickAuth ? 'Yes' : 'No';
            kickAuthStatus.className = kickAuth ? 'authenticated' : 'not-authenticated';
        }

        // Update channel info
        if (currentTwitchChannel) {
            currentTwitchChannel.textContent = data.twitch_channel || 'None';
        }

        if (currentKickChannel) {
            currentKickChannel.textContent = data.kick_channel || 'None';
        }

        // Update raffle entries
        if (raffleEntriesCount && data.raffle_entries_count !== undefined) {
            raffleEntriesCount.textContent = `Raffle Entries: ${data.raffle_entries_count}`;
        }
    }

    // Format Kick messages with emotes
    function formatKickMessage(data) {
        console.log('Formatting Kick message:', data);

        let badgesHTML = '';
        if (data.identity && Array.isArray(data.identity)) {
            data.identity.forEach(badge => {
                if (badge.type) {
                    badgesHTML += `<span class="badge badge-${badge.type.toLowerCase()}">[${badge.type.toUpperCase()}]</span> `;
                }
            });
        }

        const username = escapeHTML(data.user || 'Unknown');
        const channel = escapeHTML(data.channel || 'kick');

        let contentHTML = '';
        const messageText = data.text || '';
        const emotes = data.emotes || [];

        if (emotes.length > 0) {
            const emoteMap = {};
            emotes.forEach(emote => {
                if (emote.name && emote.url) {
                    emoteMap[emote.name] = emote.url;
                }
            });

            // Split by emote placeholders
            const parts = messageText.split(/\[emote:([^\]|]+)(?:\|[^\]]+)?\]/);

            for (let i = 0; i < parts.length; i++) {
                if (i % 2 === 0) {
                    // Regular text
                    if (parts[i]) {
                        contentHTML += escapeHTML(parts[i]);
                    }
                } else {
                    // Emote
                    const emoteName = parts[i];
                    const emoteUrl = emoteMap[emoteName];

                    if (emoteUrl) {
                        contentHTML += `<img src="${emoteUrl}" alt="${escapeHTML(emoteName)}" title="${escapeHTML(emoteName)}" class="chat-emote" style="height: 1.2em; vertical-align: middle;">`;
                    } else {
                        contentHTML += `[${escapeHTML(emoteName)}]`;
                    }
                }
            }
        } else {
            contentHTML = escapeHTML(messageText);
        }

        return `<p>Kick (${channel}): ${badgesHTML}<strong>${username}</strong>: ${contentHTML}</p>`;
    }

    // Add chat message to UI
    function addChatMessage(messageHTML) {
        const messageElement = document.createElement('div');
        messageElement.innerHTML = messageHTML;

        if (chatMessages && messageElement.firstChild) {
            chatMessages.appendChild(messageElement.firstChild);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }

    // Update viewer list
    function updateViewerList(viewers) {
        if (allViewersList) {
            allViewersList.innerHTML = '';
            viewers.forEach(viewer => {
                const li = document.createElement('li');
                li.textContent = viewer;
                allViewersList.appendChild(li);
            });
        }
    }

    // Update selected viewers
    function updateSelectedViewers(viewers) {
        if (selectedViewersList) {
            selectedViewersList.innerHTML = '';
            viewers.forEach(viewer => {
                const li = document.createElement('li');
                li.textContent = viewer;
                selectedViewersList.appendChild(li);
            });
        }
    }

    // Escape HTML to prevent XSS
    function escapeHTML(str) {
        if (!str) return '';
        return str.toString().replace(/[&<>"']/g, match => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        })[match]);
    }

    // Set up event listeners

    // Authentication buttons
    document.getElementById('auth-twitch-btn').addEventListener('click', () => {
        window.location.href = '/api/auth/twitch/login';
    });

    document.getElementById('auth-kick-btn').addEventListener('click', () => {
        window.location.href = '/api/auth/kick/login';
    });

    // Connect chat buttons
    document.getElementById('connect-twitch-chat-btn').addEventListener('click', () => {
        const channel = document.getElementById('channel-input').value;
        if (channel) {
            sendMessage({ type: 'connect_twitch_chat', data: { channel } });
        } else {
            alert('Please enter a Twitch channel name.');
        }
    });

    document.getElementById('connect-kick-chat-btn').addEventListener('click', () => {
        const channel = document.getElementById('channel-input').value;
        if (channel) {
            if (chatMessages) chatMessages.innerHTML = '';
            sendMessage({ type: 'connect_kick_chat', data: { channel } });
        } else {
            alert('Please enter a Kick channel name.');
        }
    });

    // Select random viewers button
    document.getElementById('select-random-viewers-btn').addEventListener('click', () => {
        const count = document.getElementById('viewer-count-select').value;
        const useRaffle = document.getElementById('raffle-mode').checked;

        let platform = 'twitch';
        if (currentKickChannel && currentKickChannel.textContent !== 'None') {
            platform = 'kick';
        }

        sendMessage({
            type: 'select_random_viewers',
            data: {
                count: parseInt(count, 10),
                use_raffle: useRaffle,
                platform
            }
        });
    });

    // Clear raffle entries button
    document.getElementById('clear-raffle-entries-btn').addEventListener('click', () => {
        sendMessage({ type: 'clear_raffle_entries' });
    });

    // Speak selected viewers button
    document.getElementById('speak-selected-btn').addEventListener('click', () => {
        sendMessage({ type: 'trigger_speak_selected' });
    });

    // Kick overlay control
    const clearKickOverlayBtn = document.getElementById('clear-kick-overlay-btn');
    if (clearKickOverlayBtn) {
        clearKickOverlayBtn.addEventListener('click', () => {
            sendMessage({ type: 'control_kick_overlay', data: { action: 'clear' } });
        });
    }

    const setKickOverlayLimitBtn = document.getElementById('set-kick-overlay-limit-btn');
    const kickOverlayLimitInput = document.getElementById('kick-overlay-limit-input');
    if (setKickOverlayLimitBtn && kickOverlayLimitInput) {
        setKickOverlayLimitBtn.addEventListener('click', () => {
            const limit = parseInt(kickOverlayLimitInput.value, 10);
            if (!isNaN(limit) && limit > 0) {
                sendMessage({
                    type: 'control_kick_overlay',
                    data: { action: 'set_limit', value: limit }
                });
            } else {
                alert('Please enter a valid positive number for the message limit.');
            }
        });
    }

    // Message flow radio buttons
    const flowRadios = document.querySelectorAll('input[name="kick-overlay-flow"]');
    const randomModeSettings = document.getElementById('random-mode-settings');

    flowRadios.forEach(radio => {
        radio.addEventListener('change', (event) => {
            if (event.target.checked) {
                const flowDirection = event.target.value;
                sendMessage({
                    type: 'control_kick_overlay',
                    data: { action: 'set_layout', flow: flowDirection }
                });

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

    // Show overlay URL buttons
    const showUrlBtn = document.getElementById('show-overlay-url-btn');
    const showRandomUrlBtn = document.getElementById('show-random-overlay-url-btn');
    const urlDisplay = document.getElementById('overlay-url-display');

    if (showUrlBtn && urlDisplay) {
        showUrlBtn.addEventListener('click', () => {
            const overlayUrl = `http://${window.location.host}/kick-overlay`;
            urlDisplay.textContent = overlayUrl;
            urlDisplay.style.display = 'block';
        });
    }

    if (showRandomUrlBtn && urlDisplay) {
        showRandomUrlBtn.addEventListener('click', () => {
            const randomOverlayUrl = `http://${window.location.host}/random-overlay`;
            urlDisplay.textContent = randomOverlayUrl;
            urlDisplay.style.display = 'block';
        });
    }

    // Apply overlay styles button
    const applyStylesBtn = document.getElementById('apply-overlay-styles-btn');
    if (applyStylesBtn) {
        applyStylesBtn.addEventListener('click', () => {
            const styles = {
                textColor: document.getElementById('overlay-text-color')?.value || '#ffffff',
                usernameColor: document.getElementById('overlay-username-color')?.value || '#a0a0ff',
                fontSize: parseInt(document.getElementById('overlay-font-size')?.value || '16', 10),
                textShadow: document.getElementById('overlay-text-shadow')?.value || 'on',
                bgColor: document.getElementById('overlay-bg-color')?.value || '#000000',
                bgOpacity: parseFloat(document.getElementById('overlay-bg-opacity')?.value || '0.5'),
                padding: parseInt(document.getElementById('overlay-padding')?.value || '5', 10),
                gap: parseInt(document.getElementById('overlay-gap')?.value || '5', 10),
                borderRadius: parseInt(document.getElementById('overlay-border-radius')?.value || '4', 10),
                width: parseInt(document.getElementById('overlay-width')?.value || '800', 10),
                height: parseInt(document.getElementById('overlay-height')?.value || '600', 10),
                bottomMargin: parseInt(document.getElementById('overlay-bottom-margin')?.value || '10', 10),
                randomMessageDuration: parseInt(document.getElementById('random-message-duration')?.value || '5', 10),
                randomAnimationDuration: parseInt(document.getElementById('random-animation-duration')?.value || '500', 10),
                randomMaxMessages: parseInt(document.getElementById('random-max-messages')?.value || '10', 10),
                debugMode: document.getElementById('random-debug-mode')?.checked || false
            };

            sendMessage({
                type: 'control_kick_overlay',
                data: {
                    action: 'set_styles',
                    styles
                }
            });
        });
    }

    // Reset overlay styles button
    const resetStylesBtn = document.getElementById('reset-overlay-styles-btn');
    if (resetStylesBtn) {
        resetStylesBtn.addEventListener('click', () => {
            // Reset all inputs to defaults
            if (document.getElementById('overlay-text-color')) document.getElementById('overlay-text-color').value = '#ffffff';
            if (document.getElementById('overlay-username-color')) document.getElementById('overlay-username-color').value = '#a0a0ff';
            if (document.getElementById('overlay-font-size')) document.getElementById('overlay-font-size').value = '16';
            if (document.getElementById('overlay-text-shadow')) document.getElementById('overlay-text-shadow').value = 'on';
            if (document.getElementById('overlay-bg-color')) document.getElementById('overlay-bg-color').value = '#000000';

            const bgOpacityInput = document.getElementById('overlay-bg-opacity');
            const bgOpacityValue = document.getElementById('overlay-bg-opacity-value');
            if (bgOpacityInput) {
                bgOpacityInput.value = '0.5';
                if (bgOpacityValue) bgOpacityValue.textContent = '0.5';
            }

            if (document.getElementById('overlay-padding')) document.getElementById('overlay-padding').value = '5';
            if (document.getElementById('overlay-gap')) document.getElementById('overlay-gap').value = '5';
            if (document.getElementById('overlay-border-radius')) document.getElementById('overlay-border-radius').value = '4';
            if (document.getElementById('overlay-width')) document.getElementById('overlay-width').value = '800';
            if (document.getElementById('overlay-height')) document.getElementById('overlay-height').value = '600';
            if (document.getElementById('overlay-bottom-margin')) document.getElementById('overlay-bottom-margin').value = '10';
            if (document.getElementById('random-message-duration')) document.getElementById('random-message-duration').value = '5';
            if (document.getElementById('random-animation-duration')) document.getElementById('random-animation-duration').value = '500';
            if (document.getElementById('random-max-messages')) document.getElementById('random-max-messages').value = '10';

            // Send reset command
            sendMessage({
                type: 'control_kick_overlay',
                data: {
                    action: 'reset_styles'
                }
            });
        });
    }

    // Update opacity value display when slider changes
    const bgOpacityInput = document.getElementById('overlay-bg-opacity');
    const bgOpacityValue = document.getElementById('overlay-bg-opacity-value');
    if (bgOpacityInput && bgOpacityValue) {
        bgOpacityInput.addEventListener('input', () => {
            bgOpacityValue.textContent = bgOpacityInput.value;
        });
    }

    // Toggle debug mode button
    const toggleDebugBtn = document.getElementById('toggle-debug-mode-btn');
    if (toggleDebugBtn) {
        toggleDebugBtn.addEventListener('click', () => {
            // Send toggle debug command directly to the overlay
            sendMessage({
                type: 'control_kick_overlay',
                data: {
                    action: 'toggle_debug'
                }
            });

            // Update the checkbox state (toggle it)
            const debugCheckbox = document.getElementById('random-debug-mode');
            if (debugCheckbox) {
                debugCheckbox.checked = !debugCheckbox.checked;
            }
        });
    }

    // Function to update desktop screenshot from WebSocket message
    function updateDesktopScreenshot(data) {
        // Don't log every update to avoid console spam
        // console.log('Received screenshot update with data:', data);

        const desktopViewImg = document.getElementById('desktop-view-img');
        const statusIndicator = document.getElementById('connection-status');

        if (desktopViewImg) {
            // Use the timestamp and update_id from the server to prevent caching
            const timestamp = data.timestamp || new Date().getTime();
            const updateId = data.update_id || '';
            const imagePath = data.path || 'static/screenshots/desktop_view.png';

            // Update connection status indicator if it exists
            if (statusIndicator) {
                statusIndicator.textContent = 'Connected';
                statusIndicator.className = 'status-indicator connected';
            }

            // Create a new Image object to preload the screenshot
            const newImg = new Image();

            // Set up error handler
            newImg.onerror = function(e) {
                console.error('Error loading screenshot:', e);
                console.error('Failed URL:', newImg.src);

                // Update status indicator
                if (statusIndicator) {
                    statusIndicator.textContent = 'Error';
                    statusIndicator.className = 'status-indicator error';
                }

                // Try direct approach as fallback
                setTimeout(() => {
                    const fallbackUrl = `/api/screenshot?direct=true&t=${new Date().getTime()}`;
                    console.log('Trying fallback URL:', fallbackUrl);
                    desktopViewImg.src = fallbackUrl;
                }, 200); // Reduced timeout for faster recovery
            };

            // Set up onload handler to update the visible image only after loading completes
            newImg.onload = function() {
                // Update the src of the visible image
                desktopViewImg.src = newImg.src;
                // Update the last update time for fallback detection
                lastUpdateTime = Date.now();

                // Update the last update time display if it exists
                const lastUpdateTimeDisplay = document.getElementById('last-update-time');
                if (lastUpdateTimeDisplay) {
                    lastUpdateTimeDisplay.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
                    lastUpdateTimeDisplay.style.color = 'green';
                }
            };

            // Construct the URL with the path from the data if available
            // Try to use the direct path first if it's a full URL
            let imageUrl;
            if (imagePath.startsWith('http')) {
                imageUrl = imagePath;
            } else {
                // Otherwise use the API endpoint with timestamp and ID
                imageUrl = `/api/screenshot?t=${timestamp}&id=${updateId}`;
            }

            // Set the src to start loading the new image
            newImg.src = imageUrl;
        } else {
            console.error('Desktop view image element not found');
        }
    }

    // Global variable for tracking screenshot updates
    let lastUpdateTime = Date.now();

    // Desktop View Functionality
    function initDesktopView() {
        const toggleDesktopViewBtn = document.getElementById('toggle-desktop-view-btn');
        const desktopViewContainer = document.getElementById('desktop-view-container');
        const desktopViewImg = document.getElementById('desktop-view-img');
        const refreshIntervalInput = document.getElementById('refresh-interval');

        let refreshInterval = 1000; // Default 1 second
        let refreshTimer = null;
        let isViewVisible = true; // Start with the view visible
        let fallbackMode = false; // Use fallback polling if WebSocket updates aren't coming

        // Function to refresh the desktop view image (fallback method)
        function refreshDesktopView() {
            if (fallbackMode || (Date.now() - lastUpdateTime > refreshInterval * 3)) {
                // Use direct polling in fallback mode or if no updates for a while
                const timestamp = new Date().getTime();
                console.log('Activating fallback refresh mode at', new Date().toLocaleTimeString());

                // Update status indicator
                const statusIndicator = document.getElementById('connection-status');
                if (statusIndicator) {
                    statusIndicator.textContent = 'Fallback Mode';
                    statusIndicator.className = 'status-indicator connecting';
                }

                // Create a new Image object to preload the screenshot
                const newImg = new Image();

                // Set up error handler
                newImg.onerror = function(e) {
                    console.error('Error loading fallback screenshot:', e);
                    console.error('Failed fallback URL:', newImg.src);

                    // Update status indicator to show error
                    if (statusIndicator) {
                        statusIndicator.textContent = 'Connection Error';
                        statusIndicator.className = 'status-indicator error';
                    }

                    // Try again with a different approach after a short delay
                    setTimeout(() => {
                        const emergencyUrl = `/api/screenshot?emergency=true&t=${new Date().getTime()}`;
                        console.log('Trying emergency URL:', emergencyUrl);
                        desktopViewImg.src = emergencyUrl;

                        // Update the last update time display to show error state
                        const lastUpdateTimeDisplay = document.getElementById('last-update-time');
                        if (lastUpdateTimeDisplay) {
                            lastUpdateTimeDisplay.textContent = `Error loading screenshot. Retrying...`;
                            lastUpdateTimeDisplay.style.color = 'red';
                        }
                    }, 1000);
                };

                // Set up onload handler to update the visible image only after loading completes
                newImg.onload = function() {
                    // Update the src of the visible image
                    desktopViewImg.src = newImg.src;
                    // Update the last update time
                    lastUpdateTime = Date.now();
                    console.log('Fallback: Refreshed desktop view at ' + new Date().toLocaleTimeString());

                    // Update the last update time display
                    const lastUpdateTimeDisplay = document.getElementById('last-update-time');
                    if (lastUpdateTimeDisplay) {
                        lastUpdateTimeDisplay.textContent = `Fallback update: ${new Date().toLocaleTimeString()}`;
                        lastUpdateTimeDisplay.style.color = 'orange';
                    }

                    // Update status indicator
                    if (statusIndicator) {
                        statusIndicator.textContent = 'Fallback Active';
                        statusIndicator.className = 'status-indicator connecting';
                    }
                };

                // Set the src to start loading the new image
                const fallbackUrl = `/api/screenshot?t=${timestamp}&fallback=true`;
                console.log('Loading fallback screenshot from URL:', fallbackUrl);
                newImg.src = fallbackUrl;
            }
        }

        // Show desktop view by default
        desktopViewContainer.style.display = 'block';
        toggleDesktopViewBtn.textContent = 'Hide Desktop View';

        // Initialize connection status
        const statusIndicator = document.getElementById('connection-status');
        if (statusIndicator) {
            statusIndicator.textContent = 'Connecting...';
            statusIndicator.className = 'status-indicator connecting';
        }

        // Start fallback timer as a safety measure
        refreshInterval = parseFloat(refreshIntervalInput.value) * 1000;
        console.log(`Starting fallback timer with interval: ${refreshInterval * 2}ms`);
        refreshTimer = setInterval(refreshDesktopView, refreshInterval * 2); // Twice the normal interval as fallback

        // Set up a check to enable fallback mode if no WebSocket updates are received
        setInterval(() => {
            const now = Date.now();
            const timeSinceLastUpdate = now - lastUpdateTime;
            const statusIndicator = document.getElementById('connection-status');

            // Log status periodically
            if (timeSinceLastUpdate > 10000) { // Log every 10 seconds if no updates
                console.log(`Time since last screenshot update: ${(timeSinceLastUpdate/1000).toFixed(1)}s`);

                // Update status indicator to show warning if it's been a while
                if (statusIndicator && !fallbackMode && timeSinceLastUpdate > 15000) {
                    statusIndicator.textContent = 'Connection Slow';
                    statusIndicator.className = 'status-indicator connecting';
                }
            }

            if (timeSinceLastUpdate > refreshInterval * 2) {
                // If no updates for 2x the refresh interval, enable fallback mode
                if (!fallbackMode) {
                    console.log('No WebSocket screenshot updates received for ' +
                              (timeSinceLastUpdate/1000).toFixed(1) + 's, enabling fallback mode');
                    fallbackMode = true;

                    // Update status indicator
                    if (statusIndicator) {
                        statusIndicator.textContent = 'Switching to Fallback';
                        statusIndicator.className = 'status-indicator connecting';
                    }

                    // Force an immediate refresh when entering fallback mode
                    refreshDesktopView();
                }
            } else {
                // If updates are coming in, disable fallback mode
                if (fallbackMode) {
                    console.log('WebSocket screenshot updates resumed, disabling fallback mode');
                    fallbackMode = false;

                    // Update status indicator
                    if (statusIndicator) {
                        statusIndicator.textContent = 'Connected';
                        statusIndicator.className = 'status-indicator connected';
                    }

                    // Update the last update time display
                    const lastUpdateTimeDisplay = document.getElementById('last-update-time');
                    if (lastUpdateTimeDisplay) {
                        lastUpdateTimeDisplay.textContent = `WebSocket resumed: ${new Date().toLocaleTimeString()}`;
                        lastUpdateTimeDisplay.style.color = 'green';
                    }
                }
            }
        }, refreshInterval);

        // Update last update time when a screenshot is loaded
        desktopViewImg.addEventListener('load', () => {
            lastUpdateTime = Date.now();

            // Update the last update time display if it exists
            const lastUpdateTimeDisplay = document.getElementById('last-update-time');
            if (lastUpdateTimeDisplay) {
                lastUpdateTimeDisplay.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
            }
        });

        // Toggle desktop view visibility
        if (toggleDesktopViewBtn) {
            toggleDesktopViewBtn.addEventListener('click', function() {
                isViewVisible = !isViewVisible;

                if (isViewVisible) {
                    desktopViewContainer.style.display = 'block';
                    toggleDesktopViewBtn.textContent = 'Hide Desktop View';

                    // Force an immediate refresh when showing
                    const timestamp = new Date().getTime();
                    desktopViewImg.src = `/api/screenshot?t=${timestamp}`;
                } else {
                    desktopViewContainer.style.display = 'none';
                    toggleDesktopViewBtn.textContent = 'Show Desktop View';
                }
            });
        }

        // Update refresh interval when changed
        if (refreshIntervalInput) {
            refreshIntervalInput.addEventListener('change', function() {
                // Update the refresh interval for both WebSocket and fallback
                refreshInterval = parseFloat(refreshIntervalInput.value) * 1000;

                // Update the fallback timer
                if (refreshTimer) {
                    clearInterval(refreshTimer);
                    refreshTimer = setInterval(refreshDesktopView, refreshInterval * 2);
                    console.log('Updated refresh interval to ' + refreshInterval + 'ms');
                }

                // Send the new interval to the server
                sendMessage({
                    type: 'update_screenshot_interval',
                    data: { interval: refreshInterval / 1000 } // Convert back to seconds for the server
                });
            });
        }
    }

    // Add streaming mode functionality
    let streamingMode = false;
    let streamingInterval = null;

    // Function to toggle streaming mode
    window.toggleStreamingMode = function() {
        streamingMode = !streamingMode;
        const desktopViewContainer = document.getElementById('desktop-view-container');
        const statusIndicator = document.getElementById('connection-status');

        if (streamingMode) {
            // Enable streaming mode
            if (desktopViewContainer) {
                desktopViewContainer.classList.add('streaming-mode');
            }

            if (statusIndicator) {
                statusIndicator.textContent = 'Streaming';
                statusIndicator.className = 'status-indicator connected';
            }

            // Start a more frequent refresh interval for streaming
            if (streamingInterval) clearInterval(streamingInterval);
            streamingInterval = setInterval(() => {
                const timestamp = new Date().getTime();
                const desktopViewImg = document.getElementById('desktop-view-img');
                if (desktopViewImg) {
                    desktopViewImg.src = `/api/screenshot?t=${timestamp}&streaming=true`;
                }
            }, 200); // Very frequent updates for smoother streaming

            console.log('Streaming mode enabled');
        } else {
            // Disable streaming mode
            if (desktopViewContainer) {
                desktopViewContainer.classList.remove('streaming-mode');
            }

            if (statusIndicator) {
                statusIndicator.textContent = 'Connected';
                statusIndicator.className = 'status-indicator connected';
            }

            // Stop the streaming interval
            if (streamingInterval) {
                clearInterval(streamingInterval);
                streamingInterval = null;
            }

            console.log('Streaming mode disabled');
        }
    };

    // Function for emergency refresh
    window.emergencyRefresh = function() {
        const timestamp = new Date().getTime();
        const desktopViewImg = document.getElementById('desktop-view-img');
        if (desktopViewImg) {
            console.log('Emergency refresh triggered');
            desktopViewImg.src = `/api/screenshot?t=${timestamp}&emergency=true&force=true`;

            // Update status indicator
            const statusIndicator = document.getElementById('connection-status');
            if (statusIndicator) {
                statusIndicator.textContent = 'Refreshing';
                statusIndicator.className = 'status-indicator connecting';
            }
        }
    };

    // Initialize desktop view functionality
    initDesktopView();

    // Connect to WebSocket
    connectWebSocket();
});
