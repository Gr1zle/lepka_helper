from database import (
    createProject,
    createProjectStep,
    deleteProjectById,
    deleteProjectStepById,
    getProjectStepsByProjectId,
    getProjectsByUserId,
    updateProjectProgress,
    updateProjectStepStatus,
)


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


def saveProject(userId, projectName, categoryName, deadlineDate, descriptionText):
    projectName = projectName.strip()
    descriptionText = descriptionText.strip()

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


def getProjectSteps(projectId):
    stepRecords = getProjectStepsByProjectId(projectId)

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


def calculateProjectProgress(projectId):
    stepItems = getProjectSteps(projectId)

    if len(stepItems) == 0:
        return 0

    completedCount = 0

    for stepItem in stepItems:
        if stepItem["isCompleted"]:
            completedCount += 1

    return round(completedCount / len(stepItems) * 100, 1)


def refreshProjectProgress(projectId):
    progressPercent = calculateProjectProgress(projectId)
    updateProjectProgress(projectId, progressPercent)

    return progressPercent


def getUserProjects(userId):
    projectRecords = getProjectsByUserId(userId)

    projectItems = []

    for projectRecord in projectRecords:
        projectId = projectRecord["projectId"]
        progressPercent = refreshProjectProgress(projectId)
        stepItems = getProjectSteps(projectId)

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
    deleteProjectById(projectId, userId)


def saveProjectStep(projectId, stepDescription):
    stepDescription = stepDescription.strip()

    stepDescriptionError = validateStepDescription(stepDescription)
    if stepDescriptionError:
        return False, stepDescriptionError, None

    stepId = createProjectStep(projectId, stepDescription)
    refreshProjectProgress(projectId)

    return True, "Этап добавлен", stepId


def changeProjectStepStatus(projectId, stepId, isCompleted):
    updateProjectStepStatus(stepId, isCompleted)
    progressPercent = refreshProjectProgress(projectId)

    return progressPercent


def removeProjectStep(projectId, stepId):
    deleteProjectStepById(stepId)
    progressPercent = refreshProjectProgress(projectId)

    return progressPercent

