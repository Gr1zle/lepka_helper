from database import (
    countPostLikes,
    createPost,
    createPostComment,
    createPostLike,
    deletePostById,
    deletePostCommentById,
    deletePostLike,
    getAllPosts,
    getCommentsByPostId,
    getPostLikeByUser,
    getPostsByUserId,
    updatePostLikesCount,
)

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

    tagItems = []

    for tagText in tagsText.split(","):
        cleanTag = tagText.strip()

        if cleanTag:
            tagItems.append(cleanTag)

    if len(tagItems) > 10:
        tagItems = tagItems[:10]

    return ", ".join(tagItems)


def savePost(userId, titleText, descriptionText, categoryName, tagsText):
    titleText = titleText.strip()
    descriptionText = descriptionText.strip()
    tagsText = normalizeTags(tagsText)

    titleError = validatePostTitle(titleText)
    if titleError:
        return False, titleError, None

    descriptionError = validatePostDescription(descriptionText)
    if descriptionError:
        return False, descriptionError, None

    if not categoryName:
        return False, "Выберите категорию", None

    postId = createPost(
        userId,
        titleText,
        descriptionText,
        categoryName,
        tagsText,
    )

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
                "createdAt": postRecord["createdAt"],
                "nickname": postRecord["nickname"],
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
                "createdAt": postRecord["createdAt"],
            }
        )

    return postItems


def togglePostLike(postId, userId):
    existingLike = getPostLikeByUser(postId, userId)

    if existingLike:
        deletePostLike(postId, userId)
        isLiked = False
    else:
        createPostLike(postId, userId)
        isLiked = True

    likesCount = countPostLikes(postId)
    updatePostLikesCount(postId, likesCount)

    return isLiked, likesCount


def removePost(postId, userId):
    deletePostById(postId, userId)

def validateCommentText(commentText):
    if not commentText:
        return "Введите комментарий"

    cleanCommentText = commentText.strip()

    if len(cleanCommentText) < 5:
        return "Комментарий должен быть не короче 5 символов"

    if len(cleanCommentText) > 1000:
        return "Комментарий должен быть не длиннее 1000 символов"

    return None


def savePostComment(postId, userId, commentText):
    cleanCommentText = commentText.strip()

    commentError = validateCommentText(cleanCommentText)

    if commentError:
        return False, commentError, None

    commentId = createPostComment(
        postId,
        userId,
        cleanCommentText,
    )

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
    deletePostCommentById(commentId, userId)

def checkPostLikedByUser(postId, userId):
    if userId is None:
        return False

    existingLike = getPostLikeByUser(postId, userId)

    return existingLike is not None