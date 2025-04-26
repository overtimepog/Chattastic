# Use Python 3.11 on Debian Bookworm
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core utilities
    wget \
    gnupg \
    git \
    # X11 and display utilities
    xvfb \
    xorg \
    imagemagick \
    # X11 libraries
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxtst6 \
    # XFCE desktop environment
    dbus-x11 \
    xterm \
    x11-xserver-utils \
    xauth \
    xfce4 \
    xfce4-session \
    xfce4-panel \
    xfce4-terminal \
    # Docker client dependencies
    ca-certificates \
    curl \
    software-properties-common \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI using modern repository setup
RUN mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bullseye stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Create directories for XFCE and screenshots
RUN mkdir -p debug_screenshots /app/.config/autostart

# Environment variables
ENV DISPLAY=:99 \
    DBUS_SESSION_BUS_ADDRESS=/dev/null

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip wheel setuptools \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Entrypoint configuration
COPY docker-entrypoint.sh /
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/docker-entrypoint.sh"]