FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5000

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY --chown=app:app app.py auth.py chat.py config.py models.py ./
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app static ./static

USER app
EXPOSE 5000

# La clave debe configurarse en runtime para que todas las workers compartan
# la misma clave de sesión. Las migraciones se ejecutan explícitamente aparte.
CMD ["sh", "-c", "if [ -z \"${FLASK_SECRET_KEY:-}\" ]; then echo 'Falta FLASK_SECRET_KEY; configúrala al iniciar el contenedor.' >&2; exit 1; fi; exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --threads 2 --access-logfile - --error-logfile - app:app"]
