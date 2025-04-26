/**
 * Docker Desktop Viewer - Client-side JavaScript
 *
 * Provides functionality for:
 * - Theme management (light/dark mode)
 * - WebSocket communication with the server
 * - Desktop screenshot viewing and control
 * - Docker container monitoring
 */

// Theme management functions
function setTheme(themeName) {
    localStorage.setItem('theme', themeName);
    document.documentElement.setAttribute('data-theme', themeName);

    // Update toggle button appearance
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        const icon = themeToggle.querySelector('i');
        const text = themeToggle.querySelector('span');

        if (themeName === 'dark') {
            icon.className = 'fas fa-sun';
            text.textContent = 'Light Mode';
        } else {
            icon.className = 'fas fa-moon';
            text.textContent = 'Dark Mode';
        }
    }
}

function toggleTheme() {
    const currentTheme = localStorage.getItem('theme') || 'light';
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
}

// Initialize theme from localStorage
function initTheme() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
        setTheme(savedTheme);
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        // Use dark theme if user's system preference is dark
        setTheme('dark');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Initialize theme
    initTheme();

    // Get UI elements
    const wsStatus = document.getElementById('ws-status');

    // Connect to WebSocket
    function connectWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws`;
        console.log(`Connecting to WebSocket: ${wsUrl}`);

        try {
            window.ws = new WebSocket(wsUrl);

            window.ws.onopen = () => {
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

            window.ws.onmessage = (event) => {
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

            window.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                if (wsStatus) {
                    wsStatus.textContent = 'Error';
                    wsStatus.className = 'disconnected';
                }
            };

            window.ws.onclose = () => {
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
        if (window.ws && window.ws.readyState === WebSocket.OPEN) {
            const messageStr = JSON.stringify(message);
            console.log('Sending message:', messageStr);
            window.ws.send(messageStr);
        } else {
            console.error('WebSocket not connected');
        }
    }

    // Show message to user
    function showMessage(type, message) {
        console.log(`Showing ${type} message: ${message}`);

        // Create message element if it doesn't exist
        let messageContainer = document.getElementById('message-container');
        if (!messageContainer) {
            messageContainer = document.createElement('div');
            messageContainer.id = 'message-container';
            messageContainer.style.position = 'fixed';
            messageContainer.style.top = '20px';
            messageContainer.style.left = '50%';
            messageContainer.style.transform = 'translateX(-50%)';
            messageContainer.style.zIndex = '1000';
            document.body.appendChild(messageContainer);
        }

        // Create message element
        const messageElement = document.createElement('div');
        messageElement.className = `message ${type}`;
        messageElement.textContent = message;
        messageElement.style.padding = '10px 20px';
        messageElement.style.margin = '10px 0';
        messageElement.style.borderRadius = '5px';
        messageElement.style.boxShadow = '0 2px 5px rgba(0,0,0,0.2)';

        // Set colors based on message type
        if (type === 'error') {
            messageElement.style.backgroundColor = '#f44336';
            messageElement.style.color = 'white';
        } else if (type === 'success') {
            messageElement.style.backgroundColor = '#4CAF50';
            messageElement.style.color = 'white';
        } else if (type === 'warning') {
            messageElement.style.backgroundColor = '#ff9800';
            messageElement.style.color = 'white';
        } else {
            messageElement.style.backgroundColor = '#2196F3';
            messageElement.style.color = 'white';
        }

        // Add message to container
        messageContainer.appendChild(messageElement);

        // Remove message after 5 seconds
        setTimeout(() => {
            messageElement.style.opacity = '0';
            messageElement.style.transition = 'opacity 0.5s';
            setTimeout(() => {
                messageContainer.removeChild(messageElement);
                if (messageContainer.children.length === 0) {
                    document.body.removeChild(messageContainer);
                }
            }, 500);
        }, 5000);
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

            case 'screenshot_update':
                // Handle screenshot updates
                updateDesktopScreenshot(message.data);
                break;

            case 'screenshot_interval_updated':
                // Handle screenshot interval update
                const screenshotIntervalInput = document.getElementById('screenshot-interval');
                if (screenshotIntervalInput) {
                    screenshotIntervalInput.value = message.data.interval;
                }
                showMessage('success', `Screenshot interval updated to ${message.data.interval} seconds`);
                break;

            case 'docker_containers':
                // Handle Docker containers list update
                // This is handled in docker_logs.html
                break;

            case 'error':
                showMessage('error', message.data.message);
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

        // Update screenshot interval
        const screenshotIntervalInput = document.getElementById('screenshot-interval');
        if (screenshotIntervalInput && data.screenshot_interval) {
            screenshotIntervalInput.value = data.screenshot_interval;
        }
    }

    // Update desktop screenshot
    function updateDesktopScreenshot(data) {
        const desktopViewImg = document.getElementById('desktop-view-img');
        if (!desktopViewImg) return;

        // Update the image
        if (data.path) {
            // Add a timestamp to prevent caching
            const timestamp = new Date().getTime();

            // Handle different path formats
            let imgSrc;
            if (data.path.includes('desktop_view.png')) {
                // Use the dedicated screenshots mount point
                imgSrc = `/screenshots/desktop_view.png?t=${timestamp}`;
            } else {
                // Use static-assets for other paths
                imgSrc = `/static-assets/${data.path.replace(/^static\//, '')}?t=${timestamp}`;
            }

            desktopViewImg.src = imgSrc;
        }

        // Update status
        const connectionStatus = document.getElementById('connection-status');
        if (connectionStatus) {
            connectionStatus.textContent = 'Connected';
            connectionStatus.className = 'status-indicator connected';
        }

        // Update last update time
        const lastUpdateTime = document.getElementById('last-update-time');
        if (lastUpdateTime) {
            const now = new Date();
            const timeString = now.toLocaleTimeString();
            lastUpdateTime.textContent = `Last update: ${timeString}`;
        }
    }

    // Set up event listeners

    // Toggle desktop view
    const toggleDesktopViewBtn = document.getElementById('toggle-desktop-view-btn');
    const desktopViewContainer = document.getElementById('desktop-view-container');
    if (toggleDesktopViewBtn && desktopViewContainer) {
        toggleDesktopViewBtn.addEventListener('click', () => {
            if (desktopViewContainer.style.display === 'none') {
                desktopViewContainer.style.display = 'block';
                toggleDesktopViewBtn.textContent = 'Hide Desktop View';
            } else {
                desktopViewContainer.style.display = 'none';
                toggleDesktopViewBtn.textContent = 'Show Desktop View';
            }
        });
    }

    // Update screenshot interval
    const updateScreenshotIntervalBtn = document.getElementById('update-screenshot-interval-btn');
    const screenshotIntervalInput = document.getElementById('screenshot-interval');
    if (updateScreenshotIntervalBtn && screenshotIntervalInput) {
        updateScreenshotIntervalBtn.addEventListener('click', () => {
            const interval = parseFloat(screenshotIntervalInput.value);
            if (!isNaN(interval) && interval >= 0.1 && interval <= 10) {
                sendMessage({
                    type: 'update_screenshot_interval',
                    data: { interval }
                });
            } else {
                showMessage('error', 'Please enter a valid interval between 0.1 and 10 seconds');
            }
        });
    }

    // Initialize streaming mode variables
    window.streamingMode = false;
    window.streamingInterval = null;

    // Connect to WebSocket
    connectWebSocket();
});

/**
 * Toggle streaming mode for desktop view
 *
 * When enabled, refreshes the screenshot at a higher frequency
 * for a more real-time view of the desktop.
 */
function toggleStreamingMode() {
    window.streamingMode = !window.streamingMode;

    const desktopViewContainer = document.getElementById('desktop-view-container');
    const statusIndicator = document.getElementById('connection-status');

    if (window.streamingMode) {
        // Enable streaming mode
        if (desktopViewContainer) {
            desktopViewContainer.classList.add('streaming-mode');
        }

        if (statusIndicator) {
            statusIndicator.textContent = 'Streaming';
            statusIndicator.className = 'status-indicator connected';
        }

        // Start a more frequent refresh interval for streaming
        if (window.streamingInterval) clearInterval(window.streamingInterval);
        window.streamingInterval = setInterval(() => {
            const timestamp = new Date().getTime();
            const desktopViewImg = document.getElementById('desktop-view-img');
            if (desktopViewImg) {
                // Use the API endpoint directly to ensure proper handling
                desktopViewImg.src = `/api/screenshot?force=true&t=${timestamp}`;
            }
        }, 200); // Very frequent updates for smoother streaming
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
        if (window.streamingInterval) {
            clearInterval(window.streamingInterval);
            window.streamingInterval = null;
        }
    }
}

/**
 * Force an immediate refresh of the desktop screenshot
 *
 * Used when the normal update mechanism fails or when
 * an immediate update is needed.
 */
function emergencyRefresh() {
    const desktopViewImg = document.getElementById('desktop-view-img');
    if (desktopViewImg) {
        const timestamp = new Date().getTime();
        // Use the API endpoint directly to ensure proper handling
        desktopViewImg.src = `/api/screenshot?force=true&emergency=true&t=${timestamp}`;
    }
}
