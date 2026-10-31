"""Архив контрольной версии по явному списку, без личных баз и секретов."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_info import APP_VERSION, REVIEW_DATE
from scripts.prepare_android import MODULES, VIEWS, ASSETS

DOCS = ('ТЗ', 'Plan', 'day1_requirements_audit.md', 'day2_stabilization.md', 'day3_tools.md',
        'day4_community_android.md', 'account_backend_validation.md', 'avatar_stage_photos.md',
        'project_sharing.md', 'workshops.md', 'server_community.md', 'review_version.md', 'project_step_order.md', 'project_tools_batch.md', 'lesson_library_search.md', 'offline_models_media.md')
TESTS = ('accounts', 'android_package', 'backend', 'clay_tools', 'community', 'community_api',
         'community_gateway', 'gateway', 'profile_stage_media', 'project_sharing', 'projects',
         'startup', 'workshops', 'review_release', 'device_session', 'project_batch', 'lesson_library', 'models')
SCREENSHOTS = ('day4-community-form.png', 'day4-community-post.png', 'profile-avatar.png',
               'models-gallery.png', 'models-view-320.png', 'models-step-enlarged.png', 'models-favorites.png',
               'library-suggestions.png', 'library-note-320.png', 'library-profile-favorites.png', 'library-resume.png',
               'batch-order-320.png', 'batch-import-preview.png', 'batch-calculator.png', 'batch-timer.png',
               'project-step-photo.png', 'project-copied-recipe.png', 'project-publication-recipe.png',
               'workshop-320.png', 'workshop-desktop.png', 'workshop-step-390.png',
               'server-community-feed.png', 'server-community-workshop.png', 'review-home.png', 'review-profile.png')


def getReviewFiles():
    return ['README.md', 'REVIEW_START.md', 'requirements.txt', '.gitignore', 'main.py', 'web_app.py',
             *[name + '.py' for name in MODULES], *['views/' + name + '.py' for name in VIEWS],
             *['assets/' + name for name in ASSETS], 'assets/logo.png', 'assets/lessons/README.md', 'assets/models/README.md',
             'backend/__init__.py', 'backend/main.py', 'backend/community.py', 'backend/requirements.txt',
             'backend/README.md', 'scripts/prepare_android.py', 'scripts/prepare_review.py',
             'scripts/create_server_demo.py', 'scripts/generate_learning_models.py', 'tests/image_fixtures.py',
             *['tests/test_' + name + '.py' for name in TESTS], *['docs/' + name for name in DOCS],
             *['docs/screenshots/' + name for name in SCREENSHOTS]]


def prepareReview(output):
    output = Path(output).expanduser().resolve()
    if output.suffix.lower() != '.zip':
        raise ValueError('Укажите новое имя ZIP-архива')
    files = getReviewFiles()
    contents = {name: (ROOT / name).read_bytes() for name in files}
    # Архив не наследует адрес API из личной конфигурации отправителя.
    contents['assets/client_config.json'] = b'{"apiBaseUrl": ""}\n'
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    manifest = {'version': APP_VERSION, 'reviewDate': REVIEW_DATE, 'sourceCommit': commit,
                'files': {name: hashlib.sha256(content).hexdigest() for name, content in sorted(contents.items())}}
    contents['REVIEW_MANIFEST.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'x', compression=ZIP_DEFLATED) as archive:
        for name, content in sorted(contents.items()):
            archive.writestr(f'lepka-helper-{APP_VERSION}/{name}', content)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    options = parser.parse_args()
    print(prepareReview(options.output))
