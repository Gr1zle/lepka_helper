-- Fresh schema; data and internal sqlite_sequence are not exported.

CREATE TABLE accountCodes (
        email TEXT NOT NULL, purpose TEXT NOT NULL, userId INTEGER NOT NULL,
        codeHash TEXT NOT NULL, expiresAt REAL NOT NULL, sentAt REAL NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (email, purpose), FOREIGN KEY (userId) REFERENCES users(userId)
    );

CREATE TABLE accountEvents (
        eventId INTEGER PRIMARY KEY AUTOINCREMENT, userId INTEGER NOT NULL,
        eventName TEXT NOT NULL, createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

CREATE TABLE accountSessions (
        tokenHash TEXT PRIMARY KEY, userId INTEGER NOT NULL, expiresAt REAL NOT NULL,
        FOREIGN KEY (userId) REFERENCES users(userId)
    );

CREATE TABLE activityNotices (
        noticeId INTEGER PRIMARY KEY AUTOINCREMENT, userId INTEGER NOT NULL, actorId INTEGER NOT NULL,
        kind TEXT NOT NULL, postId INTEGER NOT NULL, commentId INTEGER, eventKey TEXT NOT NULL,
        isRead INTEGER NOT NULL DEFAULT 0, createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(userId,eventKey),
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY(actorId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY(postId) REFERENCES posts(postId) ON DELETE CASCADE,
        FOREIGN KEY(commentId) REFERENCES postComments(commentId) ON DELETE CASCADE);

CREATE TABLE adminAudit (
        eventId INTEGER PRIMARY KEY AUTOINCREMENT, actorId INTEGER,
        actorNickname TEXT NOT NULL, action TEXT NOT NULL,
        targetType TEXT NOT NULL, targetId INTEGER NOT NULL, reason TEXT NOT NULL,
        createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(actorId) REFERENCES users(userId) ON DELETE SET NULL);

CREATE TABLE challengeAwards (
        challengeId INTEGER NOT NULL, place INTEGER NOT NULL, postId INTEGER, userId INTEGER,
        votes INTEGER NOT NULL, PRIMARY KEY(challengeId,place),
        FOREIGN KEY(challengeId) REFERENCES challenges(challengeId) ON DELETE CASCADE,
        FOREIGN KEY(postId) REFERENCES posts(postId) ON DELETE SET NULL,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE SET NULL);

CREATE TABLE challengeEntries (
        challengeId INTEGER NOT NULL, userId INTEGER NOT NULL, postId INTEGER NOT NULL,
        createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(challengeId,userId), UNIQUE(challengeId,postId),
        FOREIGN KEY(challengeId) REFERENCES challenges(challengeId) ON DELETE CASCADE,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY(postId) REFERENCES posts(postId) ON DELETE CASCADE);

CREATE TABLE challengeOptOuts (
        challengeId INTEGER NOT NULL,userId INTEGER NOT NULL,PRIMARY KEY(challengeId,userId),
        FOREIGN KEY(challengeId) REFERENCES challenges(challengeId) ON DELETE CASCADE,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE);

CREATE TABLE challengeVotes (
        challengeId INTEGER NOT NULL, postId INTEGER NOT NULL, userId INTEGER NOT NULL,
        PRIMARY KEY(challengeId,postId,userId),
        FOREIGN KEY(challengeId,postId) REFERENCES challengeEntries(challengeId,postId) ON DELETE CASCADE,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE);

CREATE TABLE challenges (
        challengeId INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
        rules TEXT NOT NULL, deadline TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'open',
        createdBy INTEGER, winnerPostId INTEGER, result TEXT NOT NULL DEFAULT '',
        createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, startsOn TEXT NOT NULL DEFAULT '', theme TEXT NOT NULL DEFAULT '', resultMode TEXT NOT NULL DEFAULT 'manual',
        FOREIGN KEY(createdBy) REFERENCES users(userId) ON DELETE SET NULL,
        FOREIGN KEY(winnerPostId) REFERENCES posts(postId) ON DELETE SET NULL);

CREATE TABLE colorMixtures (
            mixtureId INTEGER PRIMARY KEY AUTOINCREMENT,
            userId INTEGER NOT NULL,
            mixtureName TEXT NOT NULL,
            resultHex TEXT NOT NULL,
            totalWeight REAL NOT NULL,
            recipeJson TEXT NOT NULL,
            createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (userId) REFERENCES users(userId)
        );

CREATE TABLE commentEvents (
        userId INTEGER NOT NULL, createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (userId) REFERENCES users(userId)
    );

CREATE TABLE communityActionReceipts (
        userId INTEGER NOT NULL,requestId TEXT NOT NULL,kind TEXT NOT NULL,payloadHash TEXT NOT NULL,resultJson TEXT NOT NULL,
        PRIMARY KEY(userId,requestId),FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE);

CREATE TABLE communityCache (
        userId INTEGER NOT NULL,apiUrl TEXT NOT NULL,cacheKey TEXT NOT NULL,contentJson TEXT NOT NULL,updatedAt REAL NOT NULL,
        PRIMARY KEY(userId,apiUrl,cacheKey),FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE);

CREATE TABLE communityNotices (
        noticeId INTEGER PRIMARY KEY AUTOINCREMENT, userId INTEGER NOT NULL,
        challengeId INTEGER NOT NULL, place INTEGER NOT NULL, isRead INTEGER NOT NULL DEFAULT 0,
        createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(userId,challengeId,place),
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY(challengeId) REFERENCES challenges(challengeId) ON DELETE CASCADE);

CREATE TABLE communityOutbox (
        requestId TEXT PRIMARY KEY,userId INTEGER NOT NULL,apiUrl TEXT NOT NULL,serverUserId INTEGER NOT NULL,
        kind TEXT NOT NULL,payloadJson TEXT NOT NULL,payloadHash TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
        nextAttemptAt REAL NOT NULL DEFAULT 0,leaseUntil REAL NOT NULL DEFAULT 0,leaseToken TEXT NOT NULL DEFAULT '',
        lastError TEXT NOT NULL DEFAULT '',resultJson TEXT,createdAt REAL NOT NULL,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE);

CREATE TABLE communityRequests (
        userId INTEGER NOT NULL, requestId TEXT NOT NULL, payloadHash TEXT NOT NULL, postId INTEGER NOT NULL,
        PRIMARY KEY (userId, requestId),
        FOREIGN KEY (userId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY (postId) REFERENCES posts(postId) ON DELETE CASCADE
    );

CREATE TABLE customRoles (
        roleCode TEXT PRIMARY KEY,title TEXT NOT NULL,permissionsJson TEXT NOT NULL);

CREATE TABLE deliverySettings (
        userId INTEGER PRIMARY KEY REFERENCES users(userId) ON DELETE CASCADE,
        deviceEnabled INTEGER NOT NULL DEFAULT 0, likes INTEGER NOT NULL DEFAULT 1,
        comments INTEGER NOT NULL DEFAULT 1, replies INTEGER NOT NULL DEFAULT 1,
        awards INTEGER NOT NULL DEFAULT 1, projects INTEGER NOT NULL DEFAULT 1,
        learning INTEGER NOT NULL DEFAULT 1, emailEnabled INTEGER NOT NULL DEFAULT 0);

CREATE TABLE importedModels (
        modelId TEXT PRIMARY KEY, userId INTEGER NOT NULL, title TEXT NOT NULL,
        objText TEXT NOT NULL, materialText TEXT NOT NULL, previewImage BLOB NOT NULL,
        createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE);

CREATE TABLE learningAssets (
        assetId TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, mime TEXT NOT NULL,
        content BLOB NOT NULL, creatorId INTEGER REFERENCES users(userId) ON DELETE SET NULL, createdAt REAL NOT NULL);

CREATE TABLE learningCache (
        userId INTEGER REFERENCES users(userId) ON DELETE CASCADE, apiUrl TEXT NOT NULL, contentId TEXT NOT NULL,
        revision INTEGER NOT NULL, documentJson TEXT NOT NULL, assetsJson TEXT NOT NULL, byteCount INTEGER NOT NULL,
        downloadedAt REAL NOT NULL, PRIMARY KEY(userId,apiUrl,contentId));

CREATE TABLE learningCatalog (
        contentId TEXT PRIMARY KEY, revision INTEGER NOT NULL, state TEXT NOT NULL,
        documentJson TEXT NOT NULL, creatorId INTEGER REFERENCES users(userId) ON DELETE SET NULL,
        updatedAt TEXT NOT NULL);

CREATE TABLE learningCatalogNotices (
        userId INTEGER REFERENCES users(userId) ON DELETE CASCADE, apiUrl TEXT NOT NULL, contentId TEXT NOT NULL,
        revision INTEGER NOT NULL, title TEXT NOT NULL, isRead INTEGER NOT NULL DEFAULT 0, createdAt TEXT NOT NULL,
        PRIMARY KEY(userId,apiUrl,contentId,revision));

CREATE TABLE learningIndex (
        userId INTEGER REFERENCES users(userId) ON DELETE CASCADE, apiUrl TEXT NOT NULL, itemsJson TEXT NOT NULL,
        PRIMARY KEY(userId,apiUrl));

CREATE TABLE learningNotices (
        noticeId INTEGER PRIMARY KEY AUTOINCREMENT,userId INTEGER NOT NULL,lessonId INTEGER NOT NULL,
        kind TEXT NOT NULL,eventKey TEXT NOT NULL,createdAt TEXT NOT NULL,isRead INTEGER NOT NULL DEFAULT 0,
        snoozedUntil TEXT,UNIQUE(userId,eventKey),
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE);

CREATE TABLE learningPersonal (
        userId INTEGER REFERENCES users(userId) ON DELETE CASCADE, apiUrl TEXT NOT NULL, contentId TEXT NOT NULL,
        revision INTEGER NOT NULL, checkedJson TEXT NOT NULL DEFAULT '[]', favorite INTEGER NOT NULL DEFAULT 0,
        note TEXT NOT NULL DEFAULT '', viewPending INTEGER NOT NULL DEFAULT 1, completePending INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(userId,apiUrl,contentId));

CREATE TABLE learningSubscriptions (
        userId INTEGER REFERENCES users(userId) ON DELETE CASCADE, apiUrl TEXT NOT NULL, category TEXT NOT NULL,
        PRIMARY KEY(userId,apiUrl,category));

CREATE TABLE learningUsage (
        userId INTEGER REFERENCES users(userId) ON DELETE CASCADE, contentId TEXT REFERENCES learningCatalog(contentId) ON DELETE CASCADE,
        revision INTEGER NOT NULL, viewedAt TEXT NOT NULL, completedAt TEXT, PRIMARY KEY(userId,contentId,revision));

CREATE TABLE lessonFavorites (
        userId INTEGER NOT NULL, lessonId INTEGER NOT NULL,
        savedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(userId,lessonId), FOREIGN KEY(userId) REFERENCES users(userId));

CREATE TABLE lessonNotes (
        userId INTEGER NOT NULL, lessonId INTEGER NOT NULL, noteText TEXT NOT NULL,
        updatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(userId,lessonId), FOREIGN KEY(userId) REFERENCES users(userId));

CREATE TABLE lessonProgress (
        userId INTEGER NOT NULL, lessonId INTEGER NOT NULL, stateJson TEXT NOT NULL,
        updatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (userId, lessonId), FOREIGN KEY (userId) REFERENCES users(userId)
    );

CREATE TABLE localPostExports (
        apiUrl TEXT NOT NULL, userId INTEGER NOT NULL, localPostId INTEGER NOT NULL,
        requestId TEXT NOT NULL, serverPostId INTEGER,
        PRIMARY KEY (apiUrl, userId, localPostId),
        FOREIGN KEY (userId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY (localPostId) REFERENCES posts(postId) ON DELETE CASCADE
    );

CREATE TABLE modelFavorites (
        userId INTEGER NOT NULL, modelId TEXT NOT NULL,
        PRIMARY KEY(userId,modelId), FOREIGN KEY(userId) REFERENCES users(userId));

CREATE TABLE moderationReports (
        reportId INTEGER PRIMARY KEY AUTOINCREMENT,
        reporterId INTEGER, targetType TEXT NOT NULL, targetId INTEGER NOT NULL,
        reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
        resolution TEXT NOT NULL DEFAULT '', resolvedBy INTEGER,
        createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, resolvedAt TEXT,
        UNIQUE(reporterId,targetType,targetId),
        FOREIGN KEY(reporterId) REFERENCES users(userId) ON DELETE SET NULL,
        FOREIGN KEY(resolvedBy) REFERENCES users(userId) ON DELETE SET NULL);

CREATE TABLE notificationMailQueue (
        mailId TEXT PRIMARY KEY, userId INTEGER NOT NULL REFERENCES users(userId) ON DELETE CASCADE,
        email TEXT NOT NULL, eventKey TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
        nextAttempt REAL NOT NULL DEFAULT 0, leaseUntil REAL NOT NULL DEFAULT 0,
        createdAt REAL NOT NULL, lastError TEXT NOT NULL DEFAULT '');

CREATE TABLE notificationMailState (
        userId INTEGER PRIMARY KEY REFERENCES users(userId) ON DELETE CASCADE, since TEXT NOT NULL);

CREATE TABLE personalCheckpoints (
        checkpointId TEXT PRIMARY KEY,userId INTEGER NOT NULL,title TEXT NOT NULL,content BLOB NOT NULL,
        checksum TEXT NOT NULL,createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE);

CREATE TABLE personalNoticeSettings (
        userId INTEGER PRIMARY KEY, projectsEnabled INTEGER NOT NULL DEFAULT 1,
        lessonsEnabled INTEGER NOT NULL DEFAULT 1, resumeDays INTEGER NOT NULL DEFAULT 3,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE);

CREATE TABLE personalSyncState (
        userId INTEGER NOT NULL,apiUrl TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0,
        checksum TEXT NOT NULL DEFAULT '',pending INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(userId,apiUrl),FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE);

CREATE TABLE personalVault (
        userId INTEGER PRIMARY KEY,revision INTEGER NOT NULL,checksum TEXT NOT NULL,
        snapshotJson TEXT NOT NULL,deviceId TEXT NOT NULL,updatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE);

CREATE TABLE personalVaultHistory (
        userId INTEGER NOT NULL,revision INTEGER NOT NULL,checksum TEXT NOT NULL,snapshotJson TEXT NOT NULL,
        deviceId TEXT NOT NULL,updatedAt TEXT NOT NULL,PRIMARY KEY(userId,revision),
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE);

CREATE TABLE postComments (
            commentId INTEGER PRIMARY KEY AUTOINCREMENT,
            postId INTEGER NOT NULL,
            userId INTEGER NOT NULL,
            commentText TEXT NOT NULL,
            createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, replyToId INTEGER REFERENCES postComments(commentId) ON DELETE SET NULL,
            FOREIGN KEY (postId) REFERENCES posts(postId),
            FOREIGN KEY (userId) REFERENCES users(userId)
        );

CREATE TABLE postLikes (
            likeId INTEGER PRIMARY KEY AUTOINCREMENT,
            postId INTEGER NOT NULL,
            userId INTEGER NOT NULL,
            createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (postId) REFERENCES posts(postId),
            FOREIGN KEY (userId) REFERENCES users(userId),
            UNIQUE(postId, userId)
        );

CREATE TABLE postPhotos (
        photoId INTEGER PRIMARY KEY AUTOINCREMENT, postId INTEGER NOT NULL,
        position INTEGER NOT NULL, imageData BLOB NOT NULL,
        FOREIGN KEY (postId) REFERENCES posts(postId), UNIQUE(postId, position)
    );

CREATE TABLE posts (
            postId INTEGER PRIMARY KEY AUTOINCREMENT,
            userId INTEGER NOT NULL,
            titleText TEXT NOT NULL,
            descriptionText TEXT NOT NULL,
            categoryName TEXT NOT NULL,
            tagsText TEXT,
            likesCount INTEGER NOT NULL DEFAULT 0,
            createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, isDeleted INTEGER NOT NULL DEFAULT 0, projectDetailsJson TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (userId) REFERENCES users(userId)
        );

CREATE TABLE projectMixtures (
        projectMixtureId INTEGER PRIMARY KEY AUTOINCREMENT, projectId INTEGER NOT NULL,
        mixtureJson TEXT NOT NULL, FOREIGN KEY (projectId) REFERENCES projects(projectId)
    );

CREATE TABLE projectReminders (
        reminderId INTEGER PRIMARY KEY AUTOINCREMENT,
        userId INTEGER NOT NULL, projectId INTEGER NOT NULL,
        deadlineDate TEXT NOT NULL, kind TEXT NOT NULL,
        generatedDate TEXT NOT NULL, isRead INTEGER NOT NULL DEFAULT 0,
        UNIQUE(userId,projectId,deadlineDate,kind),
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY(projectId) REFERENCES projects(projectId) ON DELETE CASCADE);

CREATE TABLE projectSteps (
            stepId INTEGER PRIMARY KEY AUTOINCREMENT,
            projectId INTEGER NOT NULL,
            stepDescription TEXT NOT NULL,
            isCompleted INTEGER NOT NULL DEFAULT 0,
            createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, photoImage BLOB, detailsText TEXT NOT NULL DEFAULT '', sortOrder INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (projectId) REFERENCES projects(projectId)
        );

CREATE TABLE projects (
            projectId INTEGER PRIMARY KEY AUTOINCREMENT,
            userId INTEGER NOT NULL,
            projectName TEXT NOT NULL,
            categoryName TEXT NOT NULL,
            deadlineDate TEXT,
            descriptionText TEXT,
            progressPercent REAL NOT NULL DEFAULT 0,
            createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finalPhotoImage BLOB, isFinished INTEGER NOT NULL DEFAULT 0, completedAt TEXT,
            FOREIGN KEY (userId) REFERENCES users(userId)
        );

CREATE TABLE publicationDrafts (
        draftId TEXT PRIMARY KEY,userId INTEGER NOT NULL,apiUrl TEXT NOT NULL,payloadJson TEXT NOT NULL,updatedAt REAL NOT NULL,
        FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE);

CREATE TABLE referenceImages (
        referenceId TEXT PRIMARY KEY,userId INTEGER NOT NULL REFERENCES users(userId) ON DELETE CASCADE,
        apiUrl TEXT NOT NULL,title TEXT NOT NULL,image BLOB NOT NULL,createdAt REAL NOT NULL);

CREATE TABLE remoteAccounts (
        apiUrl TEXT NOT NULL, remoteUserId INTEGER NOT NULL, localUserId INTEGER NOT NULL UNIQUE,
        displayNickname TEXT NOT NULL, PRIMARY KEY (apiUrl, remoteUserId),
        FOREIGN KEY (localUserId) REFERENCES users(userId)
    );

CREATE TABLE remoteProfileCache (
        userId INTEGER NOT NULL,apiUrl TEXT NOT NULL,profileJson TEXT NOT NULL,
        PRIMARY KEY(userId,apiUrl),FOREIGN KEY(userId) REFERENCES users(userId) ON DELETE CASCADE);

CREATE TABLE remoteSessionBindings (
        tokenHash TEXT PRIMARY KEY, apiUrl TEXT NOT NULL, localUserId INTEGER NOT NULL,
        FOREIGN KEY (localUserId) REFERENCES users(userId)
    );

CREATE TABLE searchHistory (
        userId INTEGER NOT NULL, queryKey TEXT NOT NULL, queryText TEXT NOT NULL,
        lastUsed INTEGER NOT NULL, PRIMARY KEY(userId,queryKey),
        FOREIGN KEY(userId) REFERENCES users(userId));

CREATE TABLE users (
            userId INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            passwordHash TEXT NOT NULL,
            passwordSalt TEXT NOT NULL,
            nickname TEXT NOT NULL UNIQUE,
            roleName TEXT NOT NULL DEFAULT 'user',
            isBlocked INTEGER NOT NULL DEFAULT 0,
            createdAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        , emailVerified INTEGER NOT NULL DEFAULT 1, loginFailures INTEGER NOT NULL DEFAULT 0, loginBlockedUntil REAL NOT NULL DEFAULT 0, passwordFailures INTEGER NOT NULL DEFAULT 0, passwordBlockedUntil REAL NOT NULL DEFAULT 0, bioText TEXT DEFAULT '', ageCategory TEXT DEFAULT 'Взрослый 18+', favoriteColorsJson TEXT DEFAULT '[]', themeMode TEXT DEFAULT 'light', languageCode TEXT DEFAULT 'ru', notificationsEnabled INTEGER DEFAULT 1, avatarPath TEXT DEFAULT '', avatarImage BLOB);

CREATE TABLE workshopProgress (
        userId INTEGER NOT NULL, postId INTEGER NOT NULL, stateJson TEXT NOT NULL,
        PRIMARY KEY (userId, postId),
        FOREIGN KEY (userId) REFERENCES users(userId) ON DELETE CASCADE,
        FOREIGN KEY (postId) REFERENCES posts(postId) ON DELETE CASCADE
    );

CREATE INDEX activityRecipient ON activityNotices(userId,noticeId);
CREATE INDEX commentEventsUserTime ON commentEvents(userId, createdAt);
