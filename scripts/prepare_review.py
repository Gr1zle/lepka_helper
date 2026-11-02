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
from scripts.prepare_android import MODULES, VIEWS, ASSETS,NATIVE_FILES

DOCS = ('ТЗ', 'Plan', 'day1_requirements_audit.md', 'day2_stabilization.md', 'day3_tools.md',
        'day4_community_android.md', 'account_backend_validation.md', 'avatar_stage_photos.md',
        'project_sharing.md', 'workshops.md', 'server_community.md', 'review_version.md', 'project_step_order.md', 'project_tools_batch.md', 'lesson_library_search.md', 'offline_models_media.md', 'development_backlog.md', 'project_calendar_reminders.md', 'model_import_fullscreen.md', 'community_moderation.md', 'community_challenges.md','challenge_results.md','community_complete_batch.md','roles_admin_server.md','wifi_server.md','personal_notices_performance.md','personal_vault_sync.md','remaining_work.md','offline_session_outbox.md','notification_delivery.md','learning_catalog.md','color_camera_references.md','design_system.md','discovery_navigation.md','project_workflow.md','english_community.md')
TESTS = ('accounts', 'android_package', 'backend', 'clay_tools', 'community', 'community_api',
         'community_gateway', 'gateway', 'profile_stage_media', 'project_sharing', 'projects',
         'startup', 'workshops', 'review_release', 'device_session', 'project_batch', 'lesson_library', 'models', 'project_planner', 'model_import', 'moderation', 'challenges','challenge_results','community_batch','roles_admin','server_package','wifi_connection','personal_notices','personal_sync','offline_outbox','notification_delivery','learning_catalog','color_camera','design_system','discovery','project_workflow','localization')
SCREENSHOTS = ('english-community-home-320.png','english-community-home-390.png','english-community-colors-390.png','english-community-colors-dark-820.png','english-community-create-post.png','english-community-alice-reply.png','english-community-alice-inbox.png','english-community-bob-inbox.png','project-workflow-detail-390.png','project-workflow-order-before.png','project-workflow-order-after.png','project-workflow-added-step.png','project-workflow-final-required.png','project-workflow-completed-320.png','project-workflow-publication.png','project-workflow-delete-confirm.png','project-workflow-dark-820.png','discovery-home-320.png','discovery-home-1440.png','discovery-search-empty.png','discovery-search-results.png','discovery-catalogue.png','discovery-post.png','discovery-create-project.png','discovery-project-list.png','discovery-project-detail.png','discovery-notifications.png','discovery-create-post.png','discovery-color-full.png','discovery-color-zoom.png','discovery-color-return.png','design-auth-390.png','design-home-390.png','design-colors-390.png','design-search-1440.png','design-projects-320.png','design-profile-390.png','design-colors-dark-320.png','design-colors-dark-1440.png','design-model-full-820.png','color-camera-dialog-320.png','color-reference-320.png','catalog-list-390.png','catalog-offline-320.png','catalog-model-full-320.png','offline-draft-390.png','offline-queue-320.png','offline-delivered-320.png','sync-device-a.png','sync-device-b.png','sync-download-confirm.png','sync-conflict-320.png','personal-colors-immediate.png','personal-notices-390.png','personal-settings-320.png','roles-editor.png','roles-scoped-panel-320.png','roles-my-report.png','roles-delete-confirm.png','roles-audit.png','community-center.png','community-reply.png','community-reply-notice.png','community-grid-wide.png','community-grid-320.png','community-publish-contest.png','results-awards-320.png','results-notice-320.png','results-profile-320.png','results-scheduled-320.png','challenges-list-320.png','challenges-entry-320.png','challenges-create.png','day4-community-form.png', 'day4-community-post.png', 'profile-avatar.png',
               'moderation-panel-320.png','moderation-confirm-delete.png','moderation-user-blocked.png','moderation-audit.png',
               'projects-edit-fixed-wide.png', 'projects-edit-fixed-320.png', 'import-full-portrait.png', 'import-full-landscape.png', 'import-full-320.png', 'import-personal-library.png',
               'planner-calendar.png', 'planner-320.png', 'planner-reminders.png', 'planner-project.png',
               'models-gallery.png', 'models-view-320.png', 'models-step-enlarged.png', 'models-favorites.png',
               'library-suggestions.png', 'library-note-320.png', 'library-profile-favorites.png', 'library-resume.png',
               'batch-order-320.png', 'batch-import-preview.png', 'batch-calculator.png', 'batch-timer.png',
               'project-step-photo.png', 'project-copied-recipe.png', 'project-publication-recipe.png',
               'workshop-320.png', 'workshop-desktop.png', 'workshop-step-390.png',
               'server-community-feed.png', 'server-community-workshop.png', 'review-home.png', 'review-profile.png')


def getReviewFiles():
    return ['README.md', 'REVIEW_START.md', 'requirements.txt', '.gitignore', 'main.py', 'web_app.py',
             *['native/lepka_platform/'+name for name in NATIVE_FILES],
             *[name + '.py' for name in MODULES], *['views/' + name + '.py' for name in VIEWS],
             *['assets/' + name for name in ASSETS], 'assets/logo.png', 'assets/lessons/README.md', 'assets/models/README.md',
             'backend/__init__.py', 'backend/main.py', 'backend/community.py', 'backend/moderation.py', 'backend/challenges.py','backend/personal.py','backend/delivery.py','backend/catalog.py', 'backend/requirements.txt',
             'backend/README.md','backend/Dockerfile','backend/compose.yml','backend/Caddyfile','backend/.env.example','.dockerignore',
             'scripts/__init__.py','scripts/prepare_server.py','scripts/server_backup.py', 'scripts/run_wifi_server.py', 'scripts/prepare_android.py', 'scripts/prepare_review.py',
             'scripts/create_server_demo.py', 'scripts/generate_learning_models.py', 'scripts/manage_admin.py', 'tests/image_fixtures.py',
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
