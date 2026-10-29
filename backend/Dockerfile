FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN --mount=type=secret,id=ca_bundle     if [ -f /run/secrets/ca_bundle ]; then         pip install --no-cache-dir --cert /run/secrets/ca_bundle -r backend/requirements.txt;     else         pip install --no-cache-dir -r backend/requirements.txt;     fi
COPY --chmod=644 app_paths.py database.py password_service.py validators.py auth_service.py account_security.py profile_service.py mail_service.py photo_service.py /app/
COPY --chmod=644 backend/__init__.py backend/main.py /app/backend/
RUN mkdir /data && chown 65534:65534 /data && chmod 755 /app /app/backend
ENV LEPKA_SERVER_DATA_DIR=/data LEPKA_DATA_DIR=/data PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
