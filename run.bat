@echo off
echo Building and starting Docker Desktop Viewer container...

REM Use --build to rebuild images when changes are detected and run in detached mode
docker-compose up --build

REM show the logs
docker-compose logs -f

echo Docker Desktop Viewer container is now running.
echo Access the web interface at http://localhost:8000
echo.
echo To view logs, run: docker-compose logs -f
echo To stop the container, run: docker-compose down

pause
