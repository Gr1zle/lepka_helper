"""Доставка писем через HTTPS API Resend. Ключ задаётся вне исходного кода."""
import os
import requests


class MailDeliveryError(Exception):
    pass


def sendAccountCode(email, code, purpose):
    apiKey = os.environ.get('LEPKA_MAIL_API_KEY')
    sender = os.environ.get('LEPKA_MAIL_FROM')
    if not apiKey or not sender:
        raise MailDeliveryError('Отправка писем не настроена. Обратитесь к администратору')
    titles = {'registration': 'Подтверждение регистрации',
              'recovery': 'Восстановление пароля', 'email': 'Подтверждение нового email'}
    lifetime = '24 часа' if purpose == 'registration' else '10 минут'
    try:
        response = requests.post(
            'https://api.resend.com/emails',
            headers={'Authorization': f'Bearer {apiKey}'},
            json={'from': sender, 'to': [email], 'subject': f'Lepka Helper — {titles[purpose]}',
                  'text': f'Код: {code}\nДействует {lifetime}. Никому не сообщайте этот код.'},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        # Ответ сервиса и ключ не попадают в интерфейс или журнал приложения.
        raise MailDeliveryError('Не удалось отправить письмо. Повторите позже') from error
