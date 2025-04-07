# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application
- Start application: `python app.py`
- Install dependencies: `pip install -r requirements.txt`
- Run using batch file (Windows): `run.bat`

## Code Style Guidelines
- **Imports**: Group standard library imports first, followed by third-party libraries, then local modules
- **Naming**: Use snake_case for variables/functions, PascalCase for classes
- **Comments**: Include docstrings in functions with complex logic
- **Error Handling**: Use try/except blocks with specific exceptions when dealing with external APIs or file operations
- **Global Variables**: Defined in config.py for application-wide settings
- **Logging**: Use the logging module (already configured in config.py)
- **UI Components**: Store UI elements as global variables in ui/app.py
- **Threading**: Make threads daemon=True for proper application shutdown

## Project Structure
- app.py: Main entry point
- config.py: Configuration and global variables
- ui/: UI components and viewer functionality
- api/: API integrations (Twitch, Kick)
- utils/: Helper functions for authentication and audio