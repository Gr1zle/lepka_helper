"""Пользовательские роли, живые права, удаление аккаунта и личные решения по жалобам."""
import unittest
from unittest.mock import patch
import test_moderation as fixtures
import database as db
import role_service as roles
import moderation_service as moderation
import challenge_service as contests

REASON='Учебная проверка административных полномочий'


class RoleAdminTests(unittest.TestCase):
    setUp=fixtures.ModerationTests.setUp
    login=fixtures.ModerationTests.login

    def assign(self,permissions):
        roles.save(self.admin,'helper','Помощник',permissions,REASON,True)
        moderation.changeUser(self.admin,self.reader,REASON,role='helper')
        self.readerHeaders=self.login('reader@example.com')
        return self.readerHeaders

    def test_scoped_moderator_and_privilege_escalation_are_checked_by_http(self):
        headers=self.assign(['reports.manage','materials.remove'])
        access=self.client.get('/community/access',headers=headers).json()['data']
        self.assertEqual(set(access['permissions']),{'reports.manage','materials.remove'})
        self.assertEqual(self.client.get('/admin/reports',headers=headers).status_code,200)
        for path in ('/admin/users','/admin/audit','/admin/roles'):
            self.assertEqual(self.client.get(path,headers=headers).status_code,403)
        self.assertEqual(self.client.put(f'/admin/users/{self.reader}',headers=headers,json=dict(role='admin',reason=REASON)).status_code,403)
        self.assertEqual(self.client.post('/admin/roles/evil',headers=headers,json=dict(title='Новая роль',permissions=[],reason=REASON)).status_code,403)
        self.assertEqual(self.client.post('/admin/remove',headers=headers,json=dict(targetType='comment',targetId=self.comment,reason=REASON)).status_code,200)
        self.assertEqual(db.getUserByEmail('reader@example.com')['roleName'],'helper')

    def test_permission_edit_revokes_sessions_and_later_login_has_fresh_rights(self):
        headers=self.assign(['reports.manage'])
        roles.save(self.admin,'helper','Помощник',[],REASON)
        self.assertEqual(self.client.get('/admin/reports',headers=headers).status_code,401)
        fresh=self.login('reader@example.com')
        self.assertEqual(self.client.get('/community/access',headers=fresh).json()['data']['permissions'],[])
        self.assertEqual(self.client.get('/admin/reports',headers=fresh).status_code,403)
        self.assertFalse(roles.save(self.admin,'helper','Помощник',[],REASON))
        self.assertEqual(self.client.get('/community/access',headers=fresh).status_code,200)

    def test_role_validation_builtin_protection_dependencies_and_assigned_delete(self):
        cases=[('admin',[]),('deleted',[]),('guest',[]),('bad/path',[]),('helper',['roles.manage']),('helper',['accounts.block']),('helper',['reports.manage']*2)]
        for code,perms in cases:
            with self.assertRaises(ValueError):roles.save(self.admin,code,'Тестовая роль',perms,REASON,True)
        self.assign(['accounts.view'])
        with self.assertRaises(ValueError):roles.remove(self.admin,'helper',REASON)
        for code in ('admin','user','guest'):
            with self.assertRaises(ValueError):roles.remove(self.admin,code,REASON)
        moderation.changeUser(self.admin,self.reader,REASON,role='user')
        self.assertTrue(roles.remove(self.admin,'helper',REASON))
        self.assertFalse(roles.remove(self.admin,'helper',REASON))
        with self.assertRaises(ValueError):moderation.changeUser(self.admin,self.author,REASON,role='unknown')

    def test_staff_can_block_and_delete_regular_users_but_not_administrators_or_other_staff(self):
        self.assign(['accounts.view','accounts.block','accounts.delete'])
        self.assertTrue(moderation.changeUser(self.reader,self.author,REASON,blocked=True))
        self.assertTrue(moderation.changeUser(self.reader,self.author,REASON,blocked=False))
        with self.assertRaises(roles.PermissionDenied):moderation.changeUser(self.reader,self.admin,REASON,blocked=True)
        with self.assertRaises(roles.PermissionDenied):moderation.deleteUser(self.reader,self.admin,REASON)
        with self.assertRaises(ValueError):moderation.deleteUser(self.reader,self.reader,REASON)
        self.assertTrue(moderation.deleteUser(self.reader,self.author,REASON))
        self.assertIsNone(db.getUserByEmail('author@example.com'))

    def test_contest_manager_without_access_to_private_accounts_or_roles(self):
        headers=self.assign(['contests.manage'])
        response=self.client.post('/admin/challenges',headers=headers,json=dict(title='Конкурс помощника',rules='Подробные правила конкурса',deadline=contests.today()))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.get('/admin/users',headers=headers).status_code,403)
        self.assertEqual(self.client.get('/admin/roles',headers=headers).status_code,403)
        with db.openDatabase() as c:c.execute("UPDATE customRoles SET permissionsJson='[]' WHERE roleCode='helper'")
        # Даже обработчик со старым снимком UI не получает права из него.
        response=self.client.post('/admin/challenges',headers=headers,json=dict(title='Другой конкурс',rules='Подробные правила конкурса',deadline=contests.today()))
        self.assertEqual(response.status_code,403)

    def test_admin_deletion_cleans_private_data_sessions_and_records_reason(self):
        from project_service import saveProject
        saveProject(self.author,'Личный проект','Животные','','')
        moderation.reportMaterial(self.reader,'post',self.post,REASON)
        response=self.client.post(f'/admin/users/{self.author}/delete',headers=self.adminHeaders,json={'reason':REASON})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.get('/profile',headers=self.authorHeaders).status_code,401)
        self.assertEqual(moderation.myReports(self.reader)[0]['status'],'resolved')
        with db.openDatabase() as c:
            self.assertIsNone(c.execute('SELECT 1 FROM users WHERE userId=?',(self.author,)).fetchone())
            self.assertEqual(c.execute('SELECT COUNT(*) FROM projects WHERE userId=?',(self.author,)).fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM postPhotos WHERE postId=?',(self.post,)).fetchone()[0],0)
            self.assertEqual(c.execute('SELECT isDeleted FROM posts WHERE postId=?',(self.post,)).fetchone()[0],1)
            self.assertEqual(c.execute("SELECT reason FROM adminAudit WHERE action='user.delete'").fetchone()[0],REASON)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(self.client.post(f'/admin/users/{self.admin}/delete',headers=self.adminHeaders,json={'reason':REASON}).status_code,400)

    def test_audit_failures_rollback_role_edit_and_user_delete(self):
        self.assign(['reports.manage'])
        with patch('moderation_service.audit',side_effect=ValueError('Synthetic audit failure')):
            with self.assertRaises(ValueError):roles.save(self.admin,'helper','Помощник',[],REASON)
            with self.assertRaises(ValueError):moderation.deleteUser(self.admin,self.author,REASON)
        self.assertEqual(roles.access(self.reader)['permissions'],['reports.manage'])
        self.assertIsNotNone(db.getUserByEmail('author@example.com'))
        self.assertEqual(self.client.get('/admin/reports',headers=self.readerHeaders).status_code,200)
        self.assertEqual(self.client.get('/profile',headers=self.authorHeaders).status_code,200)

    def test_my_reports_reveal_only_own_reason_and_resolution_after_material_removed(self):
        rid=moderation.reportMaterial(self.reader,'post',self.post,REASON)
        moderation.reportMaterial(self.author,'comment',self.comment,'Другая причина нарушения правил')
        moderation.removeMaterial(self.admin,'post',self.post,'Подтверждено нарушение правил сообщества')
        rows=self.client.get('/community/my-reports',headers=self.readerHeaders).json()['data']
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['reportId'],rid)
        self.assertEqual(rows[0]['status'],'resolved')
        self.assertIn('Подтверждено',rows[0]['resolution'])
        self.assertNotIn('reporterId',rows[0]);self.assertNotIn('resolvedBy',rows[0])
        self.assertEqual(self.client.get('/community/my-reports').status_code,401)
        self.assertEqual(moderation.myReports(self.reader,50),[])

if __name__=='__main__':unittest.main()
