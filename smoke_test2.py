from pathlib import Path
import tempfile, json
from ui.app import App
from core.settings import load_settings, save_settings, DEFAULT_SETTINGS

def run():
    root=Path(__file__).resolve().parent
    # isolate settings/db by deleting local generated state after run
    settings=root/'settings.json'
    if settings.exists(): settings.unlink()
    app=App(); app.update();
    # base -> uk -> article -> back -> forward
    app.show_uk(); app.update()
    uk=app.db.code_articles('УК','Преступления')[0][0]
    app.open_article(uk); app.update()
    assert app.article_id==uk
    assert app._history, 'history should have a back entry'
    app.go_back(); app.update(); assert app.mode=='code'
    assert app._forward_history, 'forward should be available'
    app.go_forward(); app.update(); assert app.article_id==uk
    # workspace tabs
    ko=app.db.code_articles('УК','Преступления')[1][0]
    app.open_article(ko,add_history=False); app.update()
    assert len(app._workspace)>=2
    # FSB
    app.show_fsb(add_history=False,tab='Управления',management='М'); app.update();
    assert app._fsb_tab=='Управления'
    # settings window exists and can open all tabs
    app.open_settings(); app.update(); win=app._settings_win; assert win and win.winfo_exists()
    # notebook exists
    notebooks=[w for w in win.winfo_children() if 'ttk::notebook' in str(w)]
    win.destroy(); app._settings_win=None
    app.db.close(); app.destroy()
    print('GUI SMOKE 2 OK')

if __name__=='__main__': run()
