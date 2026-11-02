"""Android Keystore bridge. No plaintext-token fallback and no browser storage."""
import json
import secrets
import threading
import flet as ft


class ProtectedSession(ft.Control):
    def __init__(self):
        super().__init__()
        self._uiPending=None
        self._pending={};self._lock=threading.Lock();self._serial=threading.Lock()
        self._add_event_handler('result',self._received)
    def _get_control_name(self):return 'lepka_protected_session'
    def _received(self,event):
        try:record=json.loads(event.data)
        except (ValueError,TypeError):return
        with self._lock:
            pending=self._pending.get(record.get('requestId'))
            if pending and 'callback' not in pending:pending['result']=record;pending['event'].set()
            callback=pending.get('callback') if pending else None
            if callback:
                self._pending.pop(record['requestId'],None);self._uiPending=None
        if callback:
            self._set_attr('uiCommand','')
            try:self.update()
            except (AssertionError,OSError):pass
            callback(record)
    def requestUi(self,operation,value,callback):
        # User-owned dialogs have a separate command channel and no eight-second timeout.
        with self._lock:
            if self._uiPending:raise OSError('Завершите предыдущий выбор файла или снимка')
            requestId=secrets.token_hex(16);self._uiPending=requestId
            self._pending[requestId]={'callback':callback}
        try:
            self._set_attr('uiCommand',json.dumps(dict(requestId=requestId,operation=operation,value=value),ensure_ascii=False));self.update()
        except Exception:
            with self._lock:self._pending.pop(requestId,None);self._uiPending=None
            raise
    def call(self,operation,value=None,stillActive=None):
        with self._serial:
            if stillActive is not None and not stillActive():return None
            requestId=secrets.token_hex(16);pending={'event':threading.Event(),'result':None}
            with self._lock:self._pending[requestId]=pending
            try:
                self._set_attr('command',json.dumps(dict(requestId=requestId,operation=operation,value=value),ensure_ascii=False))
                self.update()
                if not pending['event'].wait(8):raise OSError('Защищённое хранилище не ответило')
                result=pending['result']
                if not result.get('ok'):raise OSError('Защищённое хранилище недоступно')
                return result.get('value')
            finally:
                with self._lock:self._pending.pop(requestId,None)
                self._set_attr('command','')
    def read(self):return self.call('read')
    def write(self,value):return self.call('write',value)=='ok'
    def delete(self):return self.call('delete')=='ok'


def attachProtectedSession(page):
    control=ProtectedSession();page.overlay.append(control);page.update()
    state=page.data if isinstance(page.data,dict) else {}
    page.data={**state,'protectedSession':control}
    page.session.set('protectedSession',control)
    return control


def getProtectedSession(page):
    if not hasattr(page,'session'):return None
    control=page.session.get('protectedSession')
    if control is None and isinstance(page.data,dict):control=page.data.get('protectedSession')
    if control is None:return attachProtectedSession(page)
    if isinstance(control,ProtectedSession) and control not in page.overlay:
        return attachProtectedSession(page)
    return control
