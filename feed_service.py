"""Порционная лента с фильтрами и устойчивым порядком."""
import database as db


def page(userId=None,mine=False,query='',category='Все',sort='new',offset=0,limit=12):
    from post_service import POST_CATEGORIES
    if sort not in ('new','popular') or type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=50:
        raise ValueError('Некорректная страница ленты')
    if not isinstance(query,str) or len(query)>120 or category not in ['Все',*POST_CATEGORIES]:raise ValueError('Проверьте фильтры ленты')
    if mine and userId is None:raise ValueError('Выполните вход')
    order='p.likesCount DESC,p.postId DESC' if sort=='popular' else 'p.postId DESC'
    with db.openDatabase() as c:
        c.create_function('fold',1,lambda v:(v or '').casefold())
        records=c.execute(f'''SELECT p.postId,p.userId,p.titleText,p.descriptionText,p.categoryName,p.tagsText,p.likesCount,
            p.isDeleted,p.createdAt,COALESCE(r.displayNickname,u.nickname) AS nickname,
            p.userId=? AS isOwn,EXISTS(SELECT 1 FROM postLikes l WHERE l.postId=p.postId AND l.userId=?) AS isLiked
            FROM posts p JOIN users u ON u.userId=p.userId LEFT JOIN remoteAccounts r ON r.localUserId=p.userId
            WHERE p.isDeleted=0 AND (?=0 OR p.userId=?) AND (?='Все' OR p.categoryName=?)
            AND instr(fold(p.titleText||' '||p.descriptionText||' '||p.tagsText),?)>0
            ORDER BY {order} LIMIT ? OFFSET ?''',(userId,userId,int(mine),userId,category,category,query.strip().casefold(),limit+1,offset)).fetchall()
        result=[]
        for row in records[:limit]:
            item=dict(row)
            item['isOwn']=bool(item['isOwn']);item['isLiked']=bool(item['isLiked'])
            item['photoIds']=[r[0] for r in c.execute('SELECT photoId FROM postPhotos WHERE postId=? ORDER BY position',(row['postId'],))]
            result.append(item)
        return {'items':result,'hasMore':len(records)>limit}
