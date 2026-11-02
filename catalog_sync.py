"""Light metadata and usage sync; media is downloaded only by explicit request."""
import time
from database import openDatabase
from catalog_client import CatalogClient


def syncIfNeeded(user,holder):
    if time.monotonic()<holder.get('catalogNext',0):return
    holder['catalogNext']=time.monotonic()+60
    with openDatabase() as c:
        used=c.execute('SELECT 1 FROM learningIndex WHERE userId=? AND apiUrl=?',(user['userId'],user.get('apiUrl',''))).fetchone()
    if not used:return
    client=CatalogClient(user);client.index();client.flushUsage()
