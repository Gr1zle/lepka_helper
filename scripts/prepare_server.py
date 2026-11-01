"""Подготовить новый серверный пакет по явному списку, без GUI, баз и секретов."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
MODULES=('personal_vault','personal_snapshot','project_archive','project_service','model_import','mesh_renderer','account_security','activity_service','app_paths','auth_service','challenge_service','color_service',
 'contest_entry','database','feed_service','learning_assets','lesson_service','mail_service','moderation_service',
 'password_service','photo_service','post_service','profile_service','project_sharing','role_service','social_feed','validators','workshop_service')
FILES=(*[m+'.py' for m in MODULES],'backend/__init__.py','backend/main.py','backend/community.py','backend/moderation.py',
 'backend/challenges.py','backend/personal.py','backend/requirements.txt','backend/Dockerfile','backend/README.md','backend/compose.yml',
 'backend/Caddyfile','backend/.env.example','docs/roles_admin_server.md','scripts/__init__.py','scripts/manage_admin.py','scripts/server_backup.py','scripts/run_wifi_server.py','scripts/create_server_demo.py','docs/wifi_server.md','docs/personal_vault_sync.md','docs/remaining_work.md',
 'docs/screenshots/sync-device-a.png','docs/screenshots/sync-device-b.png','docs/screenshots/sync-download-confirm.png','docs/screenshots/sync-conflict-320.png','.dockerignore')


def prepareServer(output):
    output=Path(output).expanduser().resolve()
    if output.exists():raise ValueError('Выберите новую папку для серверного пакета')
    contents={name:(ROOT/name).read_bytes() for name in FILES}
    for name,data in contents.items():
        if name.endswith('.py'):ast.parse(data)
    try:commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    except (OSError,subprocess.CalledProcessError):commit=None
    output.mkdir(parents=True)
    for name,data in contents.items():
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    (output/'SERVER_MANIFEST.json').write_text(json.dumps({'sourceCommit':commit,'files':{name:hashlib.sha256(data).hexdigest() for name,data in contents.items()}},ensure_ascii=False,indent=2))
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:print(prepareServer(args.output))
    except (ValueError,OSError) as error:parser.exit(1,str(error)+'\n')
