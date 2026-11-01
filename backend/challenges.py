"""HTTP конкурсного цикла; пользователь определяется только Bearer-сессией."""
from fastapi import Depends, Query, Path
from pydantic import BaseModel, ConfigDict, Field
from backend.moderation import invoke
import challenge_service as service


class ChallengeInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    title: str = Field(min_length=3, max_length=100)
    rules: str = Field(min_length=10, max_length=2000)
    deadline: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    startsOn: str | None = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$')
    theme: str = Field(default='', max_length=80)
    resultMode: str = Field(default='manual', pattern='^(manual|votes)$')


class EntryInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    postId: int = Field(gt=0)


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    state: str = Field(pattern='^(finished|cancelled)$')
    reason: str = Field(min_length=10, max_length=500)
    winnerPostId: int | None = Field(default=None, gt=0)


class VoteInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    liked: bool


def installChallengeRoutes(app, currentUser):
    @app.get('/community/challenges')
    def listing(mode: str = Query('active', pattern='^(active|finished|mine)$'), offset: int = Query(0, ge=0), user=Depends(currentUser)):
        return invoke(lambda: service.listing(user['userId'], mode, offset))

    @app.get('/community/challenge-profile')
    def profile(user=Depends(currentUser)):
        return invoke(lambda: service.profile(user['userId']))

    @app.get('/community/notices')
    def notices(offset: int = Query(0,ge=0),kind: str = Query('all',pattern='^(all|award|like|comment|reply)$'),unread: bool = False,user=Depends(currentUser)):
        return invoke(lambda: service.notices(user['userId'],offset,kind,unread))

    @app.put('/community/notices/{noticeId}/read')
    def read(noticeId: int = Path(),user=Depends(currentUser)):
        return invoke(lambda: service.readNotice(user['userId'],noticeId))

    @app.get('/community/notice-summary')
    def summary(user=Depends(currentUser)):
        return invoke(lambda: service.noticeSummary(user['userId']))

    @app.put('/community/notices-read-all')
    def readAll(user=Depends(currentUser)):
        return invoke(lambda: service.readAllNotices(user['userId']))

    @app.get('/community/challenges/{challengeId}')
    def detail(challengeId: int = Path(gt=0), offset: int = Query(0, ge=0), sort: str = Query('new', pattern='^(new|votes)$'), user=Depends(currentUser)):
        return invoke(lambda: service.detail(user['userId'], challengeId, offset, sort))

    @app.post('/admin/challenges')
    def create(body: ChallengeInput, user=Depends(currentUser)):
        return invoke(lambda: service.create(user['userId'], **body.model_dump()))

    @app.put('/community/challenges/{challengeId}/entry')
    def submit(body: EntryInput, challengeId: int = Path(gt=0), user=Depends(currentUser)):
        return invoke(lambda: service.submit(user['userId'], challengeId, body.postId))

    @app.delete('/community/challenges/{challengeId}/entry')
    def withdraw(challengeId: int = Path(gt=0), user=Depends(currentUser)):
        return invoke(lambda: service.withdraw(user['userId'], challengeId))

    @app.put('/admin/challenges/{challengeId}')
    def finish(body: DecisionInput, challengeId: int = Path(gt=0), user=Depends(currentUser)):
        return invoke(lambda: service.finish(user['userId'], challengeId, **body.model_dump()))

    @app.put('/community/challenges/{challengeId}/votes/{postId}')
    def vote(body: VoteInput, challengeId: int = Path(gt=0), postId: int = Path(gt=0), user=Depends(currentUser)):
        return invoke(lambda: service.vote(user['userId'], challengeId, postId, body.liked))
