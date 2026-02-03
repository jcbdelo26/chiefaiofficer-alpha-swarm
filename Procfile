web: uvicorn dashboard.health_app:app --host 0.0.0.0 --port ${PORT:-8080}
worker: python core/scheduler_service.py
orchestrator: python core/daily_orchestrator.py
