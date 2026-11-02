"""Запуск API в домашней сети без Docker: python -m scripts.run_wifi_server."""
import argparse
import os
from pathlib import Path
import socket


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default=os.environ.get('LEPKA_SERVER_DATA_DIR') or str(Path.home() / 'LepkaHelperServer'))
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--notification-mail', action='store_true', help='Включить почтовую очередь уведомлений (нужны LEPKA_MAIL_API_KEY и LEPKA_MAIL_FROM)')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Порт должен быть от 1 до 65535')
    directory = Path(args.data_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    os.environ['LEPKA_SERVER_DATA_DIR'] = str(directory)
    if args.notification_mail:
        os.environ['LEPKA_NOTIFICATION_MAIL_ENABLED']='1'
    print(f'Данные сервера: {directory}', flush=True)
    addresses = sorted({item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)})
    for address in addresses:
        if not address.startswith('127.'):
            print(f'Возможный адрес для телефона: http://{address}:{args.port}', flush=True)
    print('Если адрес не подходит, посмотрите IPv4 Wi-Fi адаптера командой ipconfig. Остановка: Ctrl+C.', flush=True)
    import uvicorn
    uvicorn.run('backend.main:app', host='0.0.0.0', port=args.port, workers=1, proxy_headers=False)


if __name__ == '__main__':
    main()
