FROM python:3.11-slim

# Install required packages
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    xvfb \
    xorg \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    git \
    build-essential \
    python3-dev \
    # Screenshot utilities
    imagemagick \
    # XFCE desktop environment and X utilities
    dbus-x11 \
    dbus-daemon \
    xterm \
    x11-xserver-utils \
    xauth \
    xfce4 \
    xfce4-session \
    xfce4-panel \
    xfce4-terminal \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip wheel setuptools
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Create directories for emote cache, debug screenshots, and XFCE autostart
RUN mkdir -p emote_cache debug_screenshots selenium_chrome_data
RUN mkdir -p /app/.config/autostart

# Create autostart file for Chrome with improved stability options
RUN echo '[Desktop Entry]\nType=Application\nExec=/usr/bin/google-chrome --no-sandbox --disable-dev-shm-usage --disable-gpu --disable-software-rasterizer --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding\nHidden=false\nNoDisplay=false\nX-XFCE-Autostart-enabled=true\nName=Chrome Helper\nComment=Ensures Chrome can start properly with stability options' > /app/.config/autostart/chrome-helper.desktop

# Set up Xvfb virtual display with improved configuration
ENV DISPLAY=:99
ENV DBUS_SESSION_BUS_ADDRESS=/dev/null
# Add environment variables to improve Chrome stability
ENV CHROME_DISABLE_GPU=true
ENV CHROME_NO_SANDBOX=true
ENV CHROME_DISABLE_DEV_SHM_USAGE=true

# Expose the port for the FastAPI server
EXPOSE 8000

# Start script that sets up Xvfb and runs the application
COPY docker-entrypoint.sh /
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
