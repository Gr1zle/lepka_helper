import re
from datetime import datetime

from database import (
    createProject,
    getProjectById,
    createProjectStep,
    deleteProjectById,
    deleteProjectStepById,
    getProjectStepsByProjectId,
    getProjectsByUserId,
    updateProjectProgress,
    updateProjectStepStatus,
)


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
    if not stepDescription:
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


def saveProject(userId, projectName, categoryName, deadlineDate, descriptionText):
    projectName = projectName.strip()
    descriptionText = (descriptionText or "").strip()
    deadlineDate = (deadlineDate or "").strip()

    deadlineError = validateProjectDeadline(deadlineDate)
    if deadlineError:
        return False, deadlineError, None

    projectNameError = validateProjectName(projectName)
    if projectNameError:
        return False, projectNameError, None

    descriptionError = validateProjectDescription(descriptionText)
    if descriptionError:
        return False, descriptionError, None

    if not categoryName:
        return False, "Выберите категорию проекта", None

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
                "createdAt": stepRecord["createdAt"],
            }
        )

    return stepItems


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
    if not updateProjectStepStatus(projectId, stepId, isCompleted, userId):
        return None
    progressPercent = refreshProjectProgress(projectId, userId)

    return progressPercent


def removeProjectStep(projectId, stepId, userId):
    if not deleteProjectStepById(projectId, stepId, userId):
        return None
    progressPercent = refreshProjectProgress(projectId, userId)

    return progressPercent

