"""
API endpoints for settings management.
"""

import logging
import json
import os
from fastapi import APIRouter, HTTPException, Body, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from typing import Dict, Any, Optional

from api import settings
import globals

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


@router.get("/")
async def get_settings():
    """
    Get all settings.

    Returns:
        Dict[str, Any]: The current settings
    """
    return settings.load_settings()


@router.post("/")
async def update_settings(new_settings: Dict[str, Any] = Body(...)):
    """
    Update settings.

    Args:
        new_settings: The new settings to apply

    Returns:
        Dict[str, Any]: The updated settings
    """
    try:
        updated_settings = settings.update_settings(new_settings)

        # Broadcast settings update to all connected clients
        if globals.manager:
            await globals.manager.broadcast(json.dumps({
                "type": "settings_updated",
                "data": updated_settings
            }))

        return updated_settings
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating settings: {str(e)}")


@router.get("/{key_path}")
async def get_setting(key_path: str, default: Optional[Any] = None):
    """
    Get a specific setting by key path.

    Args:
        key_path: Dot-separated path to the setting (e.g., 'obs_source.width')
        default: Default value to return if the setting doesn't exist

    Returns:
        The setting value or default if not found
    """
    value = settings.get_setting(key_path, default)
    if value is None and default is None:
        raise HTTPException(status_code=404, detail=f"Setting '{key_path}' not found")
    return {"key": key_path, "value": value}


@router.post("/{key_path}")
async def set_setting(key_path: str, value: Any = Body(..., embed=True)):
    """
    Set a specific setting by key path.

    Args:
        key_path: Dot-separated path to the setting (e.g., 'obs_source.width')
        value: The value to set

    Returns:
        Dict[str, Any]: The updated setting
    """
    try:
        success = settings.set_setting(key_path, value)
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to save setting '{key_path}'")

        # Broadcast setting update to all connected clients
        if globals.manager:
            await globals.manager.broadcast(json.dumps({
                "type": "setting_updated",
                "data": {"key": key_path, "value": value}
            }))

        return {"key": key_path, "value": value}
    except Exception as e:
        logger.error(f"Error setting '{key_path}': {e}")
        raise HTTPException(status_code=500, detail=f"Error setting '{key_path}': {str(e)}")


@router.post("/obs_dimensions")
async def update_obs_dimensions(dimensions: Dict[str, int] = Body(...)):
    """
    Update OBS source dimensions.

    Args:
        dimensions: Dictionary with width, height, and bottom_margin

    Returns:
        Dict[str, Any]: The updated OBS dimensions
    """
    try:
        # Validate dimensions
        width = dimensions.get("width", 800)
        height = dimensions.get("height", 600)
        bottom_margin = dimensions.get("bottom_margin", 10)

        # Ensure values are within reasonable ranges
        width = max(100, min(3000, width))
        height = max(100, min(3000, height))
        bottom_margin = max(0, min(200, bottom_margin))

        # Update settings
        obs_settings = {
            "obs_source": {
                "width": width,
                "height": height,
                "bottom_margin": bottom_margin
            }
        }

        updated_settings = settings.update_settings(obs_settings)

        # Broadcast settings update to all connected clients
        if globals.manager:
            await globals.manager.broadcast(json.dumps({
                "type": "obs_dimensions_updated",
                "data": updated_settings["obs_source"]
            }))

        return updated_settings["obs_source"]
    except Exception as e:
        logger.error(f"Error updating OBS dimensions: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating OBS dimensions: {str(e)}")


@router.get("/location")
async def get_settings_location():
    """
    Get information about where settings are being stored.

    Returns:
        Dict[str, Any]: Information about settings location
    """
    try:
        location_info = settings.get_settings_location()
        return location_info
    except Exception as e:
        logger.error(f"Error getting settings location: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting settings location: {str(e)}")


@router.post("/export")
async def export_settings(filename: Optional[str] = None):
    """
    Export settings to a file.

    Args:
        filename: Optional custom filename (without extension)

    Returns:
        Dict[str, Any]: Result of the export operation
    """
    try:
        result = settings.export_settings(filename)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error during export"))

        # Broadcast export success to all connected clients
        if globals.manager:
            await globals.manager.broadcast(json.dumps({
                "type": "settings_exported",
                "data": {
                    "path": result["path"],
                    "timestamp": result.get("timestamp")
                }
            }))

        return result
    except Exception as e:
        logger.error(f"Error exporting settings: {e}")
        raise HTTPException(status_code=500, detail=f"Error exporting settings: {str(e)}")


@router.post("/import")
async def import_settings(file: UploadFile = File(...)):
    """
    Import settings from an uploaded file.

    Args:
        file: The uploaded settings file

    Returns:
        Dict[str, Any]: Result of the import operation
    """
    try:
        # Create a temporary file to store the upload
        temp_file_path = f"temp_settings_import_{file.filename}"

        try:
            # Save the uploaded file
            contents = await file.read()
            with open(temp_file_path, "wb") as f:
                f.write(contents)

            # Import the settings
            result = settings.import_settings(temp_file_path)

            if not result["success"]:
                raise HTTPException(status_code=400, detail=result.get("error", "Unknown error during import"))

            # Broadcast import success to all connected clients
            if globals.manager:
                await globals.manager.broadcast(json.dumps({
                    "type": "settings_imported",
                    "data": result["settings"]
                }))

            return result
        finally:
            # Clean up the temporary file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
    except Exception as e:
        logger.error(f"Error importing settings: {e}")
        raise HTTPException(status_code=500, detail=f"Error importing settings: {str(e)}")


@router.get("/export/{filename}")
async def download_exported_settings(filename: str):
    """
    Download a previously exported settings file.

    Args:
        filename: The filename of the exported settings

    Returns:
        FileResponse: The settings file for download
    """
    try:
        # Get the settings path
        settings_path = settings.get_settings_path()
        export_dir = os.path.join(os.path.dirname(settings_path), settings.EXPORT_DIR)
        file_path = os.path.join(export_dir, filename)

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"Exported settings file '{filename}' not found")

        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="application/json"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading exported settings: {e}")
        raise HTTPException(status_code=500, detail=f"Error downloading exported settings: {str(e)}")
