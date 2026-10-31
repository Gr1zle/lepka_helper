from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import database as db
from lesson_library import (saveLessonFavorite,favoriteLessonIds,getLessonNote,saveLessonNote,
    recentSearches,rememberSearch,clearSearchHistory,searchSuggestions,lessonSearchResults,lessonShareText)
from lesson_service import searchLessons,getUserLessonState,saveUserLessonState


class LessonLibraryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        p = patch.object(db,'DATABASE_PATH',Path(folder.name)/'test.db')
        p.start()
        self.addCleanup(p.stop)
        db.initializeDatabase()
        self.user = db.createUser('one@example.com','hash','salt','one')
        self.other = db.createUser('two@example.com','hash','salt','two')

    def test_favorites_are_idempotent_private_and_survive_migration(self):
        saveLessonFavorite(self.user,1,True)
        saveLessonFavorite(self.user,1,True)
        self.assertEqual(favoriteLessonIds(self.user),{1})
        self.assertEqual(favoriteLessonIds(self.other),set())
        db.initializeDatabase()
        self.assertEqual(favoriteLessonIds(self.user),{1})
        saveLessonFavorite(self.user,1,False)
        self.assertEqual(favoriteLessonIds(self.user),set())

    def test_invalid_lesson_or_blocked_owner_cannot_write(self):
        for lesson in (True,-1,999,'1'):
            with self.assertRaises(ValueError):
                saveLessonFavorite(self.user,lesson,True)
        with db.openDatabase() as c:
            c.execute('UPDATE users SET isBlocked=1 WHERE userId=?',(self.user,))
        for action in (lambda:saveLessonFavorite(self.user,1,True),lambda:saveLessonNote(self.user,1,'Лично'),
                       lambda:rememberSearch(self.user,'котик')):
            with self.assertRaises(ValueError):action()

    def test_notes_validate_length_are_private_and_empty_save_deletes(self):
        text = 'я'*2000
        saveLessonNote(self.user,1,text)
        self.assertEqual(getLessonNote(self.user,1),text)
        self.assertEqual(getLessonNote(self.other,1),'')
        with self.assertRaises(ValueError):saveLessonNote(self.user,1,text+'я')
        self.assertEqual(getLessonNote(self.user,1),text)
        saveLessonNote(self.user,1,'Изменённая заметка')
        self.assertEqual(getLessonNote(self.user,1),'Изменённая заметка')
        saveLessonNote(self.user,1,'  ')
        self.assertEqual(getLessonNote(self.user,1),'')

    def test_history_is_most_recent_20_deduplicated_and_owner_scoped(self):
        for index in range(25):rememberSearch(self.user,f'запрос {index}')
        self.assertEqual(len(recentSearches(self.user)),20)
        self.assertEqual(recentSearches(self.user)[0],'запрос 24')
        self.assertNotIn('запрос 0',recentSearches(self.user))
        rememberSearch(self.user,'  ЗАПРОС   10  ')
        self.assertEqual(recentSearches(self.user)[0],'ЗАПРОС 10')
        self.assertEqual(len(recentSearches(self.user)),20)
        rememberSearch(self.other,'Дракон')
        clearSearchHistory(self.user)
        self.assertEqual(recentSearches(self.user),[])
        self.assertEqual(recentSearches(self.other),['Дракон'])

    def test_invalid_queries_never_enter_history(self):
        for text in ('','а','я'*121,None):
            with self.assertRaises(ValueError):rememberSearch(self.user,text)
        self.assertEqual(recentSearches(self.user),[])

    def test_suggestions_are_bounded_deduplicated_and_do_not_record_typing(self):
        for i in range(15):rememberSearch(self.user,f'пластилин {i}')
        values = searchSuggestions('пласт',self.user)
        self.assertEqual(len(values),10)
        self.assertEqual(len(set(v.casefold() for v in values)),10)
        before = recentSearches(self.user)
        self.assertEqual(searchSuggestions('к',self.user),[])
        self.assertTrue(searchSuggestions('кот',self.user))
        self.assertEqual(recentSearches(self.user),before)
        self.assertFalse(any(v.startswith('пластилин ') for v in searchSuggestions('пласт',self.other)))

    def test_filters_sorting_and_material_search(self):
        saveLessonFavorite(self.user,2,True)
        favorites = lessonSearchResults(searchLessons(''),'',self.user,favoritesOnly=True)
        self.assertEqual([l['lessonId'] for l in favorites],[2])
        self.assertEqual(lessonSearchResults(searchLessons(''),'',self.other,favoritesOnly=True),[])
        state = getUserLessonState(self.user,1)
        state['checkedMaterials'] = [0]
        saveUserLessonState(self.user,1,state)
        self.assertEqual([l['lessonId'] for l in lessonSearchResults(searchLessons(''),'',self.user,inProgressOnly=True)],[1])
        items = lessonSearchResults(searchLessons(''),'',self.user,sort='По времени')
        self.assertEqual([l['timeMinutes'] for l in items],sorted(l['timeMinutes'] for l in items))
        self.assertEqual([l['lessonId'] for l in searchLessons('желтый')],[l['lessonId'] for l in searchLessons('жёлтый')])

    def test_share_text_does_not_contain_private_notes_or_progress(self):
        saveLessonNote(self.user,1,'PRIVATE_SENTINEL')
        text = lessonShareText(1)
        self.assertIn('Милый котик',text)
        self.assertIn('Материалы:',text)
        self.assertNotIn('PRIVATE_SENTINEL',text)
        self.assertNotIn('sessionToken',text)

    def test_account_deletion_removes_library_without_touching_other_owner(self):
        for user in (self.user,self.other):
            saveLessonFavorite(user,1,True)
            saveLessonNote(user,1,'Личная заметка')
            rememberSearch(user,'котик')
        self.assertTrue(db.deleteUserDataById(self.user))
        with db.openDatabase() as c:
            for table in ('lessonFavorites','lessonNotes','searchHistory'):
                self.assertEqual(c.execute(f'SELECT COUNT(*) FROM {table} WHERE userId=?',(self.user,)).fetchone()[0],0)
        self.assertEqual(favoriteLessonIds(self.other),{1})
        self.assertTrue(getLessonNote(self.other,1))
        self.assertEqual(recentSearches(self.other),['котик'])
