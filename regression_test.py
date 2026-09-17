from __future__ import annotations
import ast, collections, json, shutil, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def static_tests():
    for path in [ROOT/'main.py', ROOT/'ui'/'app.py', ROOT/'core'/'database.py', ROOT/'core'/'parser.py', ROOT/'core'/'references.py', ROOT/'core'/'settings.py']:
        tree=ast.parse(path.read_text(encoding='utf8'))
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            names=[n.name for n in cls.body if isinstance(n, ast.FunctionDef)]
            dup=[x for x,c in collections.Counter(names).items() if c>1]
            assert not dup,(path,dup)
    text=(ROOT/'ui'/'app.py').read_text(encoding='utf8')
    for bad in ('show_authority','show_scenarios','show_penalty_search','ORG_DATA','orgbar','penaltybar'):
        assert bad not in text,bad

def backend_tests():
    from core.database import DB
    from core.references import extract_refs
    tmp=Path(tempfile.mkdtemp(prefix='ldreg_'))
    db=DB(tmp/'db.sqlite',ROOT/'data'/'laws',ROOT/'data'/'metadata.json')
    try:
        stats=db.rebuild(); assert stats[:2]==(30,1233),stats
        assert not db.validate(), db.validate()[:10]
        for code,num in [('УК','37'),('УК','64.1'),('УПК','65-1'),('ПК','16.1'),('КоАП','9.1')]:
            assert db.find_ref(code,num),(code,num)
        # Hyphenated article families are structural: 65-1 is an article, 65-1.1 is a part.
        assert db.find_ref('УПК','65-1') is not None
        assert db.find_ref('УПК','65-1.1') is not None
        assert db.find_law_ref('78-ФЗ','12') is not None
        # Plain bold article headings used by the local СМИ source must keep content attached.
        media_path=ROOT/'data'/'laws'/'22.md'
        from core.parser import parse_document
        media=[a for c in parse_document(media_path.read_text(encoding='utf8',errors='replace')) for a in c['articles']]
        m11=next(a for a in media if a['title'].startswith('Статья 1.1.'))
        m21=next(a for a in media if a['title'].startswith('Статья 2.1.'))
        m221=next(a for a in media if a['title'].startswith('Статья 2.2.1.'))
        assert m11['body'] and 'В Российской Федерации' in m11['body']
        assert m21['body'] and 'Цензура массовой информации' in m21['body']
        # 2.2.1 has the substantive text on its heading line in the source; do not report it as empty.
        assert (m221['body'] or len(m221['title']) > 20)
        # Markdown heading markers must not leak into parsed article bodies.
        assert all('####' not in a['body'] for a in media)
        assert db.find_law_ref('федеральной службе безопасности','12') is not None
        refs=extract_refs('ст. 65-1 УПК, ст. 65-1.1 УПК, ст. 64.1 УК, ст. 9.1 КоАП, статьями 37–49 Уголовного Кодекса')
        for pair in [('УПК','65-1'),('УПК','65-1.1'),('УК','64.1'),('КоАП','9.1'),('УК','37'),('УК','49')]:
            assert pair in refs,(pair,refs)
        row=db.find_ref('УК','37'); aid=row[0]; art=db.article(aid); lid=art[1]
        assert db.toggle_bm(lid,aid) is True
        assert db.pin_bm(lid,aid) is True
        bm=db.bookmarks(); assert bm and bm[0][0:3]==(lid,aid,1),bm[:1]
        assert db.pin_bm(lid,aid) is False
        rec_before= int(time.time())
        db.add_recent(lid,aid)
        rec=db.recent(10); assert rec and rec[0][0:2]==(lid,aid) and isinstance(rec[0][4],int),rec[:1]
        assert len(db.recent(10))==1
        state=(len(db.bookmarks()),len(db.recent(10)))
        db.rebuild(); assert (len(db.bookmarks()),len(db.recent(10)))==state
        # Article heading structure: standalone dotted/hyphenated article must stay discoverable.
        assert db.code_articles('УК','Преступления')
        return {'documents':stats[0],'articles':stats[1],'status':'ok'}
    finally:
        db.close(); shutil.rmtree(tmp,ignore_errors=True)

def gui_tests():
    import ui.app as am
    from ui.app import App
    tmp=Path(tempfile.mkdtemp(prefix='ldgui_'))
    old_db,old_settings=am.DB_PATH,am.SETTINGS_PATH
    am.DB_PATH=tmp/'db.sqlite'; am.SETTINGS_PATH=tmp/'settings.json'
    app=App(); app.update();
    try:
        app.show_uk(add_history=False); app.update()
        aid=app.db.find_ref('УК','37')[0]
        app.open_article(aid,add_history=False); app.update()
        assert '####' not in app.reader.get('1.0','end')
        # Bookmark UI
        app.toggle_bookmark(); app.update(); app.toggle_pin(); app.update()
        app.show_bookmarks(add_history=False); app.update()
        roots=list(app.tree.get_children('')); nested=[c for r in roots for c in app.tree.get_children(r)]
        assert f'A{aid}' in roots+nested
        app.show_recent(add_history=False); app.update(); assert f'A{aid}' in list(app.tree.get_children(''))
        # FSB tiles / sections
        for tab in ['Обзор','Управления','Полномочия','Задержание','Под прикрытием','ОРД / ОРМ','Контроль']:
            app.show_fsb(add_history=False,tab=tab); app.update()
        # History back/forward: create distinct states.
        app.show_uk(add_history=False); app.open_article(aid,add_history=True); app.show_koap(add_history=True); app.update()
        app.go_back(); app.update(); assert app.mode in ('article','code')
        app.go_forward(); app.update(); assert app.mode in ('article','code')
        # Escape in settings must not also trigger global reset.
        app.show_uk(add_history=False); app.open_settings(); app.update(); win=app._settings_win
        app._close_settings_window(win); app.update(); assert app._settings_win is None
        return {'status':'ok'}
    finally:
        try: app.destroy()
        except Exception: pass
        am.DB_PATH,am.SETTINGS_PATH=old_db,old_settings
        shutil.rmtree(tmp,ignore_errors=True)

if __name__=='__main__':
    static_tests(); b=backend_tests(); print('BACKEND',b)
    g=gui_tests(); print('GUI',g)
    print('REGRESSION OK')
