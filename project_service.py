import re
from datetime import datetime

from database import (
    createProject,
    createProjectWithSteps,
    updateProjectById,
    updateProjectStepDescription,
    getProjectById,
    createProjectStep,
    deleteProjectById,
    deleteProjectStepById,
    getProjectStepsByProjectId,
    getProjectsByUserId,
    updateProjectProgress,
    updateProjectStepStatus,
    getProjectStepPhoto, setProjectStepPhoto,
    reorderProjectSteps,
)
from photo_service import preparePhoto


# userId в операциях передаётся из текущей сессии пользователя,
# а не из поля формы. Проверка владельца выполняется также в database.py.
PROJECT_CATEGORIES = [
    "Животные",
    "Персонажи",
    "Еда",
    "Транспорт",
    "Аниме",
    "Кавай",
    "Фэнтези",
    "Реализм",
    "Другое",
]


def validateProjectName(projectName):
    if not projectName:
        return "Введите название проекта"

    if len(projectName) < 3:
        return "Название проекта должно быть не короче 3 символов"

    if len(projectName) > 80:
        return "Название проекта должно быть не длиннее 80 символов"

    return None


def validateProjectDescription(descriptionText):
    if descriptionText is None:
        return None

    if len(descriptionText) > 1500:
        return "Описание должно быть не длиннее 1500 символов"

    return None


def validateStepDescription(stepDescription):
    if not isinstance(stepDescription, str) or not stepDescription.strip():
        return "Введите описание этапа"

    if len(stepDescription.strip()) < 3:
        return "Описание этапа должно быть не короче 3 символов"

    if len(stepDescription.strip()) > 1000:
        return "Описание этапа должно быть не длиннее 1000 символов"

    return None


def validateProjectDeadline(deadlineDate):
    # Пустая дата означает «Без дедлайна». Прошедшие даты допустимы.
    if not deadlineDate:
        return None
    error = "Введите дедлайн в формате ДД.ММ.ГГГГ (например: 25.04.2026)"
    if not re.fullmatch(r"[0-9]{2}\.[0-9]{2}\.[0-9]{4}", deadlineDate):
        return error
    try:
        datetime.strptime(deadlineDate, "%d.%m.%Y")
    except ValueError:
        return "Такой даты не существует. Проверьте день, месяц и год"
    return None


def normalizeProjectData(projectName, categoryName, deadlineDate, descriptionText):
    projectName = (projectName or '').strip()
    descriptionText = (descriptionText or '').strip()
    deadlineDate = (deadlineDate or '').strip()
    for error in (validateProjectName(projectName), validateProjectDescription(descriptionText),
                  validateProjectDeadline(deadlineDate)):
        if error:
            raise ValueError(error)
    if categoryName not in PROJECT_CATEGORIES:
        raise ValueError('Выберите категорию проекта из списка')
    return projectName, categoryName, deadlineDate, descriptionText


def saveProject(userId, projectName, categoryName, deadlineDate, descriptionText, stepDescriptions=None):
    try:
        projectName, categoryName, deadlineDate, descriptionText = normalizeProjectData(
            projectName, categoryName, deadlineDate, descriptionText)
    except ValueError as error:
        return False, str(error), None

    if stepDescriptions is not None:
        if not isinstance(stepDescriptions, list) or len(stepDescriptions) > 100:
            return False, "Допускается не больше 100 этапов", None
        normalizedSteps = []
        for description in stepDescriptions:
            error = validateStepDescription(description)
            if error:
                return False, error, None
            normalizedSteps.append(description.strip())
        projectId = createProjectWithSteps(userId, projectName, categoryName, deadlineDate, descriptionText, normalizedSteps)
        return True, "Проект с этапами сохранён", projectId

    projectId = createProject(
        userId,
        projectName,
        categoryName,
        deadlineDate,
        descriptionText,
    )

    return True, "Проект сохранён", projectId


def getProjectSteps(projectId, userId):
    stepRecords = getProjectStepsByProjectId(projectId, userId)

    stepItems = []

    for stepRecord in stepRecords:
        stepItems.append(
            {
                "stepId": stepRecord["stepId"],
                "projectId": stepRecord["projectId"],
                "stepDescription": stepRecord["stepDescription"],
                "isCompleted": bool(stepRecord["isCompleted"]),
                "hasPhoto": bool(stepRecord['hasPhoto']),
                "createdAt": stepRecord["createdAt"],
            }
        )

    return stepItems


def saveProjectStepOrder(projectId, userId, orderedIds, expectedIds):
    for ids in (orderedIds, expectedIds):
        if not isinstance(ids, (list, tuple)) or any(type(value) is not int for value in ids):
            return False, 'Некорректный список этапов'
    try:
        success = reorderProjectSteps(projectId, userId, orderedIds, expectedIds)
    except ValueError as error:
        return False, str(error)
    return success, 'Порядок этапов сохранён' if success else 'Проект не найден или недоступен'


def calculateProjectProgress(projectId, userId):
    if getProjectById(projectId, userId) is None:
        return None
    stepItems = getProjectSteps(projectId, userId)

    if len(stepItems) == 0:
        return 0

    completedCount = 0

    for stepItem in stepItems:
        if stepItem["isCompleted"]:
            completedCount += 1

    return round(completedCount / len(stepItems) * 100, 1)


def refreshProjectProgress(projectId, userId):
    progressPercent = calculateProjectProgress(projectId, userId)
    if progressPercent is None:
        return None
    if not updateProjectProgress(projectId, progressPercent, userId):
        return None

    return progressPercent


def getUserProjects(userId):
    projectRecords = getProjectsByUserId(userId)

    projectItems = []

    for projectRecord in projectRecords:
        projectId = projectRecord["projectId"]
        progressPercent = refreshProjectProgress(projectId, userId)
        if progressPercent is None:
            continue  # Проект мог быть удалён после получения списка.
        stepItems = getProjectSteps(projectId, userId)

        projectItems.append(
            {
                "projectId": projectId,
                "projectName": projectRecord["projectName"],
                "categoryName": projectRecord["categoryName"],
                "deadlineDate": projectRecord["deadlineDate"],
                "descriptionText": projectRecord["descriptionText"],
                "progressPercent": progressPercent,
                "stepItems": stepItems,
                "createdAt": projectRecord["createdAt"],
            }
        )

    return projectItems


def removeProject(projectId, userId):
    return deleteProjectById(projectId, userId)


def saveProjectStep(projectId, stepDescription, userId):
    stepDescription = (stepDescription or "").strip()

    stepDescriptionError = validateStepDescription(stepDescription)
    if stepDescriptionError:
        return False, stepDescriptionError, None

    stepId = createProjectStep(projectId, stepDescription, userId)
    if stepId is None:
        return False, "Проект не найден или недоступен", None
    refreshProjectProgress(projectId, userId)

    return True, "Этап добавлен", stepId


def changeProjectStepStatus(projectId, stepId, isCompleted, userId):
    step = next((item for item in getProjectSteps(projectId, userId) if item['stepId'] == stepId), None)
    if step and isCompleted is True and not step['hasPhoto'] and not step['isCompleted']:
        raise ValueError('Перед завершением этапа добавьте фото результата')
    if not updateProjectStepStatus(projectId, stepId, isCompleted, userId):
        return None
    progressPercent = refreshProjectProgress(projectId, userId)

    return progressPercent


def saveProjectStepPhoto(projectId, stepId, userId, photo):
    if not isinstance(photo, dict):
        return False, 'Выберите фотографию'
    try:
        data = preparePhoto(photo.get('name'), photo.get('data'))['data']
    except ValueError as error:
        return False, str(error)
    if not setProjectStepPhoto(projectId, stepId, userId, data):
        return False, 'Этап не найден или недоступен'
    return True, 'Фото этапа сохранено'


def removeProjectStepPhoto(projectId, stepId, userId):
    if not setProjectStepPhoto(projectId, stepId, userId, None):
        return False, 'Этап недоступен или уже завершён. Сначала снимите отметку выполнения'
    return True, 'Фото этапа удалено'


def removeProjectStep(projectId, stepId, userId):
    if not deleteProjectStepById(projectId, stepId, userId):
        return None
    progressPercent = refreshProjectProgress(projectId, userId)

    return progressPercent



def editProject(projectId, userId, projectName, categoryName, deadlineDate, descriptionText):
    try:
        values = normalizeProjectData(projectName, categoryName, deadlineDate, descriptionText)
    except ValueError as error:
        return False, str(error)
    if not updateProjectById(projectId, userId, *values):
        return False, 'Проект не найден или недоступен'
    return True, 'Проект изменён'


def editProjectStep(projectId, stepId, userId, description):
    error = validateStepDescription(description)
    if error:
        return False, error
    if not updateProjectStepDescription(projectId, stepId, userId, description.strip()):
        return False, 'Этап не найден или недоступен'
    return True, 'Этап изменён'
