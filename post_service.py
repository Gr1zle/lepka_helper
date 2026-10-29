from database import (
    togglePostLikeForUser,
    createPostWithPhotos, getPostPhotoIds, updatePostComment,
    createPostComment,
    deletePostById,
    deletePostCommentById,
    getAllPosts,
    getCommentsByPostId,
    getPostLikeByUser,
    getPostsByUserId,
)
from photo_service import preparePhoto

POST_CATEGORIES = [
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


def validatePostTitle(titleText):
    if not titleText:
        return "Введите название работы"

    if len(titleText) < 3:
        return "Название работы должно быть не короче 3 символов"

    if len(titleText) > 100:
        return "Название работы должно быть не длиннее 100 символов"

    return None


def validatePostDescription(descriptionText):
    if not descriptionText:
        return "Введите описание работы"

    if len(descriptionText) < 10:
        return "Описание должно быть не короче 10 символов"

    if len(descriptionText) > 2000:
        return "Описание должно быть не длиннее 2000 символов"

    return None


def normalizeTags(tagsText):
    if not tagsText:
        return ""

    if not isinstance(tagsText, str):
        raise ValueError('Введите теги через запятую')
    tagItems = []

    for tagText in tagsText.split(","):
        cleanTag = tagText.strip()

        if cleanTag:
            if not 2 <= len(cleanTag) <= 30:
                raise ValueError('Каждый тег должен содержать от 2 до 30 символов')
            tagItems.append(cleanTag)

    if len(tagItems) > 10:
        raise ValueError('Допускается не больше 10 тегов')

    return ", ".join(tagItems)


def savePost(userId, titleText, descriptionText, categoryName, tagsText, photoFiles=None,
             projectDetailsJson='', existingConnection=None):
    if not isinstance(titleText, str) or not isinstance(descriptionText, str):
        return False, 'Введите название и описание работы', None
    titleText = titleText.strip()
    descriptionText = descriptionText.strip()
    try:
        tagsText = normalizeTags(tagsText)
    except ValueError as error:
        return False, str(error), None

    titleError = validatePostTitle(titleText)
    if titleError:
        return False, titleError, None

    descriptionError = validatePostDescription(descriptionText)
    if descriptionError:
        return False, descriptionError, None

    if categoryName not in POST_CATEGORIES:
        return False, "Выберите категорию из списка", None

    if not isinstance(photoFiles, list) or not 1 <= len(photoFiles) <= 10:
        return False, 'Добавьте от 1 до 10 фотографий', None
    try:
        photos = []
        for photo in photoFiles:
            if not isinstance(photo, dict):
                raise ValueError('Некорректная фотография')
            photos.append(preparePhoto(photo.get('name'), photo.get('data'))['data'])
    except ValueError as error:
        return False, str(error), None

    if projectDetailsJson:
        import json
        from project_sharing import readPublishedProject
        details = readPublishedProject(projectDetailsJson)
        if details is None or any(step['photoPosition'] is not None and step['photoPosition'] >= len(photos)
                                  for step in details['steps']):
            return False, 'Проверьте данные мастер-класса и фотографии шагов', None
        if 'workshopInfo' in details:
            details['formatVersion'] = 2
        projectDetailsJson = json.dumps(details, ensure_ascii=False)

    postId = createPostWithPhotos(
        userId,
        titleText,
        descriptionText,
        categoryName,
        tagsText,
        photos,
        projectDetailsJson, existingConnection=existingConnection,
    )
    if postId is None:
        return False, 'Аккаунт недоступен', None
    return True, "Работа опубликована", postId


def getCommunityPosts():
    postRecords = getAllPosts()
    postItems = []

    for postRecord in postRecords:
        postItems.append(
            {
                "postId": postRecord["postId"],
                "userId": postRecord["userId"],
                "titleText": postRecord["titleText"],
                "descriptionText": postRecord["descriptionText"],
                "categoryName": postRecord["categoryName"],
                "tagsText": postRecord["tagsText"] or "",
                "likesCount": postRecord["likesCount"],
                "isDeleted": bool(postRecord["isDeleted"]),
                "createdAt": postRecord["createdAt"],
                "nickname": postRecord["nickname"],
                "photoIds": getPostPhotoIds(postRecord['postId']),
            }
        )

    return postItems


def getUserPosts(userId):
    postRecords = getPostsByUserId(userId)
    postItems = []

    for postRecord in postRecords:
        postItems.append(
            {
                "postId": postRecord["postId"],
                "userId": postRecord["userId"],
                "titleText": postRecord["titleText"],
                "descriptionText": postRecord["descriptionText"],
                "categoryName": postRecord["categoryName"],
                "tagsText": postRecord["tagsText"] or "",
                "likesCount": postRecord["likesCount"],
                "isDeleted": bool(postRecord["isDeleted"]),
                "createdAt": postRecord["createdAt"],
                "nickname": postRecord['nickname'],
                "photoIds": getPostPhotoIds(postRecord['postId']),
            }
        )

    return postItems


def togglePostLike(postId, userId):
    return togglePostLikeForUser(postId, userId)


def removePost(postId, userId):
    return deletePostById(postId, userId)

def validateCommentText(commentText):
    if not commentText:
        return "Введите комментарий"

    cleanCommentText = (commentText or "").strip()

    if len(cleanCommentText) < 5:
        return "Комментарий должен быть не короче 5 символов"

    if len(cleanCommentText) > 1000:
        return "Комментарий должен быть не длиннее 1000 символов"

    if not any(character.isalnum() for character in cleanCommentText):
        return 'Добавьте текст: комментарий не может состоять только из эмодзи или символов'

    return None


def savePostComment(postId, userId, commentText):
    if not isinstance(commentText, str):
        return False, 'Введите текст комментария', None
    cleanCommentText = (commentText or "").strip()

    commentError = validateCommentText(cleanCommentText)

    if commentError:
        return False, commentError, None

    try:
        commentId = createPostComment(postId, userId, cleanCommentText)
    except ValueError as error:
        return False, str(error), None

    if commentId is None:
        return False, "Публикация или аккаунт недоступны", None
    return True, "Комментарий добавлен", commentId


def getPostComments(postId):
    commentRecords = getCommentsByPostId(postId)
    commentItems = []

    for commentRecord in commentRecords:
        commentItems.append(
            {
                "commentId": commentRecord["commentId"],
                "postId": commentRecord["postId"],
                "userId": commentRecord["userId"],
                "commentText": commentRecord["commentText"],
                "createdAt": commentRecord["createdAt"],
                "nickname": commentRecord["nickname"],
            }
        )

    return commentItems


def removePostComment(commentId, userId):
    return deletePostCommentById(commentId, userId)


def editPostComment(commentId, userId, commentText):
    if not isinstance(commentText, str):
        return False, 'Введите текст комментария'
    error = validateCommentText(commentText)
    if error:
        return False, error
    if not updatePostComment(commentId, userId, commentText.strip()):
        return False, 'Комментарий недоступен или истекли 30 минут для редактирования'
    return True, 'Комментарий изменён'

def checkPostLikedByUser(postId, userId):
    if userId is None:
        return False

    existingLike = getPostLikeByUser(postId, userId)

    return existingLike is not None
