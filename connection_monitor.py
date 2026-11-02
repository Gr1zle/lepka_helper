"""Проверка связи и отправка очереди, пока приложение открыто."""
import asyncio
import time
import sqlite3
from api_client import ApiError,apiRequest,getApiUrl
from remote_account_cache import cacheRemoteUser
from offline_access import registerVerified,noteUnavailable
from community_outbox import flush


def startConnectionMonitor(page):
    data=page.data if isinstance(page.data,dict) else {}
    holder=data.get('connectionMonitor') or {'running':False,'stop':False}
    page.data={**data,'connectionMonitor':holder}
    if holder['running']:return
    holder.update(running=True,stop=False)
    async def monitor():
        try:
            while not holder['stop']:
                await asyncio.sleep(5)
                user=page.session.get('currentUser')
                if not user or not user.get('apiUrl') or user.get('apiUrl')!=getApiUrl():continue
                token=user.get('sessionToken');apiUrl=user['apiUrl'];key=(user['userId'],token,apiUrl)
                def active():
                    current=page.session.get('currentUser') or {}
                    return (current.get('userId'),current.get('sessionToken'),getApiUrl())==key
                if user.get('sessionExpiresAt') is not None and user['sessionExpiresAt']<=time.time():
                    from device_session import forgetDeviceSession
                    await asyncio.to_thread(forgetDeviceSession,page)
                    page.session.clear();page.overlay.clear();page.go('/auth');continue
                try:
                    response=await asyncio.to_thread(apiRequest,'GET','/auth/me',sessionToken=token)
                    if not active():continue
                    live=cacheRemoteUser(response['data'],token)
                    if live['userId']!=user['userId']:raise ApiError('Аккаунт изменился',401)
                    registerVerified(live);page.session.set('currentUser',live)
                    previous=page.session.get('connectionState')
                    page.session.set('connectionState','sending')
                    sent=await asyncio.to_thread(flush,live,apiUrl,active)
                    try:
                        from catalog_sync import syncIfNeeded
                        await asyncio.to_thread(syncIfNeeded,live,holder)
                    except ApiError as error:
                        if error.statusCode==401:raise
                    except (ValueError,LookupError,sqlite3.Error):pass
                    if not active():continue
                    page.session.set('connectionState','online')
                    callback=page.session.get('refreshCommunityFeed')
                    if callback and (previous=='offline' or user.get('offline') or sent) and page.route=='/home' and (page.session.get('homeTab') or 0)==0:
                        await asyncio.to_thread(callback)
                except ApiError as error:
                    if not active():continue
                    if error.statusCode==401:
                        from device_session import forgetDeviceSession
                        from offline_access import forgetVerified
                        await asyncio.to_thread(forgetDeviceSession,page)
                        forgetVerified(token);page.session.clear();page.overlay.clear();page.go('/auth')
                        continue
                    noteUnavailable();page.session.set('connectionState','offline')
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception('Не удалось обновить очередь или кеш после проверки связи')
                    # Ошибки кеша/диска не выдают себя за успешную отправку.
                    if active():page.session.set('connectionState','error')
                queueUpdate=page.session.get('refreshOutboxDialog')
                if active() and callable(queueUpdate):queueUpdate()
                update=page.session.get('updateConnectionBanner')
                if active() and callable(update):update()
        finally:holder['running']=False
    page.run_task(monitor)
    page.on_disconnect=lambda event:holder.update(stop=True)
    def reconnect(event):
        holder['stop']=False
        if not holder['running']:startConnectionMonitor(page)
    page.on_connect=reconnect
