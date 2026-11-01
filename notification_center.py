"""Объединение локальных личных событий и страниц API с разными пространствами ID."""
from challenge_gateway import ChallengeClient
from personal_notices import personalItems,readPersonal,instant

SOURCES={'all':'Все источники','community':'Сообщество','projects':'Проекты','learning':'Обучение'}


class NoticeCenter:
    def __init__(self,user):
        self.user=user
        self.community=ChallengeClient(user)

    def local(self,source='all',unread=False):
        return [r for r in personalItems(self.user['userId']) if (source=='all' or r['source']==source) and (not unread or not r['isRead'])]

    def noticeSummary(self):
        result=dict(self.community.noticeSummary())
        local=self.local()
        result['unread']+=sum(not r['isRead'] for r in local)
        result['localUnread']=sum(not r['isRead'] for r in local)
        return result

    def notices(self,offset=0,kind='all',unread=False,source='all'):
        if type(offset) is not int or offset<0 or source not in SOURCES:
            raise ValueError('Некорректная страница или источник')
        local=self.local(source,unread) if source!='community' and kind=='all' else []
        local.sort(key=lambda r:(instant(r['createdAt']),r['noticeId']),reverse=True)
        if source in ('projects','learning'):return local[offset:offset+50]
        # Даже если все локальные события новее серверных, этот префикс
        # серверных событий заведомо расположен до искомой страницы.
        skip=max(0,offset-len(local))
        items=[]
        for start in range(skip,offset+50,50):
            batch=self.community.notices(start,kind,unread)
            items.extend([{**r,'source':'community','noticeId':'community:'+str(r['noticeId']), '_order':start+index} for index,r in enumerate(batch)])
            if len(batch)<50:break
        items.extend(local)
        items.sort(key=lambda r:(instant(r['createdAt']),1 if r['source']=='community' else 0,-r.get('_order',0),r['noticeId']),reverse=True)
        return items[offset-skip:offset-skip+50]

    def readNotice(self,noticeId):
        if noticeId.startswith('community:'):return self.community.readNotice(int(noticeId.split(':')[1]))
        return readPersonal(self.user['userId'],noticeId)

    def readAllNotices(self):
        # При сетевой ошибке не выдаём частичное чтение за успешное.
        self.community.readAllNotices()
        readPersonal(self.user['userId'])
