from __future__ import annotations
import json, sys, traceback, tempfile, shutil
from pathlib import Path

if getattr(sys, 'frozen', False):
    ROOT = Path(getattr(sys, '_MEIPASS', Path(sys.executable).resolve().parent))
    OUTPUT_ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent
    OUTPUT_ROOT = ROOT
sys.path.insert(0, str(ROOT))

def backend_tests():
    from core.database import DB
    from core.references import extract_refs
    tmp = Path(tempfile.mkdtemp(prefix='legaldesk_win_backend_'))
    db = DB(tmp/'test.db', ROOT/'data'/'laws', ROOT/'data'/'metadata.json')
    try:
        assert db.rebuild()[:2] == (30, 1233)
        assert not db.validate(), db.validate()[:10]
        for code, num in [('УК','37'), ('УК','64.1'), ('УПК','65-1'), ('ПК','16.1'), ('КоАП','9.1')]:
            assert db.find_ref(code, num), (code, num)
        assert db.find_ref('УПК','65-1.1')
        assert db.find_law_ref('78-ФЗ','12')
        refs = extract_refs('ст. 65-1 УПК, ст. 65-1.1 УПК, ст. 64.1 УК и ст. 9.1 КоАП')
        for pair in [('УПК','65-1'),('УПК','65-1.1'),('УК','64.1'),('КоАП','9.1')]:
            assert pair in refs, (pair, refs)
        aid = db.find_ref('УК','37')[0]
        art = db.article(aid); lid = art[1]
        assert db.toggle_bm(lid, aid) is True
        assert db.pin_bm(lid, aid) is True
        assert db.bookmarks()[0][0:3] == (lid, aid, 1)
        assert db.pin_bm(lid, aid) is False
        db.add_recent(lid, aid)
        assert db.recent(10)[0][0:2] == (lid, aid)
        state=(len(db.bookmarks()),len(db.recent(10)))
        db.rebuild()
        assert (len(db.bookmarks()),len(db.recent(10))) == state
        return {'status':'ok','documents':db.stats()[0],'articles':db.stats()[1]}
    finally:
        db.close(); shutil.rmtree(tmp, ignore_errors=True)

def gui_tests():
    import ui.app as am
    from ui.app import App
    tmp = Path(tempfile.mkdtemp(prefix='legaldesk_win_gui_'))
    old_db, old_settings = am.DB_PATH, am.SETTINGS_PATH
    am.DB_PATH, am.SETTINGS_PATH = tmp/'test.db', tmp/'settings.json'
    app = App(); app.update();
    try:
        app.show_uk(add_history=False); app.update()
        aid = app.db.find_ref('УК','37')[0]
        app.open_article(aid, add_history=False); app.update()
        assert '####' not in app.reader.get('1.0','end')
        # Bookmark + pin + history.
        app.toggle_bookmark(); app.toggle_pin(); app.update()
        assert app.db.bookmarks()[0][2] == 1
        app.show_bookmarks(add_history=False); app.update()
        assert any(iid.startswith('A') for parent in app.tree.get_children('') for iid in app.tree.get_children(parent))
        app.show_recent(add_history=False); app.update()
        assert app.db.recent(10)
        # Definite article numbering checks.
        assert app.db.find_ref('УК','64.1')
        assert app.db.find_ref('УПК','65-1')
        # FSB sections.
        for tab in ['Обзор','Управления','Полномочия','Задержание','Под прикрытием','ОРД / ОРМ','Контроль']:
            app.show_fsb(add_history=False, tab=tab); app.update()
        # Palette application via actual controls.
        app.open_settings(); app.update(); win=app._settings_win
        def walk(w):
            out=[w]
            for c in w.winfo_children(): out.extend(walk(c))
            return out
        emerald=None; apply_btn=None
        for w in walk(win):
            try:
                txt=w.cget('text')
                if txt and 'Emerald' in txt: emerald=w
                if txt == 'Применить': apply_btn=w
            except Exception:
                pass
        assert emerald is not None and apply_btn is not None
        emerald.invoke(); app.update(); apply_btn.invoke(); app.update()
        assert app.theme == 'emerald', app.theme
        assert app.settings.get('theme') == 'emerald'
        # Back/forward after distinct views.
        app.show_uk(add_history=False); app.open_article(aid, add_history=True); app.show_koap(add_history=True); app.update()
        app.go_back(); app.update(); app.go_forward(); app.update()
        return {'status':'ok'}
    finally:
        try: app.destroy()
        except Exception: pass
        am.DB_PATH, am.SETTINGS_PATH = old_db, old_settings
        shutil.rmtree(tmp, ignore_errors=True)

def main():
    result={'platform':sys.platform,'python':sys.version,'frozen':bool(getattr(sys,'frozen',False))}
    try: result['backend']=backend_tests()
    except Exception: result['backend']={'status':'error','traceback':traceback.format_exc()}
    try: result['gui']=gui_tests()
    except Exception: result['gui']={'status':'error','traceback':traceback.format_exc()}
    (OUTPUT_ROOT/'windows_smoke_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['backend']['status']=='ok' and result['gui']['status']=='ok' else 1
if __name__=='__main__': raise SystemExit(main())
