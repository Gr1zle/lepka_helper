import sqlite3
from app_paths import DATA_DIRECTORY


DATABASE_PATH = DATA_DIRECTORY / "lepka_helper.db"


def getConnection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def addColumnIfNotExists(cursor, tableName, columnName, columnSql):
    cursor.execute(f"PRAGMA table_info({tableName})")
    columnRecords = cursor.fetchall()

    existingColumnNames = []

    for columnRecord in columnRecords:
        existingColumnNames.append(columnRecord["name"])

    if columnName not in existingColumnNames:
        cursor.execute(
            f"""
            ALTER TABLE {tableName}
            ADD COLUMN {columnSql}
            """
        )


def initializeDatabase():
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            userId INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            passwordHash TEXT NOT NULL,
            passwordSalt TEXT NOT NULL,
            nickname TEXT NOT NULL UNIQUE,
            roleName TEXT NOT NULL DEFAULT 'user',
            isBlocked INTEGER NOT NULL DEFAULT 0,
            createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    addColumnIfNotExists(
        cursor,
        "users",
        "bioText",
        "bioText TEXT DEFAULT ''",
    )

    addColumnIfNotExists(
        cursor,
        "users",
        "ageCategory",
        "ageCategory TEXT DEFAULT 'Взрослый 18+'",
    )

    addColumnIfNotExists(
        cursor,
        "users",
        "favoriteColorsJson",
        "favoriteColorsJson TEXT DEFAULT '[]'",
    )

    addColumnIfNotExists(
        cursor,
        "users",
        "themeMode",
        "themeMode TEXT DEFAULT 'light'",
    )

    addColumnIfNotExists(
        cursor,
        "users",
        "languageCode",
        "languageCode TEXT DEFAULT 'ru'",
    )

    addColumnIfNotExists(
        cursor,
        "users",
        "notificationsEnabled",
        "notificationsEnabled INTEGER DEFAULT 1",
    )

    addColumnIfNotExists(
        cursor,
        "users",
        "avatarPath",
        "avatarPath TEXT DEFAULT ''",
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS colorMixtures (
            mixtureId INTEGER PRIMARY KEY AUTOINCREMENT,
            userId INTEGER NOT NULL,
            mixtureName TEXT NOT NULL,
            resultHex TEXT NOT NULL,
            totalWeight REAL NOT NULL,
            recipeJson TEXT NOT NULL,
            createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (userId) REFERENCES users(userId)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            projectId INTEGER PRIMARY KEY AUTOINCREMENT,
            userId INTEGER NOT NULL,
            projectName TEXT NOT NULL,
            categoryName TEXT NOT NULL,
            deadlineDate TEXT,
            descriptionText TEXT,
            progressPercent REAL NOT NULL DEFAULT 0,
            createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (userId) REFERENCES users(userId)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS projectSteps (
            stepId INTEGER PRIMARY KEY AUTOINCREMENT,
            projectId INTEGER NOT NULL,
            stepDescription TEXT NOT NULL,
            isCompleted INTEGER NOT NULL DEFAULT 0,
            createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (projectId) REFERENCES projects(projectId)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            postId INTEGER PRIMARY KEY AUTOINCREMENT,
            userId INTEGER NOT NULL,
            titleText TEXT NOT NULL,
            descriptionText TEXT NOT NULL,
            categoryName TEXT NOT NULL,
            tagsText TEXT,
            likesCount INTEGER NOT NULL DEFAULT 0,
            createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (userId) REFERENCES users(userId)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS postComments (
            commentId INTEGER PRIMARY KEY AUTOINCREMENT,
            postId INTEGER NOT NULL,
            userId INTEGER NOT NULL,
            commentText TEXT NOT NULL,
            createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (postId) REFERENCES posts(postId),
            FOREIGN KEY (userId) REFERENCES users(userId)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS postLikes (
            likeId INTEGER PRIMARY KEY AUTOINCREMENT,
            postId INTEGER NOT NULL,
            userId INTEGER NOT NULL,
            createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (postId) REFERENCES posts(postId),
            FOREIGN KEY (userId) REFERENCES users(userId),
            UNIQUE(postId, userId)
        )
        """
    )

    connection.commit()
    connection.close()


def getUserByEmail(email):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT userId, email, passwordHash, passwordSalt, nickname, roleName, isBlocked
        FROM users
        WHERE email = ?
        """,
        (email,),
    )

    userRecord = cursor.fetchone()
    connection.close()

    return userRecord


def getUserByNickname(nickname):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT userId, email, nickname
        FROM users
        WHERE nickname = ?
        """,
        (nickname,),
    )

    userRecord = cursor.fetchone()
    connection.close()

    return userRecord


def createUser(email, passwordHash, passwordSalt, nickname):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO users (email, passwordHash, passwordSalt, nickname)
        VALUES (?, ?, ?, ?)
        """,
        (email, passwordHash, passwordSalt, nickname),
    )

    userId = cursor.lastrowid

    connection.commit()
    connection.close()

    return userId


def createColorMixture(userId, mixtureName, resultHex, totalWeight, recipeJson):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO colorMixtures (userId, mixtureName, resultHex, totalWeight, recipeJson)
        VALUES (?, ?, ?, ?, ?)
        """,
        (userId, mixtureName, resultHex, totalWeight, recipeJson),
    )

    mixtureId = cursor.lastrowid

    connection.commit()
    connection.close()

    return mixtureId

def deleteColorMixtureById(userId, mixtureId):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        DELETE FROM colorMixtures
        WHERE userId = ? AND mixtureId = ?
        """,
        (userId, mixtureId),
    )

    connection.commit()
    deletedCount = cursor.rowcount
    connection.close()

    return deletedCount > 0


def getColorMixturesByUserId(userId):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT mixtureId, mixtureName, resultHex, totalWeight, recipeJson, createdAt
        FROM colorMixtures
        WHERE userId = ?
        ORDER BY createdAt DESC
        """,
        (userId,),
    )

    mixtureRecords = cursor.fetchall()
    connection.close()

    return mixtureRecords

def createProject(userId, projectName, categoryName, deadlineDate, descriptionText):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO projects (
            userId,
            projectName,
            categoryName,
            deadlineDate,
            descriptionText
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            userId,
            projectName,
            categoryName,
            deadlineDate,
            descriptionText,
        ),
    )

    projectId = cursor.lastrowid

    connection.commit()
    connection.close()

    return projectId


def getProjectsByUserId(userId):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            projectId,
            projectName,
            categoryName,
            deadlineDate,
            descriptionText,
            progressPercent,
            createdAt
        FROM projects
        WHERE userId = ?
        ORDER BY createdAt DESC
        """,
        (userId,),
    )

    projectRecords = cursor.fetchall()
    connection.close()

    return projectRecords


def getProjectById(projectId, userId):
    connection = getConnection()
    try:
        return connection.execute(
            "SELECT * FROM projects WHERE projectId = ? AND userId = ?",
            (projectId, userId),
        ).fetchone()
    finally:
        connection.close()


def deleteProjectById(projectId, userId):
    connection = getConnection()
    try:
        # Одна транзакция: либо удаляются и этапы, и проект, либо ничего.
        # Работает и с существующей базой без изменения её схемы.
        with connection:
            connection.execute(
                """DELETE FROM projectSteps
                WHERE projectId IN (
                    SELECT projectId FROM projects
                    WHERE projectId = ? AND userId = ?
                )""",
                (projectId, userId),
            )
            cursor = connection.execute(
                "DELETE FROM projects WHERE projectId = ? AND userId = ?",
                (projectId, userId),
            )
        return cursor.rowcount > 0
    finally:
        connection.close()


def getUserProfileById(userId):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            userId,
            email,
            nickname,
            roleName,
            bioText,
            ageCategory,
            favoriteColorsJson,
            themeMode,
            languageCode,
            notificationsEnabled,
            avatarPath
        FROM users
        WHERE userId = ?
        """,
        (userId,),
    )

    userRecord = cursor.fetchone()
    connection.close()

    return userRecord


def updateUserProfile(userId, nickname, bioText, ageCategory, favoriteColorsJson, avatarPath=None):
    connection = getConnection()
    cursor = connection.cursor()

    if avatarPath is None:
        cursor.execute(
            """
            UPDATE users
            SET
                nickname = ?,
                bioText = ?,
                ageCategory = ?,
                favoriteColorsJson = ?
            WHERE userId = ?
            """,
            (
                nickname,
                bioText,
                ageCategory,
                favoriteColorsJson,
                userId,
            ),
        )
    else:
        cursor.execute(
            """
            UPDATE users
            SET
                nickname = ?,
                bioText = ?,
                ageCategory = ?,
                favoriteColorsJson = ?,
                avatarPath = ?
            WHERE userId = ?
            """,
            (
                nickname,
                bioText,
                ageCategory,
                favoriteColorsJson,
                avatarPath,
                userId,
            ),
        )

    connection.commit()
    connection.close()

def createProjectStep(projectId, stepDescription, userId):
    connection = getConnection()
    try:
        with connection:
            cursor = connection.execute(
                """INSERT INTO projectSteps (projectId, stepDescription)
                SELECT projectId, ? FROM projects
                WHERE projectId = ? AND userId = ?""",
                (stepDescription, projectId, userId),
            )
        return cursor.lastrowid if cursor.rowcount else None
    finally:
        connection.close()


def getProjectStepsByProjectId(projectId, userId):
    connection = getConnection()
    try:
        return connection.execute(
            """SELECT s.stepId, s.projectId, s.stepDescription,
                      s.isCompleted, s.createdAt
            FROM projectSteps AS s
            JOIN projects AS p ON p.projectId = s.projectId
            WHERE p.projectId = ? AND p.userId = ?
            ORDER BY s.createdAt ASC, s.stepId ASC""",
            (projectId, userId),
        ).fetchall()
    finally:
        connection.close()


def updateProjectStepStatus(projectId, stepId, isCompleted, userId):
    connection = getConnection()
    try:
        with connection:
            cursor = connection.execute(
                """UPDATE projectSteps SET isCompleted = ?
                WHERE stepId = ? AND projectId = ?
                AND projectId IN (SELECT projectId FROM projects WHERE userId = ?)""",
                (1 if isCompleted else 0, stepId, projectId, userId),
            )
        return cursor.rowcount > 0
    finally:
        connection.close()


def deleteProjectStepById(projectId, stepId, userId):
    connection = getConnection()
    try:
        with connection:
            cursor = connection.execute(
                """DELETE FROM projectSteps
                WHERE stepId = ? AND projectId = ?
                AND projectId IN (SELECT projectId FROM projects WHERE userId = ?)""",
                (stepId, projectId, userId),
            )
        return cursor.rowcount > 0
    finally:
        connection.close()


def updateProjectProgress(projectId, progressPercent, userId):
    connection = getConnection()
    try:
        with connection:
            cursor = connection.execute(
                """UPDATE projects SET progressPercent = ?
                WHERE projectId = ? AND userId = ?""",
                (progressPercent, projectId, userId),
            )
        return cursor.rowcount > 0
    finally:
        connection.close()


def updateUserSettings(userId, themeMode, languageCode, notificationsEnabled):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE users
        SET
            themeMode = ?,
            languageCode = ?,
            notificationsEnabled = ?
        WHERE userId = ?
        """,
        (
            themeMode,
            languageCode,
            1 if notificationsEnabled else 0,
            userId,
        ),
    )

    connection.commit()
    connection.close()

def createPost(userId, titleText, descriptionText, categoryName, tagsText):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO posts (
            userId,
            titleText,
            descriptionText,
            categoryName,
            tagsText
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            userId,
            titleText,
            descriptionText,
            categoryName,
            tagsText,
        ),
    )

    postId = cursor.lastrowid

    connection.commit()
    connection.close()

    return postId


def getAllPosts():
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            posts.postId,
            posts.userId,
            posts.titleText,
            posts.descriptionText,
            posts.categoryName,
            posts.tagsText,
            posts.likesCount,
            posts.createdAt,
            users.nickname
        FROM posts
        INNER JOIN users ON posts.userId = users.userId
        ORDER BY posts.createdAt DESC
        """
    )

    postRecords = cursor.fetchall()
    connection.close()

    return postRecords


def getPostsByUserId(userId):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            postId,
            userId,
            titleText,
            descriptionText,
            categoryName,
            tagsText,
            likesCount,
            createdAt
        FROM posts
        WHERE userId = ?
        ORDER BY createdAt DESC
        """,
        (userId,),
    )

    postRecords = cursor.fetchall()
    connection.close()

    return postRecords


def increasePostLikes(postId):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE posts
        SET likesCount = likesCount + 1
        WHERE postId = ?
        """,
        (postId,),
    )

    connection.commit()
    connection.close()


def deletePostById(postId, userId):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        DELETE FROM posts
        WHERE postId = ? AND userId = ?
        """,
        (postId, userId),
    )

    connection.commit()
    connection.close()

def createPostComment(postId, userId, commentText):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO postComments (
            postId,
            userId,
            commentText
        )
        VALUES (?, ?, ?)
        """,
        (
            postId,
            userId,
            commentText,
        ),
    )

    commentId = cursor.lastrowid

    connection.commit()
    connection.close()

    return commentId


def getCommentsByPostId(postId):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            postComments.commentId,
            postComments.postId,
            postComments.userId,
            postComments.commentText,
            postComments.createdAt,
            users.nickname
        FROM postComments
        INNER JOIN users ON postComments.userId = users.userId
        WHERE postComments.postId = ?
        ORDER BY postComments.createdAt ASC
        """,
        (postId,),
    )

    commentRecords = cursor.fetchall()
    connection.close()

    return commentRecords


def deletePostCommentById(commentId, userId):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        DELETE FROM postComments
        WHERE commentId = ? AND userId = ?
        """,
        (
            commentId,
            userId,
        ),
    )

    connection.commit()
    connection.close()

def getPostLikeByUser(postId, userId):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT likeId, postId, userId
        FROM postLikes
        WHERE postId = ? AND userId = ?
        """,
        (postId, userId),
    )

    likeRecord = cursor.fetchone()
    connection.close()

    return likeRecord


def createPostLike(postId, userId):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO postLikes (postId, userId)
        VALUES (?, ?)
        """,
        (postId, userId),
    )

    connection.commit()
    connection.close()


def deletePostLike(postId, userId):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        DELETE FROM postLikes
        WHERE postId = ? AND userId = ?
        """,
        (postId, userId),
    )

    connection.commit()
    connection.close()


def countPostLikes(postId):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT COUNT(*) AS likesCount
        FROM postLikes
        WHERE postId = ?
        """,
        (postId,),
    )

    countRecord = cursor.fetchone()
    connection.close()

    return countRecord["likesCount"]


def updatePostLikesCount(postId, likesCount):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE posts
        SET likesCount = ?
        WHERE postId = ?
        """,
        (likesCount, postId),
    )

    connection.commit()
    connection.close()

def deleteUserDataById(userId):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        DELETE FROM postComments
        WHERE userId = ?
        """,
        (userId,),
    )

    cursor.execute(
        """
        DELETE FROM postComments
        WHERE postId IN (
            SELECT postId FROM posts WHERE userId = ?
        )
        """,
        (userId,),
    )

    cursor.execute(
        """
        DELETE FROM postLikes
        WHERE userId = ?
        """,
        (userId,),
    )

    cursor.execute(
        """
        DELETE FROM postLikes
        WHERE postId IN (
            SELECT postId FROM posts WHERE userId = ?
        )
        """,
        (userId,),
    )

    cursor.execute(
        """
        DELETE FROM posts
        WHERE userId = ?
        """,
        (userId,),
    )

    cursor.execute(
        """
        DELETE FROM projectSteps
        WHERE projectId IN (
            SELECT projectId FROM projects WHERE userId = ?
        )
        """,
        (userId,),
    )

    cursor.execute(
        """
        DELETE FROM projects
        WHERE userId = ?
        """,
        (userId,),
    )

    cursor.execute(
        """
        DELETE FROM colorMixtures
        WHERE userId = ?
        """,
        (userId,),
    )

    cursor.execute(
        """
        DELETE FROM users
        WHERE userId = ?
        """,
        (userId,),
    )

    connection.commit()
    connection.close()

def getUserPasswordById(userId):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT userId, passwordHash, passwordSalt
        FROM users
        WHERE userId = ?
        """,
        (userId,),
    )

    userRecord = cursor.fetchone()
    connection.close()

    return userRecord


def updateUserPassword(userId, passwordHash, passwordSalt):
    connection = getConnection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE users
        SET passwordHash = ?, passwordSalt = ?
        WHERE userId = ?
        """,
        (passwordHash, passwordSalt, userId),
    )

    connection.commit()
    connection.close()
