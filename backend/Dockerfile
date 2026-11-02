FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN --mount=type=secret,id=ca_bundle     if [ -f /run/secrets/ca_bundle ]; then         pip install --no-cache-dir --cert /run/secrets/ca_bundle -r backend/requirements.txt;     else         pip install --no-cache-dir -r backend/requirements.txt;     fi
COPY --chmod=644 interface_catalog.py learning_catalog.py notification_mail.py delivery_settings.py project_planner.py lesson_library.py offline_mutations.py personal_vault.py personal_snapshot.py project_archive.py project_service.py model_import.py mesh_renderer.py account_security.py activity_service.py app_paths.py auth_service.py challenge_service.py color_service.py contest_entry.py database.py feed_service.py learning_assets.py lesson_service.py mail_service.py moderation_service.py password_service.py photo_service.py post_service.py profile_service.py project_sharing.py role_service.py social_feed.py validators.py workshop_service.py /app/
COPY --chmod=644 backend/__init__.py backend/main.py backend/community.py backend/moderation.py backend/challenges.py backend/personal.py backend/delivery.py backend/catalog.py /app/backend/
COPY --chmod=644 scripts/__init__.py scripts/manage_admin.py scripts/server_backup.py scripts/run_wifi_server.py scripts/create_server_demo.py /app/scripts/
COPY --chmod=644 assets/i18n_en.json /app/assets/i18n_en.json
RUN mkdir /data && chown 65534:65534 /data && chmod 755 /app /app/backend /app/scripts /app/assets
ENV LEPKA_SERVER_DATA_DIR=/data LEPKA_DATA_DIR=/data PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD ["python", "-c", "import urllib.request; urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8000/ready',timeout=3).read()"]
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
