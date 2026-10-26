from password_service import createPasswordHash as hashWithSalt, checkPassword
import secrets

from database import createUser, deleteUserDataById, getUserByEmail, getUserByNickname, updateUserPassword
from validators import (
    validateEmail,
    validatePassword,
    validatePasswordConfirmation,
    validateNickname,
)


def createPasswordHash(password, passwordSalt):
    return hashWithSalt(password, passwordSalt)[0]


def registerUser(email, password, passwordConfirmation, nickname, isPolicyAccepted):
    email = email.strip().lower()
    nickname = nickname.strip()

    emailError = validateEmail(email)
    if emailError:
        return False, emailError, None

    nicknameError = validateNickname(nickname)
    if nicknameError:
        return False, nicknameError, None

    passwordError = validatePassword(password)
    if passwordError:
        return False, passwordError, None

    confirmationError = validatePasswordConfirmation(password, passwordConfirmation)
    if confirmationError:
        return False, confirmationError, None

    if not isPolicyAccepted:
        return False, "Необходимо согласиться с политикой конфиденциальности", None

    existingEmailUser = getUserByEmail(email)
    if existingEmailUser:
        return False, "Пользователь с таким email уже зарегистрирован", None

    existingNicknameUser = getUserByNickname(nickname)
    if existingNicknameUser:
        return False, "Такой никнейм уже занят", None

    passwordSalt = secrets.token_hex(16)
    passwordHash = createPasswordHash(password, passwordSalt)

    userId = createUser(email, passwordHash, passwordSalt, nickname)

    return True, "Регистрация прошла успешно", {
        "userId": userId,
        "email": email,
        "nickname": nickname,
        "roleName": "user",
    }


def loginUser(email, password):
    email = email.strip().lower()

    emailError = validateEmail(email)
    if emailError:
        return False, emailError, None

    if not password:
        return False, "Введите пароль", None

    userRecord = getUserByEmail(email)
    if not userRecord:
        return False, "Неверный email или пароль", None

    if userRecord["isBlocked"] == 1:
        return False, "Аккаунт заблокирован", None

    if not checkPassword(password, userRecord["passwordHash"], userRecord["passwordSalt"]):
        return False, "Неверный email или пароль", None

    return True, f"Добро пожаловать, {userRecord['nickname']}!", {
        "userId": userRecord["userId"],
        "email": userRecord["email"],
        "nickname": userRecord["nickname"],
        "roleName": userRecord["roleName"],
    }

def deleteUserAccount(email, password):
    email = email.strip().lower()

    userRecord = getUserByEmail(email)

    if not userRecord:
        return False, "Пользователь не найден"

    if not checkPassword(password, userRecord["passwordHash"], userRecord["passwordSalt"]):
        return False, "Неверный пароль"

    deleteUserDataById(userRecord["userId"])

    return True, "Аккаунт удалён"


def changePasswordByEmail(email, newPassword, newPasswordConfirmation):
    email = email.strip().lower()

    emailError = validateEmail(email)
    if emailError:
        return False, emailError

    passwordError = validatePassword(newPassword)
    if passwordError:
        return False, passwordError

    confirmationError = validatePasswordConfirmation(newPassword, newPasswordConfirmation)
    if confirmationError:
        return False, confirmationError

    userRecord = getUserByEmail(email)
    if not userRecord:
        return False, "Пользователь с таким email не найден"

    passwordSalt = secrets.token_hex(16)
    passwordHash = createPasswordHash(newPassword, passwordSalt)
    updateUserPassword(userRecord["userId"], passwordHash, passwordSalt)

    return True, "Пароль успешно изменён. Теперь можно войти."


def ensureDemoUser():
    """Создаёт тестового пользователя для быстрой проверки приложения."""
    demoEmail = "test@email.com"
    demoPassword = "Test123456"
    demoNickname = "test_user"

    existingUser = getUserByEmail(demoEmail)
    if existingUser:
        return {
            "userId": existingUser["userId"],
            "email": existingUser["email"],
            "nickname": existingUser["nickname"],
            "roleName": existingUser["roleName"],
        }

    passwordSalt = secrets.token_hex(16)
    passwordHash = createPasswordHash(demoPassword, passwordSalt)
    userId = createUser(demoEmail, passwordHash, passwordSalt, demoNickname)

    return {
        "userId": userId,
        "email": demoEmail,
        "nickname": demoNickname,
        "roleName": "user",
    }
