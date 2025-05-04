# Kick Chat Connection Test

This folder contains test scripts for connecting to a Kick streamer's chat using persistent browser sessions. The scripts demonstrate four different approaches:

1. `test_playwright.py` - Using Playwright with playwright_stealth
2. `test_undetected.py` - Using undetected_chromedriver with Selenium
3. `test_mechanicalsoup.py` - Using MechanicalSoup for a lighter-weight approach
4. `test_robobrowser.py` - Using RoboBrowser for a simple, Pythonic approach

## Features

- Persistent browser sessions for maintaining connection
- Stealth mode to avoid detection
- Proxy support for bypassing Cloudflare protection
- Chat message extraction and parsing
- Emote handling

## Prerequisites

Install the required dependencies:

```bash
pip install playwright playwright-stealth undetected-chromedriver selenium beautifulsoup4 mechanicalsoup robobrowser
```

For Playwright, you also need to install the browsers:

```bash
playwright install
```

## Configuration

The test scripts use the ZenRows proxy configuration from the main application's `config.py` file. No additional configuration is needed for the proxy settings.

## Usage

### Playwright Version

```bash
python test_playwright.py
```

### Undetected ChromeDriver Version

```bash
python test_undetected.py
```

### MechanicalSoup Version

```bash
python test_mechanicalsoup.py
```

### RoboBrowser Version

```bash
python test_robobrowser.py
```

All scripts will prompt you to enter a Kick channel name. After connecting, they will display chat messages in the console.

## How It Works

1. **Browser Initialization**: Both scripts create a persistent browser session.
2. **Stealth Mode**: Applied to avoid detection by anti-bot systems.
3. **Connection**: Navigate to the Kick channel page.
4. **Cloudflare Detection**: If Cloudflare protection is detected, retry with a proxy.
5. **Message Polling**: Continuously poll the DOM for new chat messages.
6. **Message Parsing**: Extract username, content, timestamp, and emotes from each message.
7. **Cleanup**: Properly close browser resources when done.

## Proxy Strategy

The scripts use a two-step approach for proxies:

1. First attempt without a proxy
2. If Cloudflare protection is detected, retry with the ZenRows proxy from config.py

## Notes

- The scripts create a folder named `chrome_data` for the undetected_chromedriver version to store persistent session data.
- All scripts handle the bug where emojis in chat messages have unwanted square brackets `[]` after them.
- The polling interval varies by implementation (0.8 seconds for Playwright, 2 seconds for RoboBrowser) to balance responsiveness with resource usage.
- RoboBrowser combines the best of Requests and BeautifulSoup for a simple, Pythonic approach to web scraping without a standalone browser.
