import sqlite3
import uuid
from contextlib import contextmanager, nullcontext
from app_paths import DATA_DIRECTORY


DATABASE_PATH = DATA_DIRECTORY / "lepka_helper.db"


def getConnection():
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection

@contextmanager
def openDatabase():
    """Транзакция с откатом при исключении и обязательным закрытием соединения."""
    connection = getConnection()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


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

    # Старые аккаунты сохраняют доступ. Новые требуют подтверждения почты.
    for columnName, columnSql in (
        ('emailVerified', 'emailVerified INTEGER NOT NULL DEFAULT 1'),
        ('loginFailures', 'loginFailures INTEGER NOT NULL DEFAULT 0'),
        ('loginBlockedUntil', 'loginBlockedUntil REAL NOT NULL DEFAULT 0'),
        ('passwordFailures', 'passwordFailures INTEGER NOT NULL DEFAULT 0'),
        ('passwordBlockedUntil', 'passwordBlockedUntil REAL NOT NULL DEFAULT 0'),
    ):
        addColumnIfNotExists(cursor, 'users', columnName, columnSql)

    cursor.execute("""CREATE TABLE IF NOT EXISTS accountCodes (
        email TEXT NOT NULL, purpose TEXT NOT NULL, userId INTEGER NOT NULL,
        codeHash TEXT NOT NULL, expiresAt REAL NOT NULL, sentAt REAL NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (email, purpose), FOREIGN KEY (userId) REFERENCES users(userId)
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS accountSessions (
        tokenHash TEXT PRIMARY KEY, userId INTEGER NOT NULL, expiresAt REAL NOT NULL,
        FOREIGN KEY (userId) REFERENCES users(userId)
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS accountEvents (
        eventId INTEGER PRIMARY KEY AUTOINCREMENT, userId INTEGER NOT NULL,
        eventName TEXT NOT NULL, createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS remoteAccounts (
        apiUrl TEXT NOT NULL, remoteUserId INTEGER NOT NULL, localUserId INTEGER NOT NULL UNIQUE,
        displayNickname TEXT NOT NULL, PRIMARY KEY (apiUrl, remoteUserId),
        FOREIGN KEY (localUserId) REFERENCES users(userId)
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS remoteSessionBindings (
        tokenHash TEXT PRIMARY KEY, apiUrl TEXT NOT NULL, localUserId INTEGER NOT NULL,
        FOREIGN KEY (localUserId) REFERENCES users(userId)
    )""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS communityCache (
        userId INTEGER NOT NULL,apiUrl TEXT NOT NULL,cacheKey TEXT NOT NULL,contentJson TEXT NOT NULL,updatedAt REAL NOT NULL,
        PRIMARY KEY(userId,apiUrl,cacheKey),FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS publicationDrafts (
        draftId TEXT PRIMARY KEY,userId INTEGER NOT NULL,apiUrl TEXT NOT NULL,payloadJson TEXT NOT NULL,updatedAt REAL NOT NULL,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS communityOutbox (
        requestId TEXT PRIMARY KEY,userId INTEGER NOT NULL,apiUrl TEXT NOT NULL,serverUserId INTEGER NOT NULL,
        kind TEXT NOT NULL,payloadJson TEXT NOT NULL,payloadHash TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
        nextAttemptAt REAL NOT NULL DEFAULT 0,leaseUntil REAL NOT NULL DEFAULT 0,leaseToken TEXT NOT NULL DEFAULT '',
        lastError TEXT NOT NULL DEFAULT '',resultJson TEXT,createdAt REAL NOT NULL,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS communityActionReceipts (
        userId INTEGER NOT NULL,requestId TEXT NOT NULL,kind TEXT NOT NULL,payloadHash TEXT NOT NULL,resultJson TEXT NOT NULL,
        PRIMARY KEY(userId,requestId),FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS remoteProfileCache (
        userId INTEGER NOT NULL,apiUrl TEXT NOT NULL,profileJson TEXT NOT NULL,
        PRIMARY KEY(userId,apiUrl),FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS lessonProgress (
        userId INTEGER NOT NULL, lessonId INTEGER NOT NULL, stateJson TEXT NOT NULL,
        updatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (userId, lessonId), FOREIGN KEY (userId) REFERENCES users(userId)
    )""")
    cursor.execute('''CREATE TABLE IF NOT EXISTS lessonFavorites (
        userId INTEGER NOT NULL, lessonId INTEGER NOT NULL,
        savedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(userId,lessonId), FOREIGN KEY(userId) REFERENCES users(userId))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS lessonNotes (
        userId INTEGER NOT NULL, lessonId INTEGER NOT NULL, noteText TEXT NOT NULL,
        updatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(userId,lessonId), FOREIGN KEY(userId) REFERENCES users(userId))''')
    cursor.execute("""CREATE TABLE IF NOT EXISTS personalNoticeSettings (
        userId INTEGER PRIMARY KEY, projectsEnabled INTEGER NOT NULL DEFAULT 1,
        lessonsEnabled INTEGER NOT NULL DEFAULT 1, resumeDays INTEGER NOT NULL DEFAULT 3,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS learningNotices (
        noticeId INTEGER PRIMARY KEY AUTOINCREMENT,userId INTEGER NOT NULL,lessonId INTEGER NOT NULL,
        kind TEXT NOT NULL,eventKey TEXT NOT NULL,createdAt TEXT NOT NULL,isRead INTEGER NOT NULL DEFAULT 0,
        snoozedUntil TEXT,UNIQUE(userId,eventKey),
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE)""")
    cursor.execute('''CREATE TABLE IF NOT EXISTS modelFavorites (
        userId INTEGER NOT NULL, modelId TEXT NOT NULL,
        PRIMARY KEY(userId,modelId), FOREIGN KEY(userId) REFERENCES users(userId))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS importedModels (
        modelId TEXT PRIMARY KEY, userId INTEGER NOT NULL, title TEXT NOT NULL,
        objText TEXT NOT NULL, materialText TEXT NOT NULL, previewImage BLOB NOT NULL,
        createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS searchHistory (
        userId INTEGER NOT NULL, queryKey TEXT NOT NULL, queryText TEXT NOT NULL,
        lastUsed INTEGER NOT NULL, PRIMARY KEY(userId,queryKey),
        FOREIGN KEY(userId) REFERENCES users(userId))''')

    cursor.execute("""CREATE TABLE IF NOT EXISTS personalVault (
        userId INTEGER PRIMARY KEY,revision INTEGER NOT NULL,checksum TEXT NOT NULL,
        snapshotJson TEXT NOT NULL,deviceId TEXT NOT NULL,updatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS personalVaultHistory (
        userId INTEGER NOT NULL,revision INTEGER NOT NULL,checksum TEXT NOT NULL,snapshotJson TEXT NOT NULL,
        deviceId TEXT NOT NULL,updatedAt TEXT NOT NULL,PRIMARY KEY(userId,revision),
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS personalSyncState (
        userId INTEGER NOT NULL,apiUrl TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0,
        checksum TEXT NOT NULL DEFAULT '',pending INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(userId,apiUrl),FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS personalCheckpoints (
        checkpointId TEXT PRIMARY KEY,userId INTEGER NOT NULL,title TEXT NOT NULL,content BLOB NOT NULL,
        checksum TEXT NOT NULL,createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE)""")
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
    addColumnIfNotExists(cursor, 'users', 'avatarImage', 'avatarImage BLOB')

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

    addColumnIfNotExists(cursor, 'projectSteps', 'photoImage', 'photoImage BLOB')
    addColumnIfNotExists(cursor, 'projects', 'completedAt', 'completedAt TEXT')
    cursor.execute('''CREATE TABLE IF NOT EXISTS projectReminders (
        reminderId INTEGER PRIMARY KEY AUTOINCREMENT,
        userId INTEGER NOT NULL, projectId INTEGER NOT NULL,
        deadlineDate TEXT NOT NULL, kind TEXT NOT NULL,
        generatedDate TEXT NOT NULL, isRead INTEGER NOT NULL DEFAULT 0,
        UNIQUE(userId,projectId,deadlineDate,kind),
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY(projectId) REFERENCES projects(projectId) ON DELETE CASCADE)''')
    stepColumns = {row['name'] for row in cursor.execute('PRAGMA table_info(projectSteps)')}
    if 'sortOrder' not in stepColumns:
        addColumnIfNotExists(cursor, 'projectSteps', 'sortOrder', 'sortOrder INTEGER NOT NULL DEFAULT 0')
        # Сохраняем прежний порядок при первом обновлении существующей базы.
        records = cursor.execute('SELECT stepId, projectId FROM projectSteps ORDER BY projectId, createdAt, stepId').fetchall()
        positions = {}
        for record in records:
            position = positions.get(record['projectId'], 0)
            cursor.execute('UPDATE projectSteps SET sortOrder = ? WHERE stepId = ?', (position, record['stepId']))
            positions[record['projectId']] = position + 1

    # Копия рецепта: удаление смеси из палитры не меняет материалы проекта.
    cursor.execute("""CREATE TABLE IF NOT EXISTS projectMixtures (
        projectMixtureId INTEGER PRIMARY KEY AUTOINCREMENT, projectId INTEGER NOT NULL,
        mixtureJson TEXT NOT NULL, FOREIGN KEY (projectId) REFERENCES projects(projectId)
    )""")

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

    addColumnIfNotExists(cursor, 'posts', 'isDeleted', 'isDeleted INTEGER NOT NULL DEFAULT 0')
    addColumnIfNotExists(cursor, 'posts', 'projectDetailsJson', "projectDetailsJson TEXT NOT NULL DEFAULT ''")

    cursor.execute("""CREATE TABLE IF NOT EXISTS postPhotos (
        photoId INTEGER PRIMARY KEY AUTOINCREMENT, postId INTEGER NOT NULL,
        position INTEGER NOT NULL, imageData BLOB NOT NULL,
        FOREIGN KEY (postId) REFERENCES posts(postId), UNIQUE(postId, position)
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS workshopProgress (
        userId INTEGER NOT NULL, postId INTEGER NOT NULL, stateJson TEXT NOT NULL,
        PRIMARY KEY (userId, postId),
        FOREIGN KEY (userId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY (postId) REFERENCES posts(postId) ON DELETE CASCADE
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS communityRequests (
        userId INTEGER NOT NULL, requestId TEXT NOT NULL, payloadHash TEXT NOT NULL, postId INTEGER NOT NULL,
        PRIMARY KEY (userId, requestId),
        FOREIGN KEY (userId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY (postId) REFERENCES posts(postId) ON DELETE CASCADE
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS localPostExports (
        apiUrl TEXT NOT NULL, userId INTEGER NOT NULL, localPostId INTEGER NOT NULL,
        requestId TEXT NOT NULL, serverPostId INTEGER,
        PRIMARY KEY (apiUrl, userId, localPostId),
        FOREIGN KEY (userId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY (localPostId) REFERENCES posts(postId) ON DELETE CASCADE
    )""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS commentEvents (
        userId INTEGER NOT NULL, createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (userId) REFERENCES users(userId)
    )""")
    cursor.execute('CREATE INDEX IF NOT EXISTS commentEventsUserTime ON commentEvents(userId, createdAt)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS moderationReports (
        reportId INTEGER PRIMARY KEY AUTOINCREMENT,
        reporterId INTEGER, targetType TEXT NOT NULL, targetId INTEGER NOT NULL,
        reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
        resolution TEXT NOT NULL DEFAULT '', resolvedBy INTEGER,
        createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, resolvedAt TEXT,
        UNIQUE(reporterId,targetType,targetId),
        FOREIGN KEY(reporterId) REFERENCES users(userId) ON DELETE SET NULL,
        FOREIGN KEY(resolvedBy) REFERENCES users(userId) ON DELETE SET NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS customRoles (
        roleCode TEXT PRIMARY KEY,title TEXT NOT NULL,permissionsJson TEXT NOT NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS adminAudit (
        eventId INTEGER PRIMARY KEY AUTOINCREMENT, actorId INTEGER,
        actorNickname TEXT NOT NULL, action TEXT NOT NULL,
        targetType TEXT NOT NULL, targetId INTEGER NOT NULL, reason TEXT NOT NULL,
        createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(actorId) REFERENCES users(userId) ON DELETE SET NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS challenges (
        challengeId INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
        rules TEXT NOT NULL, deadline TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'open',
        createdBy INTEGER, winnerPostId INTEGER, result TEXT NOT NULL DEFAULT '',
        createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(createdBy) REFERENCES users(userId) ON DELETE SET NULL,
        FOREIGN KEY(winnerPostId) REFERENCES posts(postId) ON DELETE SET NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS challengeEntries (
        challengeId INTEGER NOT NULL, userId INTEGER NOT NULL, postId INTEGER NOT NULL,
        createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(challengeId,userId), UNIQUE(challengeId,postId),
        FOREIGN KEY(challengeId) REFERENCES challenges(challengeId) ON DELETE CASCADE,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY(postId) REFERENCES posts(postId) ON DELETE CASCADE)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS challengeOptOuts (
        challengeId INTEGER NOT NULL,userId INTEGER NOT NULL,PRIMARY KEY(challengeId,userId),
        FOREIGN KEY(challengeId) REFERENCES challenges(challengeId) ON DELETE CASCADE,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS challengeVotes (
        challengeId INTEGER NOT NULL, postId INTEGER NOT NULL, userId INTEGER NOT NULL,
        PRIMARY KEY(challengeId,postId,userId),
        FOREIGN KEY(challengeId,postId) REFERENCES challengeEntries(challengeId,postId) ON DELETE CASCADE,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE)''')
    addColumnIfNotExists(cursor, 'challenges', 'startsOn', "startsOn TEXT NOT NULL DEFAULT ''")
    addColumnIfNotExists(cursor, 'challenges', 'theme', "theme TEXT NOT NULL DEFAULT ''")
    addColumnIfNotExists(cursor, 'challenges', 'resultMode', "resultMode TEXT NOT NULL DEFAULT 'manual'")
    cursor.execute('''CREATE TABLE IF NOT EXISTS challengeAwards (
        challengeId INTEGER NOT NULL, place INTEGER NOT NULL, postId INTEGER, userId INTEGER,
        votes INTEGER NOT NULL, PRIMARY KEY(challengeId,place),
        FOREIGN KEY(challengeId) REFERENCES challenges(challengeId) ON DELETE CASCADE,
        FOREIGN KEY(postId) REFERENCES posts(postId) ON DELETE SET NULL,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE SET NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS communityNotices (
        noticeId INTEGER PRIMARY KEY AUTOINCREMENT, userId INTEGER NOT NULL,
        challengeId INTEGER NOT NULL, place INTEGER NOT NULL, isRead INTEGER NOT NULL DEFAULT 0,
        createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(userId,challengeId,place),
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY(challengeId) REFERENCES challenges(challengeId) ON DELETE CASCADE)''')


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

    addColumnIfNotExists(cursor,'postComments','replyToId',
        'replyToId INTEGER REFERENCES postComments(commentId) ON DELETE SET NULL')
    cursor.execute('''CREATE TABLE IF NOT EXISTS activityNotices (
        noticeId INTEGER PRIMARY KEY AUTOINCREMENT, userId INTEGER NOT NULL, actorId INTEGER NOT NULL,
        kind TEXT NOT NULL, postId INTEGER NOT NULL, commentId INTEGER, eventKey TEXT NOT NULL,
        isRead INTEGER NOT NULL DEFAULT 0, createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(userId,eventKey),
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY(actorId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY(postId) REFERENCES posts(postId) ON DELETE CASCADE,
        FOREIGN KEY(commentId) REFERENCES postComments(commentId) ON DELETE CASCADE)''')
    cursor.execute('CREATE INDEX IF NOT EXISTS activityRecipient ON activityNotices(userId,noticeId)')

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
        SELECT *
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


def createUser(email, passwordHash, passwordSalt, nickname, emailVerified=True):
    # Соединение закрывается и при конфликте email/ника — важно для Windows.
    with openDatabase() as connection:
        cursor = connection.execute(
            '''INSERT INTO users (email, passwordHash, passwordSalt, nickname, emailVerified)
            VALUES (?, ?, ?, ?, ?)''', (email, passwordHash, passwordSalt, nickname, int(emailVerified)))
        return cursor.lastrowid


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
            connection.execute('''DELETE FROM projectMixtures WHERE projectId IN
                (SELECT projectId FROM projects WHERE projectId = ? AND userId = ?)''', (projectId, userId))
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
            avatarPath,
            avatarImage
        FROM users
        WHERE userId = ?
        """,
        (userId,),
    )

    userRecord = cursor.fetchone()
    connection.close()

    return userRecord


def updateUserProfile(userId, nickname, bioText, ageCategory, favoriteColorsJson, avatarPath=None):
    with openDatabase() as connection:
        if avatarPath is None:
            connection.execute(
                """UPDATE users SET nickname = ?, bioText = ?, ageCategory = ?, favoriteColorsJson = ?
                WHERE userId = ?""", (nickname, bioText, ageCategory, favoriteColorsJson, userId))
        else:
            connection.execute(
                """UPDATE users SET nickname = ?, bioText = ?, ageCategory = ?, favoriteColorsJson = ?, avatarPath = ?
                WHERE userId = ?""", (nickname, bioText, ageCategory, favoriteColorsJson, avatarPath, userId))


def createProjectStep(projectId, stepDescription, userId):
    connection = getConnection()
    try:
        with connection:
            cursor = connection.execute(
                """INSERT INTO projectSteps (projectId, stepDescription, sortOrder)
                SELECT projectId, ?, COALESCE((SELECT MAX(sortOrder) FROM projectSteps WHERE projectId = ?), -1) + 1 FROM projects
                WHERE projectId = ? AND userId = ?""",
                (stepDescription, projectId, projectId, userId),
            )
        return cursor.lastrowid if cursor.rowcount else None
    finally:
        connection.close()


def reorderProjectSteps(projectId, userId, orderedIds, expectedIds):
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        owned = connection.execute('''SELECT p.projectId FROM projects p JOIN users u ON u.userId = p.userId
            WHERE p.projectId = ? AND p.userId = ? AND u.isBlocked = 0''', (projectId, userId)).fetchone()
        if owned is None:
            return False
        current = [row['stepId'] for row in connection.execute(
            'SELECT stepId FROM projectSteps WHERE projectId = ? ORDER BY sortOrder, stepId', (projectId,))]
        if current != list(expectedIds):
            raise ValueError('Этапы уже изменились. Закройте окно и откройте порядок этапов заново')
        if len(orderedIds) != len(current) or set(orderedIds) != set(current):
            raise ValueError('Нужно передать все этапы проекта без повторений')
        connection.executemany('UPDATE projectSteps SET sortOrder = ? WHERE projectId = ? AND stepId = ?',
                               [(position, projectId, stepId) for position, stepId in enumerate(orderedIds)])
        return True


def getProjectStepsByProjectId(projectId, userId):
    connection = getConnection()
    try:
        return connection.execute(
            """SELECT s.stepId, s.projectId, s.stepDescription,
                      s.isCompleted, s.createdAt, (length(s.photoImage) > 0) AS hasPhoto
            FROM projectSteps AS s
            JOIN projects AS p ON p.projectId = s.projectId
            WHERE p.projectId = ? AND p.userId = ?
            ORDER BY s.sortOrder ASC, s.stepId ASC""",
            (projectId, userId),
        ).fetchall()
    finally:
        connection.close()


def updateProjectStepStatus(projectId, stepId, isCompleted, userId):
    if type(isCompleted) is not bool:
        return False
    connection = getConnection()
    try:
        with connection:
            cursor = connection.execute(
                """UPDATE projectSteps SET isCompleted = ?
                WHERE stepId = ? AND projectId = ?
                AND projectId IN (SELECT projectId FROM projects WHERE userId = ?)
                AND (? = 0 OR length(photoImage) > 0 OR isCompleted = 1)""",
                (1 if isCompleted else 0, stepId, projectId, userId, int(isCompleted)),
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
                """UPDATE projects SET completedAt = CASE
                    WHEN ? < 100 THEN NULL
                    WHEN progressPercent < 100 THEN strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                    ELSE completedAt END, progressPercent = ?
                WHERE projectId = ? AND userId = ?""",
                (progressPercent, progressPercent, projectId, userId),
            )
        return cursor.rowcount > 0
    finally:
        connection.close()


def updateUserSettings(userId, themeMode, languageCode, notificationsEnabled):
    with openDatabase() as connection:
        connection.execute(
            """UPDATE users SET themeMode = ?, languageCode = ?, notificationsEnabled = ? WHERE userId = ?""",
            (themeMode, languageCode, int(notificationsEnabled), userId))


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
            posts.isDeleted,
            posts.createdAt,
            COALESCE(remoteAccounts.displayNickname, users.nickname) AS nickname
        FROM posts
        INNER JOIN users ON posts.userId = users.userId
        LEFT JOIN remoteAccounts ON remoteAccounts.localUserId = users.userId
        ORDER BY posts.createdAt DESC, posts.postId DESC
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
        SELECT posts.*, COALESCE(remoteAccounts.displayNickname, users.nickname) AS nickname
        FROM posts
        JOIN users ON users.userId = posts.userId
        LEFT JOIN remoteAccounts ON remoteAccounts.localUserId = users.userId
        WHERE posts.userId = ?
        ORDER BY posts.createdAt DESC, posts.postId DESC
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
    with openDatabase() as connection:
        ownedPost = connection.execute(
            '''SELECT postId FROM posts WHERE postId = ? AND userId = ?
            AND EXISTS (SELECT 1 FROM users WHERE userId = ? AND isBlocked = 0)''',
            (postId, userId, userId),
        ).fetchone()
        if ownedPost is None:
            return False
        erasePost(connection,postId)
        return True


def erasePost(connection,postId):
    """Внутренняя операция в уже проверенной транзакции владельца/модератора."""
    connection.execute('DELETE FROM postComments WHERE postId = ?', (postId,))
    connection.execute('DELETE FROM postLikes WHERE postId = ?', (postId,))
    connection.execute('DELETE FROM postPhotos WHERE postId = ?', (postId,))
    connection.execute('DELETE FROM posts WHERE postId = ?', (postId,))


def createPostComment(postId, userId, commentText, replyToId=None,existingConnection=None):
    with (nullcontext(existingConnection) if existingConnection is not None else openDatabase()) as connection:
        if not connection.in_transaction:connection.execute('BEGIN IMMEDIATE')
        if replyToId is not None:
            if type(replyToId) is not int or not 1<=replyToId<=9223372036854775807 or not connection.execute(
                'SELECT 1 FROM postComments WHERE commentId=? AND postId=?',(replyToId,postId)).fetchone():
                raise ValueError('Комментарий для ответа уже недоступен')
        recent = connection.execute("""SELECT COUNT(*) FROM commentEvents
            WHERE userId = ? AND createdAt > datetime('now', '-1 minute')""", (userId,)).fetchone()[0]
        if recent >= 5:
            raise ValueError('Можно отправить не больше 5 комментариев в минуту')
        cursor = connection.execute(
            """INSERT INTO postComments (postId, userId, commentText)
            SELECT p.postId, u.userId, ? FROM posts AS p, users AS u
            WHERE p.postId = ? AND p.isDeleted = 0 AND u.userId = ? AND u.isBlocked = 0""",
            (commentText, postId, userId),
        )
        if not cursor.rowcount:
            return None
        commentId = cursor.lastrowid
        connection.execute('UPDATE postComments SET replyToId=? WHERE commentId=?',(replyToId,commentId))
        from activity_service import comment
        comment(connection,postId,userId,commentId,replyToId)
        connection.execute('INSERT INTO commentEvents (userId) VALUES (?)', (userId,))
        connection.execute("DELETE FROM commentEvents WHERE createdAt < datetime('now', '-1 day')")
        return commentId


def togglePostLikeForUser(postId, userId):
    with openDatabase() as connection:
        connection.execute('BEGIN IMMEDIATE')
        available = connection.execute(
            """SELECT p.postId FROM posts AS p, users AS u
            WHERE p.postId = ? AND p.isDeleted = 0 AND u.userId = ? AND u.isBlocked = 0""",
            (postId, userId),
        ).fetchone()
        if available is None:
            return False, None
        cursor = connection.execute('DELETE FROM postLikes WHERE postId = ? AND userId = ?', (postId, userId))
        isLiked = cursor.rowcount == 0
        if isLiked:
            connection.execute('INSERT INTO postLikes (postId, userId) VALUES (?, ?)', (postId, userId))
        if isLiked:
            from activity_service import record
            owner=connection.execute('SELECT userId FROM posts WHERE postId=?',(postId,)).fetchone()[0]
            record(connection,owner,userId,'like',postId)
        likesCount = connection.execute('SELECT COUNT(*) FROM postLikes WHERE postId = ?', (postId,)).fetchone()[0]
        connection.execute('UPDATE posts SET likesCount = ? WHERE postId = ?', (likesCount, postId))
        return isLiked, likesCount


def getCommentsByPostId(postId, offset=0, limit=None, newest=False):
    connection = getConnection()
    cursor = connection.cursor()

    direction='DESC' if newest else 'ASC'
    cursor.execute(
        f"""
        SELECT
            postComments.commentId,
            postComments.postId,
            postComments.userId,
            postComments.commentText,
            postComments.createdAt,
            postComments.replyToId,
            (SELECT pu.nickname FROM postComments parent JOIN users pu ON pu.userId=parent.userId WHERE parent.commentId=postComments.replyToId) AS replyNickname,
            COALESCE(remoteAccounts.displayNickname, users.nickname) AS nickname
        FROM postComments
        INNER JOIN users ON postComments.userId = users.userId
        LEFT JOIN remoteAccounts ON remoteAccounts.localUserId = users.userId
        WHERE postComments.postId = ?
        ORDER BY postComments.commentId {direction} LIMIT ? OFFSET ?
        """,
        (postId, -1 if limit is None else limit, offset),
    )

    commentRecords = cursor.fetchall()
    connection.close()

    return commentRecords


def deletePostCommentById(commentId, userId):
    with openDatabase() as connection:
        cursor = connection.execute("""DELETE FROM postComments WHERE commentId = ? AND userId = ?
            AND EXISTS (SELECT 1 FROM users WHERE userId = ? AND isBlocked = 0)""",
            (commentId, userId, userId))
        return cursor.rowcount > 0

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

def deleteUserDataById(userId, existingConnection=None):
    context = openDatabase() if existingConnection is None else nullcontext(existingConnection)
    with context as connection:
        # Сначала удаляются личные данные. Чужие комментарии остаются под заглушкой.
        connection.execute('DELETE FROM postComments WHERE userId = ?', (userId,))
        connection.execute('DELETE FROM commentEvents WHERE userId = ?', (userId,))
        connection.execute('DELETE FROM postLikes WHERE userId = ?', (userId,))
        connection.execute('''DELETE FROM workshopProgress WHERE userId = ? OR postId IN
            (SELECT postId FROM posts WHERE userId = ?)''', (userId, userId))
        ownedPosts = connection.execute('SELECT postId FROM posts WHERE userId = ?', (userId,)).fetchall()
        if ownedPosts:
            connection.execute('DELETE FROM activityNotices WHERE postId IN (SELECT postId FROM posts WHERE userId=?)',(userId,))
            deletedAuthor = connection.execute(
                "SELECT userId FROM users WHERE roleName = 'deleted' LIMIT 1"
            ).fetchone()
            if deletedAuthor is None:
                cursor = connection.execute(
                    """INSERT INTO users (email, passwordHash, passwordSalt, nickname, roleName, isBlocked)
                    VALUES (?, '', '', 'Удалённый пользователь', 'deleted', 1)""",
                    (f'deleted-{uuid.uuid4().hex}@invalid.example',)
                )
                deletedAuthorId = cursor.lastrowid
            else:
                deletedAuthorId = deletedAuthor['userId']
            connection.execute(
                """UPDATE posts SET userId = ?, titleText = 'Работа удалена пользователем',
                descriptionText = 'Работа удалена пользователем', tagsText = '', likesCount = 0,
                isDeleted = 1, projectDetailsJson = ''
                WHERE userId = ?""", (deletedAuthorId, userId)
            )
            for postRecord in ownedPosts:
                connection.execute('DELETE FROM postLikes WHERE postId = ?', (postRecord['postId'],))
                connection.execute('DELETE FROM postPhotos WHERE postId = ?', (postRecord['postId'],))
        connection.execute("""UPDATE posts SET likesCount = (
            SELECT COUNT(*) FROM postLikes WHERE postLikes.postId = posts.postId)""")
        connection.execute('DELETE FROM projectMixtures WHERE projectId IN (SELECT projectId FROM projects WHERE userId = ?)', (userId,))
        connection.execute('DELETE FROM projectSteps WHERE projectId IN (SELECT projectId FROM projects WHERE userId = ?)', (userId,))
        connection.execute('DELETE FROM projects WHERE userId = ?', (userId,))
        connection.execute('DELETE FROM colorMixtures WHERE userId = ?', (userId,))
        connection.execute('DELETE FROM lessonProgress WHERE userId = ?', (userId,))
        connection.execute('DELETE FROM lessonFavorites WHERE userId = ?', (userId,))
        connection.execute('DELETE FROM modelFavorites WHERE userId = ?', (userId,))
        connection.execute('DELETE FROM lessonNotes WHERE userId = ?', (userId,))
        connection.execute('DELETE FROM searchHistory WHERE userId = ?', (userId,))
        connection.execute('DELETE FROM accountCodes WHERE userId = ?', (userId,))
        connection.execute('DELETE FROM accountSessions WHERE userId = ?', (userId,))
        connection.execute('DELETE FROM remoteSessionBindings WHERE localUserId = ?', (userId,))
        connection.execute('DELETE FROM remoteAccounts WHERE localUserId = ?', (userId,))
        cursor = connection.execute("DELETE FROM users WHERE userId = ? AND roleName != 'deleted'", (userId,))
        if cursor.rowcount:
            connection.execute("INSERT INTO accountEvents (userId, eventName) VALUES (?, 'selfDelete')", (userId,))
        return cursor.rowcount > 0


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


def createProjectWithSteps(userId, projectName, categoryName, deadlineDate, descriptionText, stepDescriptions,
                           existingConnection=None):
    context = openDatabase() if existingConnection is None else nullcontext(existingConnection)
    with context as connection:
        cursor = connection.execute(
            """INSERT INTO projects (userId, projectName, categoryName, deadlineDate, descriptionText)
            VALUES (?, ?, ?, ?, ?)""", (userId, projectName, categoryName, deadlineDate, descriptionText))
        projectId = cursor.lastrowid
        connection.executemany('INSERT INTO projectSteps (projectId, stepDescription, sortOrder) VALUES (?, ?, ?)',
                               [(projectId, description, position) for position, description in enumerate(stepDescriptions)])
        return projectId


def getLessonProgress(userId, lessonId):
    with openDatabase() as connection:
        record = connection.execute('SELECT stateJson FROM lessonProgress WHERE userId = ? AND lessonId = ?',
                                    (userId, lessonId)).fetchone()
        return record['stateJson'] if record else None


def saveLessonProgress(userId, lessonId, stateJson):
    with openDatabase() as connection:
        connection.execute("""INSERT INTO lessonProgress (userId, lessonId, stateJson) VALUES (?, ?, ?)
            ON CONFLICT (userId, lessonId) DO UPDATE SET stateJson = excluded.stateJson,
            updatedAt = CURRENT_TIMESTAMP""", (userId, lessonId, stateJson))


def updateProjectById(projectId, userId, projectName, categoryName, deadlineDate, descriptionText):
    with openDatabase() as connection:
        cursor = connection.execute("""UPDATE projects SET projectName = ?, categoryName = ?,
            deadlineDate = ?, descriptionText = ? WHERE projectId = ? AND userId = ?""",
            (projectName, categoryName, deadlineDate, descriptionText, projectId, userId))
        return cursor.rowcount > 0


def updateProjectStepDescription(projectId, stepId, userId, description):
    with openDatabase() as connection:
        cursor = connection.execute("""UPDATE projectSteps SET stepDescription = ?
            WHERE stepId = ? AND projectId = ? AND projectId IN
            (SELECT projectId FROM projects WHERE userId = ?)""", (description, stepId, projectId, userId))
        return cursor.rowcount > 0


def createPostWithPhotos(userId, titleText, descriptionText, categoryName, tagsText, photos,
                         projectDetailsJson='', existingConnection=None, challengeId=None):
    context = openDatabase() if existingConnection is None else nullcontext(existingConnection)
    with context as connection:
        if not connection.in_transaction:connection.execute('BEGIN IMMEDIATE')
        connection.execute('SAVEPOINT publication')
        try:
            from contest_entry import publicationTags,enroll
            tagsText=publicationTags(connection,userId,tagsText,challengeId)
            cursor = connection.execute("""INSERT INTO posts
                (userId, titleText, descriptionText, categoryName, tagsText, projectDetailsJson)
                SELECT userId, ?, ?, ?, ?, ? FROM users WHERE userId = ? AND isBlocked = 0""",
                (titleText, descriptionText, categoryName, tagsText, projectDetailsJson, userId))
            if not cursor.rowcount:
                connection.execute('RELEASE publication')
                return None
            postId = cursor.lastrowid
            connection.executemany('INSERT INTO postPhotos (postId, position, imageData) VALUES (?, ?, ?)',
                                   [(postId, index, data) for index, data in enumerate(photos)])
            enroll(connection,postId,strict=True)
            connection.execute('RELEASE publication')
            return postId
        except Exception:
            connection.execute('ROLLBACK TO publication')
            connection.execute('RELEASE publication')
            raise


def getPostPhotoIds(postId):
    with openDatabase() as connection:
        return [row['photoId'] for row in connection.execute("""SELECT ph.photoId FROM postPhotos AS ph
            JOIN posts AS p ON p.postId = ph.postId WHERE ph.postId = ? AND p.isDeleted = 0
            ORDER BY ph.position""", (postId,))]


def getPostPhoto(photoId):
    # Опубликованные фотографии общедоступны. Пути к файлам здесь не принимаются.
    with openDatabase() as connection:
        row = connection.execute("""SELECT ph.imageData FROM postPhotos AS ph
            JOIN posts AS p ON p.postId = ph.postId WHERE ph.photoId = ? AND p.isDeleted = 0""",
            (photoId,)).fetchone()
        return bytes(row['imageData']) if row else None


def updatePostComment(commentId, userId, commentText):
    with openDatabase() as connection:
        cursor = connection.execute("""UPDATE postComments SET commentText = ?
            WHERE commentId = ? AND userId = ? AND createdAt >= datetime('now', '-30 minutes')
            AND EXISTS (SELECT 1 FROM users WHERE userId = ? AND isBlocked = 0)
            AND EXISTS (SELECT 1 FROM posts WHERE posts.postId = postComments.postId AND isDeleted = 0)""",
            (commentText, commentId, userId, userId))
        return cursor.rowcount > 0


def setUserAvatar(userId, imageData):
    with openDatabase() as connection:
        cursor = connection.execute("""UPDATE users SET avatarImage = ?, avatarPath = ''
            WHERE userId = ? AND isBlocked = 0""", (imageData, userId))
        return cursor.rowcount > 0


def getProjectStepPhoto(projectId, stepId, userId):
    with openDatabase() as connection:
        row = connection.execute("""SELECT s.photoImage FROM projectSteps AS s
            JOIN projects AS p ON p.projectId = s.projectId
            WHERE s.projectId = ? AND s.stepId = ? AND p.userId = ?""", (projectId, stepId, userId)).fetchone()
        return bytes(row['photoImage']) if row and row['photoImage'] else None


def setProjectStepPhoto(projectId, stepId, userId, imageData):
    with openDatabase() as connection:
        cursor = connection.execute("""UPDATE projectSteps SET photoImage = ?
            WHERE projectId = ? AND stepId = ?
            AND projectId IN (SELECT projectId FROM projects WHERE userId = ?)
            AND (? IS NOT NULL OR isCompleted = 0)""", (imageData, projectId, stepId, userId, imageData))
        return cursor.rowcount > 0
