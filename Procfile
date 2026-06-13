# Demo process model for Render's free tier, which has no separate worker dynos.
# honcho runs all three in one container. In production these are separate,
# independently scalable services (see docker-compose.yml).
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 3
worker: celery -A config worker -l info
beat: celery -A config beat -l info
