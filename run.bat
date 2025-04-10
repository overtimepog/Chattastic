@echo off
echo Building and starting Chattastic Docker container...

REM Use --build to rebuild images when changes are detected and run in detached mode
docker-compose up --build -d

REM show the logs
docker-compose logs -f

echo Chattastic Docker container is now running.
echo Access the web interface at http://localhost:8000
echo.
echo To view logs, run: docker-compose logs -f
echo To stop the container, run: docker-compose down
