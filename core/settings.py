from __future__ import annotations
import copy, json
from pathlib import Path

DEFAULT_SETTINGS={
    'theme':'azure','custom_colors':{},'custom_themes':{},'ui_style':'legal','glow':'low','animations':True,
    'font_scale':1.0,'density':'normal','reader_width':100,'show_preview':True,'show_sanctions':True,
    'show_related':True,'show_article_source':True,'list_mode':'title_preview','preview_chars':110,
    'reader_position':'right','startup':'home','uk_default':'Преступления','koap_default':'Правонарушения',
    'history_limit':50,'link_mode':'history','remember_scroll':True,'confirm_exit':False,'check_on_start':False,
    'open_last':False,'auto_scroll_search':True,'quick_access':['detention','uk','koap','pc','upk','fsb'],
    'quick_order':['detention','uk','koap','pc','upk','fsb','bookmarks'],'developer_mode':False,
    'profiles':{
      'Повседневный':{'theme':'azure','ui_style':'legal','glow':'low','animations':True,'font_scale':1.0,'density':'normal'},
      'Компактный':{'theme':'graphite','ui_style':'minimal','glow':'off','animations':False,'font_scale':0.95,'density':'compact'},
      'Чтение':{'theme':'paper','ui_style':'paper','glow':'off','animations':False,'font_scale':1.15,'density':'large','reader_width':115},
    },
}

def load_settings(path: Path):
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        out=copy.deepcopy(DEFAULT_SETTINGS); out.update(data or {})
        return out
    except Exception:
        return copy.deepcopy(DEFAULT_SETTINGS)

def save_settings(path: Path,data):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(path)
