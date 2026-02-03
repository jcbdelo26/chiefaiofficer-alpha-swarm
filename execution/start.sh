#!/bin/bash

# Start the Scheduler Service (Worker) in the background
echo "Starting Scheduler Service..."
python core/scheduler_service.py &

# Start the Web Dashboard (Foreground)
echo "Starting Web Dashboard..."
uvicorn dashboard.health_app:app --host 0.0.0.0 --port ${PORT:-8080}
