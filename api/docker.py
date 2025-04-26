"""
Docker API Module

Provides functionality for interacting with Docker containers and streaming logs.
Features:
- Container listing and status monitoring
- Log retrieval and real-time streaming
- WebSocket integration for live updates
"""

import asyncio
import json
import logging
import docker
from docker.errors import DockerException
import globals

# Set up logging
logger = logging.getLogger(__name__)

# Docker client
client = None

def init_docker_client():
    """Initialize Docker client."""
    global client
    try:
        client = docker.from_env()
        logger.info("Docker client initialized successfully")
        return True
    except DockerException as e:
        logger.error(f"Failed to initialize Docker client: {e}")
        # Check if we're running inside a container
        import os
        if os.path.exists('/.dockerenv'):
            logger.warning("Running inside a Docker container without Docker socket access.")
            logger.warning("Docker API functionality will be limited.")
            logger.warning("To enable Docker API, mount the Docker socket when running the container.")
        return False

async def get_containers():
    """Get list of Docker containers."""
    if not client:
        if not init_docker_client():
            return []

    try:
        containers = client.containers.list(all=True)
        container_list = []

        for container in containers:
            container_list.append({
                'id': container.id,
                'name': container.name,
                'status': container.status,
                'image': container.image.tags[0] if container.image.tags else container.image.id,
                'created': container.attrs['Created'],
                'ports': container.ports,
            })

        return container_list
    except DockerException as e:
        logger.error(f"Error getting container list: {e}")
        return []

async def get_container_logs(container_id, tail=100):
    """Get logs for a specific container."""
    if not client:
        if not init_docker_client():
            return []

    try:
        container = client.containers.get(container_id)
        logs = container.logs(tail=tail, timestamps=True).decode('utf-8').splitlines()
        return logs
    except DockerException as e:
        logger.error(f"Error getting logs for container {container_id}: {e}")
        return []

async def stream_container_logs(container_id, websocket):
    """Stream logs from a container to a WebSocket."""
    if not client:
        if not init_docker_client():
            return

    try:
        container = client.containers.get(container_id)

        # Send initial logs
        logs = container.logs(tail=50, timestamps=True).decode('utf-8').splitlines()
        for log in logs:
            await websocket.send_text(json.dumps({
                'type': 'docker_log',
                'data': {
                    'container_id': container_id,
                    'log': log
                }
            }))

        # Stream new logs
        for line in container.logs(stream=True, follow=True, timestamps=True):
            log_line = line.decode('utf-8').strip()
            await websocket.send_text(json.dumps({
                'type': 'docker_log',
                'data': {
                    'container_id': container_id,
                    'log': log_line
                }
            }))

            # Check if websocket is still open
            try:
                # Try to receive a message with a very short timeout
                # This is a way to check if the connection is still alive
                await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
            except asyncio.TimeoutError:
                # This is expected, we're just checking connection
                pass
            except Exception:
                # Any other exception means the connection is closed
                logger.info(f"WebSocket closed, stopping log stream for container {container_id}")
                break

    except DockerException as e:
        logger.error(f"Error streaming logs for container {container_id}: {e}")
        await websocket.send_text(json.dumps({
            'type': 'error',
            'data': {
                'message': f"Error streaming logs: {str(e)}"
            }
        }))

async def broadcast_container_status():
    """Broadcast container status to all connected clients."""
    containers = await get_containers()

    status_data = {
        'type': 'docker_containers',
        'data': {
            'containers': containers
        }
    }

    await globals.manager.broadcast(json.dumps(status_data))
