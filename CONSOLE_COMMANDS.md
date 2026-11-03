# Команды Lepka Helper — Windows PowerShell

Выполняйте из папки проекта или распакованного **серверного пакета**. Нужен Python 3.12. Не меняйте привычную папку данных сервера при обновлении: в ней `accounts.db`, аккаунты и общее сообщество. Телефон и ПК подключаются к одному роутеру; Docker и хостинг не нужны.

## 1. Установка один раз

```powershell
py -3.12 -m venv .server-venv
.\.server-venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.server-venv\Scripts\python.exe -m pip check
```

При обновлении распакуйте новый сервер отдельно, повторите установку зависимостей и используйте **прежний** `--data-dir`. Активация venv не требуется.

## 2. Обычный запуск сервера

```powershell
.\.server-venv\Scripts\python.exe -m scripts.run_wifi_server --data-dir "$HOME\LepkaHelperServer" --port 8000
```

Окно оставить открытым. Остановка — **Ctrl+C**. Для повторного запуска — та же команда.

| Настройка | Что означает |
|---|---|
| `--data-dir` | Постоянная папка с серверной `accounts.db`; на чистом запуске создаётся автоматически. Замените пример на свой прежний путь |
| Без `--data-dir` | Берётся `LEPKA_SERVER_DATA_DIR`, иначе `$HOME\LepkaHelperServer` |
| `--port 8000` | TCP-порт, по умолчанию 8000. При изменении изменить также адрес на телефоне и правило Firewall |
| `--notification-mail` | Включает очередь **писем о событиях** сообщества. Нужны Resend и настройки доставки пользователя; по умолчанию выключена, если env не включает её |
| Адрес прослушивания | Launcher всегда использует `0.0.0.0`, один процесс. Отдельного `--host` нет; `0.0.0.0` не вводится в телефон |

Все допустимые параметры:

```powershell
.\.server-venv\Scripts\python.exe -m scripts.run_wifi_server --help
```

## 3. Проверка и подключение телефона

В **другом** окне PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
ipconfig
```

Ожидается `status=ok` / `status=ready`. В `ipconfig` найдите IPv4 активного сетевого адаптера, например `192.168.1.10`. В браузере телефона откройте `http://192.168.1.10:8000/ready`. В приложении «Подключение к серверу / Wi-Fi»: тот же адрес **без `/ready`**, разрешить HTTP своей сети, проверить связь, сохранить и войти. `127.0.0.1` на телефоне указывает на сам телефон.

Если соединение блокирует Windows Firewall, разрешите Python в частной сети. Альтернатива — PowerShell **администратора**:

```powershell
New-NetFirewallRule -DisplayName "Lepka Helper API" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Private
```

Проверьте также, что это не гостевая сеть с изоляцией устройств. Компьютер должен оставаться включённым.

## 4. Создание предусмотренного тестового пользователя

Сначала сервер должен хотя бы раз запуститься и создать базу. В другом терминале из той же папки:

```powershell
.\.server-venv\Scripts\python.exe -m scripts.create_server_demo --data-dir "$HOME\LepkaHelperServer"
```

Вход: **`test@email.com` / `Test123456`**. Это общеизвестный учебный аккаунт, почта ему не нужна. Скрипт не заменяет пароль существующего пользователя и не создаёт администратора. Одинаковый тестовый вход на двух устройствах — один пользователь; для двух авторов нужны два обычных зарегистрированных аккаунта.

## 5. Назначение первого администратора

Сначала зарегистрируйте и подтвердите email нужного аккаунта в приложении на **этом сервере**. Замените `owner@example.com` своим email:

```powershell
.\.server-venv\Scripts\python.exe -m scripts.manage_admin --database "$HOME\LepkaHelperServer\accounts.db" --email "owner@example.com"
```

Команда назначает роль существующему подтверждённому незаблокированному аккаунту, записывает аудит и отзывает его прежние сессии. После неё войдите в приложение заново. Она не создаёт пользователя и не меняет пароль. Повторное выполнение для уже назначенного администратора безопасно. Не назначайте публичный тестовый аккаунт администратором сервера с личными данными.

## 6. Почта для регистрации, восстановления и событий

До запуска сервера в **том же терминале** задайте свои значения Resend. В примере только заполнители:

```powershell
$env:LEPKA_MAIL_API_KEY = "<свой-ключ-Resend>"
$env:LEPKA_MAIL_FROM = "Lepka Helper <адрес-разрешённого-отправителя>"
$env:LEPKA_NOTIFICATION_MAIL_ENABLED = "0"
.\.server-venv\Scripts\python.exe -m scripts.run_wifi_server --data-dir "$HOME\LepkaHelperServer" --port 8000
```

Коды регистрации/восстановления/смены email работают независимо от очереди событий. Нужен интернет **у сервера**, допустимый отправитель и разрешённые адресаты Resend. Если нужны также письма о событиях, остановите сервер и повторите запуск с `--notification-mail`. Это не Firebase push. Env действует в текущем терминале; launcher сам `.env` не читает. Реальные ключи не включать в GitHub и APK.

## 7. Резервная копия и восстановление

До смены версии/защиты (выходное имя должно быть новым):

```powershell
.\.server-venv\Scripts\python.exe -m scripts.server_backup backup --source "$HOME\LepkaHelperServer\accounts.db" --output "$HOME\LepkaBackups\before-defense.db"
```

Восстановление **в новый каталог**; текущая база не заменяется:

```powershell
.\.server-venv\Scripts\python.exe -m scripts.server_backup restore --source "$HOME\LepkaBackups\before-defense.db" --output "$HOME\LepkaRestored\accounts.db"
.\.server-venv\Scripts\python.exe -m scripts.run_wifi_server --data-dir "$HOME\LepkaRestored" --port 8000
```

Перед последней командой остановите старый сервер. После восстановления нужно войти заново: сохранённые сессии/коды отзываются. Копии содержат персональные данные, не публикуйте их.

## 8. Клиент на ПК — необязательно, только полный проект

Серверный ZIP не содержит GUI. В полной копии проекта:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:LEPKA_DATA_DIR = "$HOME\LepkaClientA"
$env:LEPKA_API_URL = "http://127.0.0.1:8000"
$env:LEPKA_ALLOW_LOCAL_API = "1"
.\.venv\Scripts\python.exe main.py --port 8550
```

Сохранённое подключение в настройках клиента имеет приоритет над env. Для второго клиента — другое окно, `LEPKA_DATA_DIR="$HOME\LepkaClientB"`, `--port 8551`, другой аккаунт. Для показа без сервера: `main.py --local --port 8552` с отдельной папкой данных; этот режим не демонстрирует общее сообщество.
