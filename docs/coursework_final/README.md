# Lepka Helper 0.18 — материалы к защите

Итоговая оценка: **PARTIAL**. Код и доступные проверки выполнены; физический Android, домашняя Wi-Fi-сеть и реальные письма требуют ручного прогона. Не все пункты первоначального ТЗ реализованы — они явно перечислены в отчёте.

Начните с [итогового отчёта](FINAL_REPORT.md), затем используйте [сценарий защиты](DEMO_SCENARIO.md).

| Документ | Содержание |
|---|---|
| [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | Назначение, возможности, режимы и ограничения |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Клиент, API, хранение, безопасность, схемы |
| [DATABASE.md](DATABASE.md) | Все 58 таблиц, поля, ключи, индексы и ограничения |
| [ER_DIAGRAM.mmd](ER_DIAGRAM.mmd) | Полная ER-диаграмма |
| [FUNCTIONAL_REQUIREMENTS.md](FUNCTIONAL_REQUIREMENTS.md) | 45 требований и фактические статусы |
| [TEST_CASES.md](TEST_CASES.md) | Шаги, результаты и отдельный ручной чек-лист |
| [AUTOMATED_TESTS.md](AUTOMATED_TESTS.md) | Реестр всех автоматизированных проверок |
| [USER_GUIDE.md](USER_GUIDE.md) | Руководство по фактическому интерфейсу |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Windows, ПК-сервер, Wi-Fi, APK, копии и диагностика |
| [DEMO_SCENARIO.md](DEMO_SCENARIO.md) | Защита 5–7 и 15–25 минут, подготовка и резервный план |
| [MODULE_INDEX.md](MODULE_INDEX.md) | Инвентаризация Python-модулей |
| [API_REFERENCE.md](API_REFERENCE.md) | 81 операция API |
| [demo/README.md](demo/README.md) | Проверенные искусственные файлы для демонстрации |

Результаты: [518 тестов](evidence/automated_tests.json), [два клиента и перезапуск API](evidence/browser_core.json), [проекты](evidence/browser_projects.json), [исправление до/после](evidence/challenge_regression.json), [Android-оборудование](evidence/android_hardware.json), [APK](evidence/apk.json). [Снимки](evidence/screenshots/) — браузерные, не снимки физического телефона. Исходные ТЗ/Plan не редактировались; [их контрольные суммы](evidence/original_documents.json).
