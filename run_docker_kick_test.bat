@echo off
echo Running Kick chat test in Docker container...

REM Build the Docker image if needed
docker-compose build

REM Run the test script in the container
docker-compose run --rm chattastic python test_docker.py %1 %2

echo Test completed.
