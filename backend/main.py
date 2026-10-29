"""Запуск: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000."""
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import os
from pathlib import Path
import threading
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

import account_security as security
import auth_service as accounts
import database
import profile_service as profiles


class InputModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class EmailInput(InputModel):
    email: str = Field(max_length=100)


class LoginInput(EmailInput):
    password: str = Field(max_length=64)


class RegisterInput(LoginInput):
    passwordConfirmation: str = Field(max_length=64)
    nickname: str = Field(max_length=20)
    isPolicyAccepted: bool


class ConfirmInput(EmailInput):
    code: str = Field(max_length=20)


class ResetInput(EmailInput):
    newPassword: str = Field(max_length=64)
    newPasswordConfirmation: str = Field(max_length=64)
    recoveryCode: str = Field(max_length=20)


class ProfileInput(InputModel):
    nickname: str = Field(max_length=20)
    bioText: str = Field(max_length=500)
    ageCategory: str = Field(max_length=40)
    favoriteColors: list[str] = Field(max_length=5)
    # Загрузка файлов требует отдельного API. Пути устройства сервер не принимает.
    avatarPath: str = Field(default='', max_length=0)


class SettingsInput(InputModel):
    themeMode: str = Field(max_length=10)
    languageCode: str = Field(max_length=5)
    notificationsEnabled: bool


class PasswordInput(InputModel):
    currentPassword: str = Field(max_length=64)
    newPassword: str = Field(max_length=64)
    repeatedNewPassword: str = Field(max_length=64)


class DeleteInput(InputModel):
    password: str = Field(max_length=64)


class NewEmailInput(InputModel):
    newEmail: str = Field(max_length=100)
    password: str = Field(max_length=64)


class ConfirmEmailInput(InputModel):
    newEmail: str = Field(max_length=100)
    code: str = Field(max_length=20)


bearer = HTTPBearer(auto_error=False)


def currentUser(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    user = security.getSessionUser(credentials.credentials) if credentials else None
    if user is None:
        raise HTTPException(401, 'Сессия завершена. Выполните вход снова',
                            headers={'WWW-Authenticate': 'Bearer'})
    return user


def resultResponse(result):
    success, message, *data = result
    if not success:
        raise HTTPException(400, message)
    return {'message': message, 'data': data[0] if data else None}


def createApp(dataDirectory=None):
    @asynccontextmanager
    async def lifespan(application):
        directory = dataDirectory or os.environ.get('LEPKA_SERVER_DATA_DIR')
        if not directory:
            raise RuntimeError('Задайте LEPKA_SERVER_DATA_DIR — отдельную папку базы сервера')
        directory = Path(directory).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        previousPath = database.DATABASE_PATH
        database.DATABASE_PATH = directory / 'accounts.db'
        try:
            database.initializeDatabase()
            yield
        finally:
            database.DATABASE_PATH = previousPath

    application = FastAPI(title='Lepka Helper Accounts', version='1.0', lifespan=lifespan)
    attempts = defaultdict(deque)
    attemptsLock = threading.Lock()

    @application.middleware('http')
    async def limitPublicRequests(request: Request, callNext):
        # Один процесс сервера: общий лимит запросов с адреса за минуту.
        # Счётчики входа и неверных кодов дополнительно хранятся в SQLite.
        if request.method == 'POST' and request.url.path.startswith('/auth/'):
            address = request.client.host if request.client else 'unknown'
            now = time.monotonic()
            with attemptsLock:
                for key in list(attempts):
                    if not attempts[key] or attempts[key][-1] <= now - 60:
                        del attempts[key]
                history = attempts[address]
                while history and history[0] <= now - 60:
                    history.popleft()
                if len(history) >= 30:
                    return JSONResponse({'detail': 'Слишком много запросов. Повторите через минуту'},
                                        status_code=429, headers={'Retry-After': '60'})
                history.append(now)
        return await callNext(request)

    @application.exception_handler(RequestValidationError)
    async def validationError(request, error):
        # Стандартный ответ Pydantic может включать введённые пароли.
        return JSONResponse({'detail': 'Проверьте поля запроса: неверный формат или лишние поля'}, status_code=422)

    @application.get('/health')
    def health():
        return {'status': 'ok'}

    @application.post('/auth/register')
    def register(body: RegisterInput):
        return resultResponse(accounts.registerUser(**body.model_dump()))

    @application.post('/auth/login')
    def login(body: LoginInput):
        return resultResponse(accounts.loginUser(**body.model_dump()))

    @application.post('/auth/registration/code')
    def registrationCode(body: EmailInput):
        return resultResponse(accounts.requestRegistrationCode(body.email))

    @application.post('/auth/registration/confirm')
    def registrationConfirm(body: ConfirmInput):
        return resultResponse(security.confirmRegistration(body.email, body.code))

    @application.post('/auth/recovery/code')
    def recoveryCode(body: EmailInput):
        return resultResponse(accounts.requestPasswordRecovery(body.email))

    @application.post('/auth/recovery/confirm')
    def recoveryConfirm(body: ResetInput):
        return resultResponse(accounts.changePasswordByEmail(**body.model_dump()))

    @application.get('/auth/me')
    def session(user=Depends(currentUser)):
        return {'data': security.makePublicUser(user)}

    @application.post('/auth/logout')
    def logout(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials:
            security.logoutUser(credentials.credentials)
        return {'message': 'Выход выполнен', 'data': None}

    @application.get('/profile')
    def profile(user=Depends(currentUser)):
        return {'data': profiles.getUserProfile(user['userId'])}

    @application.put('/profile')
    def saveProfile(body: ProfileInput, user=Depends(currentUser)):
        return resultResponse(profiles.saveUserProfile(user['userId'], **body.model_dump()))

    @application.put('/profile/avatar')
    async def avatar(request: Request, user=Depends(currentUser)):
        # Клиент отправляет уже уменьшенный PNG; владелец берётся только из токена.
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 2 * 1024 * 1024:
                raise HTTPException(413, 'Аватар после обработки должен быть не больше 2 МБ')
            body.extend(chunk)
        result = await run_in_threadpool(profiles.saveUserAvatar, user['userId'], bytes(body))
        return resultResponse(result)

    @application.delete('/profile/avatar')
    def deleteAvatar(user=Depends(currentUser)):
        return resultResponse(profiles.removeUserAvatar(user['userId']))

    @application.put('/profile/settings')
    def settings(body: SettingsInput, user=Depends(currentUser)):
        return resultResponse(profiles.saveUserSettings(user['userId'], **body.model_dump()))

    @application.post('/account/password')
    def password(body: PasswordInput, user=Depends(currentUser)):
        return resultResponse(profiles.changeUserPassword(user['userId'], **body.model_dump()))

    @application.post('/account/email/code')
    def newEmail(body: NewEmailInput, user=Depends(currentUser)):
        return resultResponse(accounts.requestEmailChange(user['userId'], **body.model_dump()))

    @application.post('/account/email/confirm')
    def confirmEmail(body: ConfirmEmailInput, user=Depends(currentUser)):
        return resultResponse(accounts.confirmEmailChange(user['userId'], **body.model_dump()))

    @application.delete('/account')
    def delete(body: DeleteInput, user=Depends(currentUser)):
        return resultResponse(accounts.deleteUserAccount(user['userId'], body.password))

    return application


app = createApp()
