"""Идентификаторы заявок принадлежат текущему режиму сообщества."""
from urllib.parse import urlencode
from moderation_gateway import ModerationClient
import challenge_service as service


class ChallengeClient(ModerationClient):
    def listing(self, mode='active', offset=0):
        return self.call('GET', '/community/challenges?' + urlencode(dict(mode=mode, offset=offset)),
                         local=lambda actor: service.listing(actor, mode, offset))

    def detail(self, challengeId, offset=0, sort='new'):
        return self.call('GET', f'/community/challenges/{challengeId}?' + urlencode(dict(offset=offset, sort=sort)),
                         local=lambda actor: service.detail(actor, challengeId, offset, sort))

    def create(self, title, rules, deadline, startsOn=None, theme='', resultMode='manual'):
        return self.call('POST', '/admin/challenges', dict(title=title, rules=rules, deadline=deadline, startsOn=startsOn, theme=theme, resultMode=resultMode),
                         lambda actor: service.create(actor, title, rules, deadline, startsOn, theme, resultMode))

    def submit(self, challengeId, postId):
        return self.call('PUT', f'/community/challenges/{challengeId}/entry', dict(postId=postId),
                         lambda actor: service.submit(actor, challengeId, postId))

    def withdraw(self, challengeId):
        return self.call('DELETE', f'/community/challenges/{challengeId}/entry',
                         local=lambda actor: service.withdraw(actor, challengeId))

    def finish(self, challengeId, state, reason, winnerPostId=None):
        return self.call('PUT', f'/admin/challenges/{challengeId}', dict(state=state, reason=reason, winnerPostId=winnerPostId),
                         lambda actor: service.finish(actor, challengeId, state, reason, winnerPostId))

    def vote(self, challengeId, postId, liked):
        return self.call('PUT', f'/community/challenges/{challengeId}/votes/{postId}', dict(liked=liked),
                         lambda actor: service.vote(actor, challengeId, postId, liked))

    def profile(self):
        return self.call('GET','/community/challenge-profile',local=lambda actor:service.profile(actor))

    def notices(self,offset=0):
        return self.call('GET',f'/community/notices?offset={offset}',local=lambda actor:service.notices(actor,offset))

    def readNotice(self,noticeId):
        return self.call('PUT',f'/community/notices/{noticeId}/read',local=lambda actor:service.readNotice(actor,noticeId))
