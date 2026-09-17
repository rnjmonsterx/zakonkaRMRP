import os
from pathlib import Path
os.environ.setdefault('PYTHONPATH','.')
from core.database import DB
from core.references import extract_refs
from ui.app import App

def backend():
    root=Path(__file__).resolve().parent
    db=DB(root/'smoke.db',root/'data'/'laws',root/'data'/'metadata.json')
    assert db.rebuild()[0:2]==(30,1233)
    assert db.find_ref('ПК','13.2')
    assert extract_refs('ст. 9.1 КоАП и ст. 37 УК и ст. 65-1 УПК')==[('КоАП','9.1'),('УК','37'),('УПК','65-1')]
    issues=db.validate(); assert not issues, issues[:3]
    assert db.find_ref('УПК','65-1')
    assert db.find_ref('УК','10-1')
    # state preservation
    row=db.code_articles('УК','Преступления')[0]; db.toggle_bm(row[1],row[0]); db.add_recent(row[1],row[0]); db.rebuild(); assert len(db.bookmarks())==1 and len(db.recent())==1
    db.close(); (root/'smoke.db').unlink(missing_ok=True)

def gui():
    app=App(); app.update_idletasks();
    assert hasattr(app,'back_button') and hasattr(app,'forward_button')
    app.show_uk(add_history=False); app.update_idletasks()
    app.show_koap(add_history=False); app.update_idletasks()
    app.show_detention(add_history=False); app.select_detention_step('05'); app.update_idletasks()
    app.show_fsb(add_history=False,tab='Управления',management='М'); app.update_idletasks()
    # open known article and exercise history
    art=app.db.code_articles('УК','Преступления')[0][0]; app.open_article(art,add_history=False); app.update_idletasks()
    assert app.article_id==art
    app.db.close(); app.destroy()

backend(); gui(); print('SMOKE OK')
