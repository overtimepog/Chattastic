@echo off
echo Building and starting Chattastic Docker container...

REM Build the Docker image
docker-compose build

REM Run the container
docker-compose up -d

REM show the logs
docker-compose logs -f

echo Chattastic Docker container is now running.
echo Access the web interface at http://localhost:8000
echo.
echo To view logs, run: docker-compose logs -f
echo To stop the container, run: docker-compose down
