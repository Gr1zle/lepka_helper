# Инвентаризация Python-модулей

AST-инвентаризация текущего дерева, не утверждение об исполнении каждой ветви. Полные пути, SHA-256, строки и верхнеуровневые функции: [modules.json](evidence/modules.json). «APK/Server» означает явный список упаковки, а не загрузку во время каждого запуска.

| Модуль | Строк | APK | Сервер | Назначение/docstring |
|---|---:|---|---|---|
| `account_gateway.py` | 228 | да | — | Единый вход для интерфейса: прежние локальные сервисы или HTTP API. |
| `account_security.py` | 123 | да | да | Одноразовые коды и сессии. В SQLite хранятся только их хеши. |
| `activity_service.py` | 19 | да | да | Уведомления об активности: события записываются в транзакции самого действия. |
| `api_client.py` | 119 | да | — | HTTP-транспорт клиента. Секрет Resend здесь не используется. |
| `app_info.py` | 4 | да | — | Единая версия приложения для финальной контрольной версии. |
| `app_paths.py` | 10 | да | да | Единая папка данных, не зависящая от текущей рабочей директории. |
| `app_state.py` | 26 | да | — |  |
| `auth_service.py` | 162 | да | да | Регистрация и вход: проверки выполняются независимо от интерфейса Flet. |
| `backend/__init__.py` | 1 | — | да | Сервер аккаунтов Lepka Helper. |
| `backend/catalog.py` | 96 | — | да |  |
| `backend/challenges.py` | 82 | — | да | HTTP конкурсного цикла; пользователь определяется только Bearer-сессией. |
| `backend/community.py` | 268 | — | да | API сообщества. Личные действия используют только пользователя из Bearer-сессии. |
| `backend/delivery.py` | 26 | — | да |  |
| `backend/main.py` | 303 | — | да | Запуск: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000. |
| `backend/moderation.py` | 95 | — | да | HTTP права администратора проверяются заново для каждого действия. |
| `backend/personal.py` | 32 | — | да |  |
| `camera_web.py` | 33 | да | — | User-initiated browser camera, with a capture-input fallback for LAN HTTP. |
| `catalog_client.py` | 144 | да | — | Complete, checked offline packages, scoped to the current account and API. |
| `catalog_media.py` | 61 | да | — | Private cached video: short-lived web tickets with byte ranges, native files. |
| `catalog_sync.py` | 13 | да | — | Light metadata and usage sync; media is downloaded only by explicit request. |
| `catalog_upload.py` | 58 | да | — | Single-use bounded web uploads, validated by the current catalogue authority. |
| `challenge_gateway.py` | 49 | да | — | Идентификаторы заявок принадлежат текущему режиму сообщества. |
| `challenge_service.py` | 296 | да | да | Конкурсы: единые транзакции для локального режима и API. |
| `clay_tools.py` | 90 | да | — | Простые расчёты объёма/массы и таймер на монотонных часах. |
| `color_export.py` | 70 | да | — | PNG-рецепт: одинаковая кириллица на всех ОС благодаря включённому шрифту. |
| `color_photo.py` | 66 | да | — | Camera/gallery colour sampling and simple, explicit reference-image operations. |
| `color_service.py` | 402 | да | да |  |
| `color_wheel.py` | 83 | да | — | Кешируемое изображение круга и выбор оттенка по координатам. |
| `community_cache.py` | 24 | да | — | Ограниченный кеш прочитанных данных, разделённый по аккаунту и серверу. |
| `community_gateway.py` | 341 | да | — | Сообщество: локальные сервисы или сервер API, без подмены режима при сбое. |
| `community_outbox.py` | 103 | да | — | Долговечная очередь без токенов; повторяется только под владельцем и его API. |
| `connection_monitor.py` | 76 | да | — |  |
| `contest_entry.py` | 65 | да | да | Теги конкурса и отбор публикаций в уже открытой транзакции. |
| `database.py` | 1382 | да | да |  |
| `date_field.py` | 29 | да | — |  |
| `deferred_community.py` | 40 | да | — | Проверка и постановка пользовательских отправок до первого сетевого запроса. |
| `delivery_settings.py` | 28 | да | да | Preferences for device notifications and optional server email delivery. |
| `design_system.py` | 134 | да | — | Shared, theme-aware presentation. No application data or navigation side effects. |
| `device_notifications.py` | 136 | да | — | Build an account-scoped Android alarm plan. No remote token in native data. |
| `device_session.py` | 136 | да | — | Восстановление местной Android-сессии из закрытого каталога приложения. |
| `download_service.py` | 50 | да | — | Короткоживущие одноразовые ссылки на PNG, без доступа к файлам пользователя. |
| `feed_service.py` | 33 | да | да | Порционная лента с фильтрами и устойчивым порядком. |
| `file_export.py` | 69 | да | — | Byte-oriented export: Android documents, browser downloads, atomic desktop files. |
| `interface_catalog.py` | 12 | да | да | Static English vocabulary shared by presentation and built-in search. No network. |
| `learning_assets.py` | 12 | да | да | Явный каталог авторских геометрических моделей и учебных схем. |
| `learning_catalog.py` | 194 | да | да | Editable catalogue. Publications are versioned; binary files are immutable. |
| `lesson_library.py` | 152 | да | да | Личная библиотека встроенных уроков и история поиска в клиентской SQLite. |
| `lesson_service.py` | 284 | да | да |  |
| `localization.py` | 110 | да | — | Offline Russian/English presentation; database values and user text stay intact. |
| `mail_service.py` | 44 | да | да | Доставка писем через HTTPS API Resend. Ключ задаётся вне исходного кода. |
| `main.py` | 204 | — | — |  |
| `mesh_renderer.py` | 120 | да | да | Небольшой OBJ-просмотрщик: перспективная проекция, отсечение граней и свет. |
| `model_import.py` | 117 | да | да | Ограниченный импорт OBJ/MTL без распаковки файлов в файловую систему. |
| `model_service.py` | 138 | да | — | Каталог встроенных OBJ и личное избранное моделей. |
| `model_upload.py` | 62 | да | — | Одноразовая ограниченная передача личной модели из браузера. |
| `moderation_gateway.py` | 92 | да | — | Жалобы и панель: текущая локальная база или API, без обхода прав при сбое. |
| `moderation_service.py` | 168 | да | да | Жалобы и администрирование. actorId передаёт проверенный шлюз/API. |
| `notification_center.py` | 49 | да | — | Объединение локальных личных событий и страниц API с разными пространствами ID. |
| `notification_mail.py` | 106 | — | да | Opt-in mail spool. Disabled unless the server operator explicitly enables it. |
| `offline_access.py` | 47 | да | — | Ограниченный доступ к личным данным по ранее подтверждённой серверной сессии. |
| `offline_mutations.py` | 49 | да | да | Повторяемые серверные действия: заданный лайк и комментарий с квитанцией. |
| `password_service.py` | 22 | да | да | Общий формат пароля для регистрации, входа и изменения пароля. |
| `personal_checkpoints.py` | 54 | да | — | Пять последних полных копий в личной SQLite, атомарное восстановление. |
| `personal_notices.py` | 105 | да | — | Личные события устройства: дедлайны и обучение. Доставка при открытии приложения. |
| `personal_snapshot.py` | 144 | да | да | Перенос личных данных без аккаунтов, токенов, чужих ID и публикаций. |
| `personal_sync.py` | 111 | да | — | Ручная двусторонняя синхронизация снимка с проверкой версий и локальных изменений. |
| `personal_vault.py` | 53 | да | да | Версии личного снимка на сервере. Владельца задаёт проверенный Bearer-токен. |
| `photo_picker.py` | 115 | да | — |  |
| `photo_service.py` | 65 | да | да | Проверка фотографий до записи: исходники пользователя не изменяются. |
| `photo_upload.py` | 98 | да | — | Одноразовая загрузка фото из браузера. Черновики живут только в памяти. |
| `post_service.py` | 312 | да | да |  |
| `profile_service.py` | 227 | да | да |  |
| `project_archive.py` | 113 | да | да | Перенос личного проекта: ограниченный JSON, без ID владельца и путей файлов. |
| `project_backups.py` | 56 | да | — | Копии JSON в закрытом каталоге Android, раздельно для местных владельцев. |
| `project_planner.py` | 103 | да | да | Личный календарь и локальные напоминания. Фоновой push-доставки нет. |
| `project_service.py` | 336 | да | да |  |
| `project_sharing.py` | 268 | да | да | Связь личного проекта с палитрой и публикацией. |
| `project_statistics.py` | 18 | да | — | Статистика по дате последнего завершения; старые даты не выдумываются. |
| `project_upload.py` | 76 | да | — | Ограниченная одноразовая загрузка JSON с проверкой сессии. |
| `publication_drafts.py` | 39 | да | — | Незавершённые публикации: фото и текст сохраняются отдельно для владельца/API. |
| `pull_refresh.py` | 26 | да | — | Native refresh gesture and a portable scroll fallback, one scroll owner. |
| `reference_service.py` | 28 | да | — |  |
| `remote_account_cache.py` | 69 | да | — | Привязка серверного аккаунта к отдельному владельцу локальных проектов. |
| `role_service.py` | 87 | да | да | Явные полномочия администрирования; встроенные роли не редактируются. |
| `scripts/__init__.py` | 1 | — | — | Служебные команды проекта; не содержат пользовательских данных и секретов. |
| `scripts/coursework_files.py` | 69 | — | — | Explicit final coursework delivery allowlist; never glob application data. |
| `scripts/create_server_demo.py` | 45 | — | — | Однократное создание тестового пользователя в существующей серверной базе. |
| `scripts/generate_coursework_demo.py` | 64 | — | — | Generate portable sample assets using a temporary DB; never provision a real server account. |
| `scripts/generate_final_inventory.py` | 54 | — | — | Export schema/API/source inventory from an isolated fresh database, never a user database. |
| `scripts/generate_learning_models.py` | 212 | — | — | Авторские OBJ из геометрических деталей и 37 пошаговых 3D-схем. |
| `scripts/manage_admin.py` | 45 | — | — | Назначить первого администратора в явно выбранной существующей базе. |
| `scripts/prepare_android.py` | 150 | — | — | Готовит отдельную папку сборки без баз, .env и сервера. |
| `scripts/prepare_review.py` | 73 | — | — | Архив контрольной версии по явному списку, без личных баз и секретов. |
| `scripts/prepare_server.py` | 41 | — | — | Подготовить новый серверный пакет по явному списку, без GUI, баз и секретов. |
| `scripts/run_final_checks.py` | 56 | — | — | Run the real unittest suite with per-case JSON evidence and no external mail. |
| `scripts/run_wifi_server.py` | 32 | — | — | Запуск API в домашней сети без Docker: python -m scripts.run_wifi_server. |
| `scripts/server_backup.py` | 46 | — | — | Согласованная копия SQLite; восстановление только в новый файл, без старых сессий. |
| `secure_device.py` | 75 | да | — | Android Keystore bridge. No plaintext-token fallback and no browser storage. |
| `social_feed.py` | 37 | да | да | Единый личный список: награды и события публикаций, без копирования текста материалов. |
| `ui_helpers.py` | 107 | да | — |  |
| `validators.py` | 66 | да | да |  |
| `views/about_dialog.py` | 30 | да | — |  |
| `views/admin_permissions.py` | 14 | да | — | Короткий снимок для видимости кнопок. Разрешение действия всегда проверяет сервис. |
| `views/admin_view.py` | 140 | да | — |  |
| `views/auth_view.py` | 333 | да | — |  |
| `views/catalog_file_picker.py` | 53 | да | — |  |
| `views/challenge_view.py` | 219 | да | — |  |
| `views/clay_tools_view.py` | 108 | да | — |  |
| `views/color_scan.py` | 114 | да | — |  |
| `views/community_notices.py` | 159 | да | — |  |
| `views/community_tab.py` | 491 | да | — |  |
| `views/contest_picker.py` | 39 | да | — |  |
| `views/discovery.py` | 203 | да | — |  |
| `views/home_view.py` | 2060 | да | — |  |
| `views/learning_catalog.py` | 232 | да | — |  |
| `views/lesson_library_view.py` | 94 | да | — |  |
| `views/model_gallery.py` | 99 | да | — |  |
| `views/model_import.py` | 80 | да | — |  |
| `views/model_view.py` | 151 | да | — |  |
| `views/moderation_actions.py` | 57 | да | — |  |
| `views/notification_delivery.py` | 75 | да | — |  |
| `views/offline_controls.py` | 138 | да | — |  |
| `views/onboarding_view.py` | 157 | да | — |  |
| `views/personal_data.py` | 226 | да | — |  |
| `views/personal_notice_settings.py` | 23 | да | — |  |
| `views/profile_edit_view.py` | 49 | — | — |  |
| `views/profile_tab.py` | 770 | да | — |  |
| `views/profile_view.py` | 40 | — | — |  |
| `views/project_editor.py` | 166 | да | — |  |
| `views/project_planner.py` | 131 | да | — |  |
| `views/project_sharing.py` | 159 | да | — |  |
| `views/project_statistics.py` | 34 | да | — |  |
| `views/project_step_order.py` | 55 | да | — |  |
| `views/project_transfer.py` | 190 | да | — |  |
| `views/reference_gallery.py` | 80 | да | — |  |
| `views/report_history.py` | 38 | да | — |  |
| `views/role_editor.py` | 57 | да | — |  |
| `views/server_connection.py` | 61 | да | — |  |
| `views/splash_view.py` | 114 | да | — |  |
| `views/workshop_view.py` | 146 | да | — |  |
| `web_app.py` | 36 | — | — | Веб-запуск Flet с отдельным маршрутом скачивания PNG. |
| `workshop_service.py` | 112 | да | да | Чтение опубликованного мастер-класса и личный прогресс читателя. |
