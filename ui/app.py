from __future__ import annotations
import copy, json, os, re, time, sqlite3, sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox, colorchooser
from tkinter.scrolledtext import ScrolledText

from core.parser import clean_md, normalize
from core.references import extract_refs
from core.database import DB
from core.settings import DEFAULT_SETTINGS, load_settings, save_settings
from ui.theme import PALETTES, PALETTE_LABELS
from ui.widgets import ToolTip

APP="Юридический помощник"
if getattr(sys,"frozen",False):
    BASE=Path(sys.executable).resolve().parent
    RESOURCE_BASE=Path(getattr(sys,"_MEIPASS",BASE))
else:
    BASE=Path(__file__).resolve().parents[1]
    RESOURCE_BASE=BASE
DATA=RESOURCE_BASE/"data"/"laws"
META=RESOURCE_BASE/"data"/"metadata.json"
DB_PATH=BASE/"legal_desk.db"
SETTINGS_PATH=BASE/"settings.json"
BACKUPS=BASE/"backups"
BG="#070b11"; SIDE="#0c121b"; PANEL="#101822"; FIELD="#111c2b"; READER="#0b0f17"; TEXT="#eef4fa"; MUTED="#7f8fa2"; BORDER="#213048"; ACCENT="#68b8ff"; GREEN="#35dfbb"; GOLD="#e2bc66"; SELECT="#19496d"; RED="#ef606d"

class App(tk.Tk):
    PALETTES = PALETTES
    PALETTE_LABELS = PALETTE_LABELS
    FSB_MANAGEMENTS = [('М', 'Управление «М»', 'Первая оперативно-следственная служба: следствие, инспекции, антикоррупционная работа.', 18, 20), ('К', 'Управление «К»', 'Вторая оперативно-следственная служба: наркотики, оружие, контрабанда, внедрения и следствие.', 23, 25), ('А', 'Управление «А»', 'Защита конституционного строя, терроризм, экстремизм и силовое сопровождение специальных операций.', 26, 27), ('О', 'Управление «О»', 'Организационно-кадровая работа и Академия ФСБ.', None, 28), ('АПС', 'Пятая служба', 'Прикомандирование сотрудников к государственным организациям, наблюдение и контроль.', 29, 31)]
    FSB_DETENTION_LISTS = {'Общее': ('Общий перечень по ПК 13.2', ['37', '38', '39', '40', '41', '42', '43', '44', '45', '46', '47', '48', '49', '54', '56', '57', '58', '59', '60', '61', '62', '63', '64', '65', '66', '67', '68', '70', '86', '87', '89', '90', '91', '92', '93', '94', '95', '96', '97', '98'], 'ПК 13.2'), 'М': ('Управление «М» · специальный перечень', ['37', '38', '39', '40', '41', '46', '47', '53', '55', '63', '64', '67', '69', '70', '71', '72', '73', '74', '75', '77', '78', '79', '80', '81', '87', '89', '90', '93', '94'], 'ПК 16.1'), 'К': ('Управление «К» · специальный перечень', ['37', '38', '39', '63', '64', '64-1', '89', '90'], 'ПК 16.2'), 'Передача в ФСБ': ('Составы, по которым задержание передаётся сотрудникам ФСБ', ['53', '55', '72', '73', '74', '75', '78'], 'ПК 13.3')}
    FSB_ORM = [('01', 'Опрос', 'сбор фактической информации со слов опрашиваемого лица'), ('02', 'Наведение справок', 'официальные запросы в органы государственной власти'), ('03', 'Сбор образцов', 'сбор образцов для дальнейших исследований'), ('04', 'Контрольная закупка / контролируемая поставка', 'разрешены для управлений «К» и «М» ФСБ и СК'), ('05', 'Исследование предметов и документов', 'изучение объектов, связанных со следами или результатами преступной деятельности'), ('06', 'Скрытое наблюдение', 'наружное и внутреннее'), ('07', 'Установление личности', 'установление личности лица'), ('08', 'Обследование', 'помещения, здания, сооружения, участок местности и транспорт'), ('09', 'Контроль почтовых отправлений и иных сообщений', 'контроль сообщений'), ('10', 'Прослушивание телефонных переговоров', 'получение и фиксация переговоров'), ('11', 'Снятие информации с технических каналов связи', 'получение и фиксация сигналов'), ('12', 'Оперативное внедрение', 'оперативное внедрение'), ('13', 'Получение компьютерной информации / записи с камер', 'копирование или изъятие электронных сведений'), ('14', 'Предупреждение и пресечение коррупции', 'разрешено для управления «М» ФСБ и СК')]

    def __init__(self):
        super().__init__()
        self.title('Юридический помощник')
        self.geometry('1540x900')
        self.minsize(1180, 720)
        self.protocol('WM_DELETE_WINDOW', self._on_close)
        self.settings = load_settings(SETTINGS_PATH)
        self.theme = self.settings.get('theme', 'neon')
        self.font_scale = float(self.settings.get('font_scale', 1.0) or 1.0)
        self.mode = 'home'
        self.code = None
        self.law_id = None
        self.article_id = None
        self._last_view = None
        self._history = []
        self._forward_history = []
        self._workspace = {}
        self._restoring = False
        self._middle_widget = None
        self._middle_y = 0
        self._middle_active = False
        self._search_job = None
        self._read_mode = False
        self._reader_scroll = {}
        self._tree_lock = False
        self._detention_tab = 'Порядок'
        self.db = DB(DB_PATH, DATA, META)
        self.db.rebuild()
        self.build()
        if self.settings.get('check_on_start'):
            self.after(250, self.validate_database)
        self.after_idle(lambda: self._start_view())

    def _on_close(self):
        if self.settings.get('confirm_exit'):
            if not messagebox.askyesno('Выход', 'Закрыть «Юридический помощник»?', parent=self):
                return
        self.destroy()

    def _font(self, size, semibold=False):
        return ('Segoe UI Semibold' if semibold else 'Segoe UI', max(7, int(round(size * self.font_scale))))

    def _start_view(self):
        if self.settings.get('open_last'):
            try:
                rows = self.db.recent(1)
                if rows:
                    self.open_article(rows[0][1], add_history=False)
                    return
            except Exception:
                pass
        start = self.settings.get('startup', 'home')
        mapping = {'home': lambda: self.show_home(add_history=False), 'detention': lambda: self.show_detention(add_history=False), 'uk': lambda: self.show_uk(), 'koap': lambda: self.show_koap(), 'fsb': lambda: self.show_fsb(add_history=False), 'bookmarks': lambda: self.show_bookmarks(add_history=False), 'recent': lambda: self.show_recent(add_history=False)}
        mapping.get(start, mapping['home'])()

    def _apply_reader_options(self):
        if not hasattr(self, 'reader'):
            return
        try:
            self.reader.tag_configure('head', font=self._font(15, True))
            self.reader.tag_configure('subhead', font=self._font(10, True))
            self.reader.tag_configure('body', font=self._font(10), spacing3=5)
            self.reader.tag_configure('measure', font=self._font(10, True), spacing1=4, spacing3=5)
            self.reader.tag_configure('measure_label', font=self._font(8, True))
            self.reader.configure(padx=max(12, int(24 * self.settings.get('reader_width', 100) / 100)))
        except Exception:
            pass

    def _settings_color(self, key, current, parent):
        chosen = colorchooser.askcolor(color=current, parent=parent, title='Выберите цвет')[1]
        if chosen:
            self._pending_colors[key] = chosen
            return chosen
        return current

    def _profile_payload(self, values):
        return {'theme': values.get('theme', 'azure'), 'ui_style': values.get('ui_style', 'legal'), 'glow': values.get('glow', 'low'), 'animations': values.get('animations', True), 'font_scale': float(values.get('font_scale', 1.0)), 'density': values.get('density', 'normal'), 'reader_width': int(values.get('reader_width', 100)), 'custom_colors': dict(values.get('custom_colors') or {})}

    def _rebuild_after_settings(self, close_window=True, reopen=False, tab_index=0):
        state = (self.mode, self.code, self.law_id, self.article_id)
        for w in list(self.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass
        self.apply_palette()
        self.build()
        mode, code, law, article = state
        try:
            if mode == 'article' and article:
                self.open_article(article, add_history=False)
            elif mode == 'detention':
                self.show_detention(add_history=False)
            elif mode == 'fsb':
                self.show_fsb(add_history=False)
            elif mode == 'bookmarks':
                self.show_bookmarks(add_history=False)
            elif mode == 'recent':
                self.show_recent(add_history=False)
            elif code == 'УК':
                self.show_uk(add_history=False)
            elif code == 'КоАП':
                self.show_koap(add_history=False)
            else:
                self.show_home(add_history=False)
        except Exception:
            self.show_home(add_history=False)
        if close_window and getattr(self, '_settings_win', None) is not None:
            try:
                self._settings_win.destroy()
            except Exception:
                pass
            self._settings_win = None
        if reopen:
            self.after(80, lambda: self.open_settings(tab_index=tab_index))

    def open_settings(self, tab_index=0):
        if getattr(self, '_settings_win', None) is not None and self._settings_win.winfo_exists():
            self._settings_win.lift()
            self._settings_win.focus_force()
            return
        win = tk.Toplevel(self)
        self._settings_win = win
        win.title('Настройки · Юридический помощник')
        win.geometry('1050x780')
        win.minsize(920, 650)
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        st = ttk.Style(win)
        try:
            st.theme_use('clam')
        except Exception:
            pass
        st.configure('Settings.TNotebook', background=BG, borderwidth=0)
        st.configure('Settings.TNotebook.Tab', background=PANEL, foreground=TEXT, padding=(14, 8), font=self._font(9, True), borderwidth=0)
        st.map('Settings.TNotebook.Tab', background=[('selected', SELECT)], foreground=[('selected', TEXT)])
        st.configure('Settings.TCombobox', fieldbackground=FIELD, background=PANEL, foreground=TEXT, arrowcolor=ACCENT, padding=(4, 3))
        st.map('Settings.TCombobox', fieldbackground=[('readonly', FIELD)], foreground=[('readonly', TEXT)])
        st.configure('Settings.TButton', background=PANEL, foreground=TEXT, padding=(12, 7), borderwidth=0, font=self._font(9, True))
        st.map('Settings.TButton', background=[('active', FIELD)])
        st.configure('Settings.Accent.TButton', background=ACCENT, foreground='#07131c', padding=(14, 7), borderwidth=0, font=self._font(9, True))
        st.map('Settings.Accent.TButton', background=[('active', ACCENT)])
        outer = tk.Frame(win, bg=BG)
        outer.pack(fill='both', expand=True, padx=18, pady=14)
        head = tk.Frame(outer, bg=BG)
        head.pack(fill='x', pady=(0, 8))
        tk.Label(head, text='Настройки', bg=BG, fg=TEXT, font=self._font(20, True)).pack(anchor='w')
        tk.Label(head, text='Персонализация интерфейса, чтения и рабочего режима', bg=BG, fg=MUTED, font=self._font(9)).pack(anchor='w', pady=(2, 0))
        pages = {}
        nb = ttk.Notebook(outer, style='Settings.TNotebook')
        nb.pack(fill='both', expand=True)

        def page(name):
            tab = tk.Frame(nb, bg=BG)
            nb.add(tab, text=name)
            pages[name] = tab
            canvas = tk.Canvas(tab, bg=BG, highlightthickness=0, bd=0)
            scroll = tk.Scrollbar(tab, orient='vertical', command=canvas.yview, bg=FIELD, activebackground=SELECT, troughcolor=BG, highlightthickness=0, bd=0)
            canvas.configure(yscrollcommand=scroll.set)
            canvas.pack(side='left', fill='both', expand=True)
            scroll.pack(side='right', fill='y')
            inner = tk.Frame(canvas, bg=BG)
            wid = canvas.create_window((0, 0), window=inner, anchor='nw')
            inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
            canvas.bind('<Configure>', lambda e: canvas.itemconfigure(wid, width=e.width))

            def wheel(e):
                try:
                    canvas.yview_scroll(int(-1 * (e.delta / 120)), 'units')
                except Exception:
                    pass
            canvas.bind('<MouseWheel>', wheel, add='+')
            inner.bind('<MouseWheel>', wheel, add='+')
            return inner

        def section(parent, title, subtitle=None):
            box = tk.Frame(parent, bg=PANEL)
            box.pack(fill='x', pady=(0, 8))
            tk.Label(box, text=title, bg=PANEL, fg=ACCENT, font=self._font(10, True)).pack(anchor='w', padx=12, pady=(10, 2))
            if subtitle:
                tk.Label(box, text=subtitle, bg=PANEL, fg=MUTED, font=self._font(8), wraplength=880, justify='left').pack(anchor='w', padx=12, pady=(0, 9))
            return box

        def combo(box, label, var, vals, width=22):
            r = tk.Frame(box, bg=PANEL)
            r.pack(fill='x', padx=12, pady=5)
            tk.Label(r, text=label, bg=PANEL, fg=TEXT, font=self._font(9, True)).pack(side='left')
            w = tk.OptionMenu(r, var, *vals)
            w.configure(bg=FIELD, fg=TEXT, activebackground=SELECT, activeforeground=TEXT, highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT, relief='flat', bd=0, padx=8, pady=4, width=width // 2, font=self._font(8, True))
            try:
                w['menu'].configure(bg=FIELD, fg=TEXT, activebackground=SELECT, activeforeground=TEXT, bd=0, font=self._font(8))
            except Exception:
                pass
            w.pack(side='right')
            return w

        def check(box, var, label, note=None):
            r = tk.Frame(box, bg=PANEL)
            r.pack(fill='x', padx=12, pady=4)
            tk.Checkbutton(r, text=label, variable=var, bg=PANEL, fg=TEXT, selectcolor=FIELD, activebackground=PANEL, activeforeground=TEXT, highlightthickness=0, bd=0, font=self._font(9, True)).pack(anchor='w')
            if note:
                tk.Label(r, text=note, bg=PANEL, fg=MUTED, font=self._font(8), wraplength=880, justify='left').pack(anchor='w', padx=28, pady=(0, 3))
        vars = {}
        self._pending_colors = dict(self.settings.get('custom_colors') or {})
        p = page('Внешний вид')
        b = section(p, 'Готовые палитры', 'Выберите палитру, затем нажмите «Применить». Никаких скрытых применений.')
        themes = [('azure', 'Azure'), ('graphite', 'Graphite'), ('emerald', 'Emerald'), ('violet', 'Violet'), ('amber', 'Amber'), ('crimson', 'Crimson'), ('cyan', 'Cyan'), ('midnight', 'Midnight'), ('paper', 'Paper Dark'), ('custom', 'Своя тема')]
        theme_var = tk.StringVar(value=self.theme if self.theme in PALETTE_LABELS else 'azure')
        vars['theme'] = theme_var
        preview_box = tk.Frame(b, bg=FIELD, highlightthickness=1, highlightbackground=BORDER)
        preview_box.pack(fill='x', padx=12, pady=(2, 10))
        preview_title = tk.Label(preview_box, text='Статья 37. Убийство', bg=FIELD, fg=TEXT, font=self._font(10, True))
        preview_title.pack(anchor='w', padx=10, pady=(8, 2))
        preview_text = tk.Label(preview_box, text='Краткий фрагмент статьи…', bg=FIELD, fg=MUTED, font=self._font(8))
        preview_text.pack(anchor='w', padx=10)
        preview_measure = tk.Label(preview_box, text='Наказание: 7 лет', bg=FIELD, fg=GREEN, font=self._font(9, True))
        preview_measure.pack(anchor='w', padx=10, pady=(4, 8))
        grid = tk.Frame(b, bg=PANEL)
        grid.pack(fill='x', padx=12, pady=(0, 10))
        palette_buttons = {}

        def refresh_theme_preview():
            k = theme_var.get()
            pal = PALETTES.get(k, PALETTES['azure']).copy()
            if k == 'custom':
                pal.update(self._pending_colors)
            for w in (preview_box,):
                w.configure(bg=pal['FIELD'])
            preview_title.configure(bg=pal['FIELD'], fg=pal['TEXT'])
            preview_text.configure(bg=pal['FIELD'], fg=pal['MUTED'])
            preview_measure.configure(bg=pal['FIELD'], fg=pal['GREEN'])
            for key, btn in palette_buttons.items():
                active = key == k
                btn.configure(bg=pal.get('PANEL', PANEL) if active else PANEL, fg=pal.get('TEXT', TEXT))
                if active:
                    btn.configure(highlightthickness=2, highlightbackground=pal.get('ACCENT', ACCENT))
                else:
                    btn.configure(highlightthickness=0)

        def choose_theme(k):
            theme_var.set(k)
            refresh_theme_preview()
        for i, (k, lbl) in enumerate(themes):
            col = PALETTES.get(k, PALETTES['azure'])['ACCENT'] if k != 'custom' else self._pending_colors.get('ACCENT', ACCENT)
            btn = tk.Button(grid, text='■  ' + lbl, bg=PANEL, fg=TEXT, activebackground=FIELD, activeforeground=TEXT, relief='flat', bd=0, font=self._font(8, True), anchor='w', padx=8, pady=5, command=lambda kk=k: choose_theme(kk))
            btn.grid(row=i // 2, column=i % 2, sticky='ew', padx=(0 if i % 2 == 0 else 6, 6), pady=3)
            palette_buttons[k] = btn
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        apply_theme_btn = tk.Button(b, text='Применить выбранную палитру', bg=ACCENT, fg='#07131c', activebackground=ACCENT, relief='flat', bd=0, font=self._font(9, True), padx=12, pady=7, command=lambda: apply_changes(False))
        apply_theme_btn.pack(anchor='e', padx=12, pady=(0, 10))
        b = section(p, 'Стиль интерфейса')
        vars['ui_style_label'] = tk.StringVar(value={'minimal': 'Минималистичный', 'legal': 'Legal Tech', 'neon': 'Neon', 'monochrome': 'Монохромный', 'paper': 'Paper Dark'}.get(self.settings.get('ui_style', 'legal'), 'Legal Tech'))
        combo(b, 'Стиль', vars['ui_style_label'], ['Минималистичный', 'Legal Tech', 'Neon', 'Монохромный', 'Paper Dark'])
        b = section(p, 'Эффекты')
        vars['glow'] = tk.StringVar(value={'off': 'Выкл.', 'low': 'Слабое', 'medium': 'Среднее', 'high': 'Сильное'}.get(self.settings.get('glow', 'low'), 'Слабое'))
        combo(b, 'Свечение', vars['glow'], ['Выкл.', 'Слабое', 'Среднее', 'Сильное'])
        vars['animations'] = tk.BooleanVar(value=bool(self.settings.get('animations', True)))
        check(b, vars['animations'], 'Анимации', 'Отключите для максимально статичного интерфейса.')
        b = section(p, 'Размер и плотность')
        vars['font_scale'] = tk.DoubleVar(value=float(self.settings.get('font_scale', 1.0)))
        tk.Scale(b, from_=0.85, to=1.4, resolution=0.05, orient='horizontal', length=480, variable=vars['font_scale'], showvalue=True, bg=PANEL, fg=TEXT, troughcolor=FIELD, activebackground=ACCENT, highlightthickness=0, bd=0).pack(anchor='e', padx=12, pady=4)
        vars['density_label'] = tk.StringVar(value={'compact': 'Компактная', 'normal': 'Обычная', 'large': 'Увеличенная'}.get(self.settings.get('density', 'normal'), 'Обычная'))
        combo(b, 'Плотность', vars['density_label'], ['Компактная', 'Обычная', 'Увеличенная'])
        p = page('Цвета')
        b = section(p, 'Своя тема', 'Выберите любой базовый цвет. После выбора нажмите «Применить». ')
        color_keys = [('BG', 'Фон'), ('SIDE', 'Боковая панель'), ('PANEL', 'Панели'), ('FIELD', 'Поля'), ('TEXT', 'Текст'), ('MUTED', 'Вторичный текст'), ('ACCENT', 'Акцент'), ('GREEN', 'Дополнительный акцент'), ('SELECT', 'Выделение'), ('BORDER', 'Границы')]
        swatches = {}
        for key, label in color_keys:
            r = tk.Frame(b, bg=PANEL)
            r.pack(fill='x', padx=12, pady=2)
            tk.Label(r, text=label, bg=PANEL, fg=TEXT, font=self._font(8, True)).pack(side='left')
            c = self._pending_colors.get(key, self.palette().get(key, ACCENT))
            btn = tk.Button(r, text=c, bg=c, fg=TEXT, activebackground=c, relief='flat', bd=0, width=12, font=self._font(8, True))
            btn.pack(side='right')
            swatches[key] = btn

        def refresh_swatches():
            for k, btn in swatches.items():
                c = self._pending_colors.get(k, self.palette().get(k, ACCENT))
                btn.configure(text=c, bg=c, activebackground=c)
        for k, btn in swatches.items():
            btn.configure(command=lambda kk=k, bb=btn: self._choose_settings_color(kk, bb, win, theme_var, swatches))

        def apply_custom_colors():
            theme_var.set('custom')
            apply_changes(False)
        tk.Button(b, text='Применить свою палитру', bg=ACCENT, fg='#07131c', activebackground=ACCENT, relief='flat', bd=0, font=self._font(9, True), padx=12, pady=7, command=apply_custom_colors).pack(anchor='e', padx=12, pady=10)
        b2 = section(p, 'Сохранённые палитры')
        saved_list = tk.Listbox(b2, bg=FIELD, fg=TEXT, selectbackground=SELECT, selectforeground=TEXT, relief='flat', height=5, font=self._font(9))
        saved_list.pack(fill='x', padx=12, pady=6)
        for nm in self.settings.get('custom_themes', {}):
            saved_list.insert('end', nm)
        sr = tk.Frame(b2, bg=PANEL)
        sr.pack(fill='x', padx=12, pady=(0, 10))

        def apply_saved_theme():
            sel = saved_list.curselection()
            if not sel:
                return
            nm = saved_list.get(sel[0])
            self._pending_colors = dict(self.settings.get('custom_themes', {}).get(nm, {}))
            theme_var.set('custom')
            refresh_swatches()
            refresh_theme_preview()

        def save_saved_theme():
            nm = simpledialog.askstring('Сохранить тему', 'Название палитры:', parent=win)
            if not nm:
                return
            self.settings.setdefault('custom_themes', {})[nm] = dict(self._pending_colors)
            save_settings(SETTINGS_PATH, self.settings)
            saved_list.delete(0, 'end')
            for n in self.settings['custom_themes']:
                saved_list.insert('end', n)

        def delete_saved_theme():
            sel = saved_list.curselection()
            if not sel:
                return
            nm = saved_list.get(sel[0])
            self.settings.get('custom_themes', {}).pop(nm, None)
            save_settings(SETTINGS_PATH, self.settings)
            saved_list.delete(sel[0])
        for txt, fn in [('Применить выбранную', apply_saved_theme), ('Сохранить как…', save_saved_theme), ('Удалить', delete_saved_theme)]:
            ttk.Button(sr, text=txt, style='Settings.TButton', command=fn).pack(side='left', padx=(0, 6))
        p = page('Чтение')
        b = section(p, 'Список статей', 'Краткое представление в центральном списке. Полный текст открывается справа.')
        vars['list_mode'] = tk.StringVar(value={'title_only': 'Только название', 'title_preview': 'Название + описание'}.get(self.settings.get('list_mode', 'title_preview'), 'Название + описание'))
        combo(b, 'Формат списка', vars['list_mode'], ['Только название', 'Название + описание'])
        vars['preview_chars'] = tk.IntVar(value=int(self.settings.get('preview_chars', 110)))
        tk.Scale(b, from_=60, to=180, resolution=10, orient='horizontal', length=480, variable=vars['preview_chars'], showvalue=True, bg=PANEL, fg=TEXT, troughcolor=FIELD, activebackground=ACCENT, highlightthickness=0, bd=0).pack(anchor='e', padx=12, pady=4)
        for k, label in [('show_preview', 'Показывать краткое описание'), ('show_sanctions', 'Выделять меры наказания'), ('show_related', 'Показывать связанные нормы'), ('show_article_source', 'Показывать источник статьи')]:
            vars[k] = tk.BooleanVar(value=bool(self.settings.get(k, True)))
            check(b, vars[k], label)
        b = section(p, 'Правая панель')
        vars['reader_width'] = tk.IntVar(value=int(self.settings.get('reader_width', 100)))
        tk.Scale(b, from_=70, to=130, resolution=5, orient='horizontal', length=480, variable=vars['reader_width'], showvalue=True, bg=PANEL, fg=TEXT, troughcolor=FIELD, activebackground=ACCENT, highlightthickness=0, bd=0).pack(anchor='e', padx=12, pady=4)
        vars['reader_position'] = tk.StringVar(value={'right': 'Справа', 'center': 'По центру'}.get(self.settings.get('reader_position', 'right'), 'Справа'))
        combo(b, 'Положение статьи', vars['reader_position'], ['Справа', 'По центру'])
        vars['remember_scroll'] = tk.BooleanVar(value=bool(self.settings.get('remember_scroll', True)))
        check(b, vars['remember_scroll'], 'Запоминать положение прокрутки')
        b = section(p, 'Поиск')
        vars['auto_scroll_search'] = tk.BooleanVar(value=bool(self.settings.get('auto_scroll_search', True)))
        check(b, vars['auto_scroll_search'], 'Автоматически прокручивать к найденному тексту')
        p = page('Навигация')
        b = section(p, 'Старт')
        startvals = [('home', 'Главная'), ('detention', 'Порядок задержания'), ('uk', 'УК'), ('koap', 'КоАП'), ('fsb', 'ФСБ'), ('bookmarks', 'Закладки'), ('recent', 'История')]
        vars['startup'] = tk.StringVar(value=dict(startvals).get(self.settings.get('startup', 'home'), 'Главная'))
        combo(b, 'Экран при запуске', vars['startup'], [x[1] for x in startvals], 26)
        vars['uk_default'] = tk.StringVar(value=self.settings.get('uk_default', 'Преступления'))
        combo(b, 'Стартовый режим УК', vars['uk_default'], ['Преступления', 'Общая часть', 'Все'])
        vars['koap_default'] = tk.StringVar(value=self.settings.get('koap_default', 'Правонарушения'))
        combo(b, 'Стартовый режим КоАП', vars['koap_default'], ['Правонарушения', 'ПДД', 'Общая часть', 'Все'])
        b = section(p, 'История и переходы')
        vars['link_mode'] = tk.StringVar(value='Сохранять историю' if self.settings.get('link_mode', 'history') == 'history' else 'Без записи в историю')
        combo(b, 'Переходы по ссылкам', vars['link_mode'], ['Сохранять историю', 'Без записи в историю'], 26)
        vars['history_limit'] = tk.StringVar(value=str(self.settings.get('history_limit', 50)))
        combo(b, 'Размер истории', vars['history_limit'], ['20', '50', '100'])
        vars['open_last'] = tk.BooleanVar(value=bool(self.settings.get('open_last', False)))
        check(b, vars['open_last'], 'Открывать последнее место при запуске')
        vars['confirm_exit'] = tk.BooleanVar(value=bool(self.settings.get('confirm_exit', False)))
        check(b, vars['confirm_exit'], 'Подтверждать выход')
        b = section(p, 'Удобство')
        vars['save_scroll_global'] = tk.BooleanVar(value=bool(self.settings.get('remember_scroll', True)))
        check(b, vars['save_scroll_global'], 'Сохранять положение в статье при возврате')
        p = page('Быстрый доступ')
        b = section(p, 'Панель быстрых кнопок', 'Кнопки располагаются под глобальным поиском.')
        qopts = [('detention', 'Порядок задержания'), ('uk', 'УК'), ('koap', 'КоАП'), ('pc', 'ПК'), ('upk', 'УПК'), ('fsb', 'ФСБ'), ('bookmarks', 'Закладки')]
        selected = set(self.settings.get('quick_access', []))
        qvars = {}
        order = list(self.settings.get('quick_order', []))
        order += [k for k, _ in qopts if k not in order]
        order = order[:len(qopts)]
        for k, lbl in qopts:
            qvars[k] = tk.BooleanVar(value=k in selected)
            check(b, qvars[k], lbl)
        b2 = section(p, 'Порядок кнопок')
        lb = tk.Listbox(b2, bg=FIELD, fg=TEXT, selectbackground=SELECT, selectforeground=TEXT, relief='flat', height=7, font=self._font(9))
        lb.pack(fill='x', padx=12, pady=6)
        labels = dict(qopts)
        for k in order:
            lb.insert('end', labels.get(k, k))

        def move(delta):
            sel = lb.curselection()
            if not sel:
                return
            i = sel[0]
            j = i + delta
            if not 0 <= j < lb.size():
                return
            val = lb.get(i)
            lb.delete(i)
            lb.insert(j, val)
            lb.selection_set(j)
        mr = tk.Frame(b2, bg=PANEL)
        mr.pack(fill='x', padx=12, pady=(0, 8))
        ttk.Button(mr, text='↑', style='Settings.TButton', command=lambda: move(-1)).pack(side='left', padx=(0, 4))
        ttk.Button(mr, text='↓', style='Settings.TButton', command=lambda: move(1)).pack(side='left')
        p = page('Профили')
        b = section(p, 'Рабочие профили', 'Профили сохраняют настройки интерфейса и чтения.')
        lbp = tk.Listbox(b, bg=FIELD, fg=TEXT, selectbackground=SELECT, selectforeground=TEXT, relief='flat', height=7, font=self._font(9))
        lbp.pack(fill='x', padx=12, pady=6)
        for name in self.settings.get('profiles', {}):
            lbp.insert('end', name)
        pr = tk.Frame(b, bg=PANEL)
        pr.pack(fill='x', padx=12, pady=(0, 10))

        def collect_profile():
            return {'theme': theme_var.get(), 'ui_style': {'Минималистичный': 'minimal', 'Legal Tech': 'legal', 'Neon': 'neon', 'Монохромный': 'monochrome', 'Paper Dark': 'paper'}.get(vars['ui_style_label'].get(), 'legal'), 'glow': {'Выкл.': 'off', 'Слабое': 'low', 'Среднее': 'medium', 'Сильное': 'high'}.get(vars['glow'].get(), 'low'), 'animations': vars['animations'].get(), 'font_scale': vars['font_scale'].get(), 'density': {'Компактная': 'compact', 'Обычная': 'normal', 'Увеличенная': 'large'}.get(vars['density_label'].get(), 'normal'), 'reader_width': vars['reader_width'].get(), 'custom_colors': dict(self._pending_colors)}

        def apply_profile():
            sel = lbp.curselection()
            if not sel:
                return
            name = lbp.get(sel[0])
            data = self.settings.get('profiles', {}).get(name, {})
            theme_var.set(data.get('theme', theme_var.get()))
            self._pending_colors = dict(data.get('custom_colors') or self._pending_colors)
            if 'ui_style' in data:
                vars['ui_style_label'].set({'minimal': 'Минималистичный', 'legal': 'Legal Tech', 'neon': 'Neon', 'monochrome': 'Монохромный', 'paper': 'Paper Dark'}.get(data['ui_style'], 'Legal Tech'))
            if 'glow' in data:
                vars['glow'].set({'off': 'Выкл.', 'low': 'Слабое', 'medium': 'Среднее', 'high': 'Сильное'}.get(data['glow'], 'Слабое'))
            if 'density' in data:
                vars['density_label'].set({'compact': 'Компактная', 'normal': 'Обычная', 'large': 'Увеличенная'}.get(data['density'], 'Обычная'))
            for k in ('animations', 'font_scale', 'reader_width'):
                if k in data:
                    vars[k].set(data[k])
            apply_changes(False)

        def save_profile():
            nm = simpledialog.askstring('Сохранить профиль', 'Название профиля:', parent=win)
            if not nm:
                return
            self.settings.setdefault('profiles', {})[nm] = collect_profile()
            save_settings(SETTINGS_PATH, self.settings)
            lbp.delete(0, 'end')
            for n in self.settings['profiles']:
                lbp.insert('end', n)

        def delete_profile():
            sel = lbp.curselection()
            if not sel:
                return
            nm = lbp.get(sel[0])
            self.settings.get('profiles', {}).pop(nm, None)
            save_settings(SETTINGS_PATH, self.settings)
            lbp.delete(sel[0])
        for txt, fn in [('Применить профиль', apply_profile), ('Сохранить текущие как…', save_profile), ('Удалить', delete_profile)]:
            ttk.Button(pr, text=txt, style='Settings.TButton', command=fn).pack(side='left', padx=(0, 6))
        p = page('База')
        b = section(p, 'Локальная база', 'Только локальные документы приложения.')
        d, a, bm = self.db.stats()
        tk.Label(b, text=f'Документов  {d}   •   Статей  {a}   •   Закладок  {bm}', bg=PANEL, fg=TEXT, font=self._font(11, True)).pack(anchor='w', padx=12, pady=12)
        br = tk.Frame(b, bg=PANEL)
        br.pack(fill='x', padx=12, pady=(0, 12))
        ttk.Button(br, text='Проверить базу', style='Settings.TButton', command=self.validate_database).pack(side='left', padx=(0, 5))
        ttk.Button(br, text='Пересобрать базу', style='Settings.TButton', command=self.rebuild_database).pack(side='left', padx=5)
        vars['check_on_start'] = tk.BooleanVar(value=bool(self.settings.get('check_on_start', False)))
        check(b, vars['check_on_start'], 'Проверять базу при запуске')
        b = section(p, 'Сброс')
        tk.Button(b, text='Сбросить все настройки', bg=FIELD, fg=TEXT, activebackground=SELECT, relief='flat', bd=0, font=self._font(9, True), padx=10, pady=7, command=lambda: reset_settings()).pack(anchor='w', padx=12, pady=(0, 10))
        p = page('Расширенные')
        b = section(p, 'Разработчик')
        vars['developer_mode'] = tk.BooleanVar(value=bool(self.settings.get('developer_mode', False)))
        check(b, vars['developer_mode'], 'Режим разработчика')
        ttk.Button(b, text='Открыть data', style='Settings.TButton', command=lambda: self._open_path(DATA)).pack(anchor='w', padx=12, pady=4)
        ttk.Button(b, text='Открыть папку приложения', style='Settings.TButton', command=lambda: self._open_path(BASE)).pack(anchor='w', padx=12, pady=(0, 10))
        ttk.Button(b, text='Экспорт настроек…', style='Settings.TButton', command=self.export_settings).pack(anchor='w', padx=12, pady=4)
        ttk.Button(b, text='Импорт настроек…', style='Settings.TButton', command=self.import_settings).pack(anchor='w', padx=12, pady=4)
        tk.Button(b, text='Проверить настройки JSON', bg=FIELD, fg=TEXT, activebackground=SELECT, relief='flat', bd=0, font=self._font(9, True), padx=10, pady=7, command=lambda: messagebox.showinfo('Настройки', 'Файл настроек читается корректно.\n\nПуть:\n' + str(SETTINGS_PATH), parent=win)).pack(anchor='w', padx=12, pady=4)
        actions = tk.Frame(outer, bg=BG)
        actions.pack(fill='x', pady=(9, 0))
        tk.Button(actions, text='Отмена', bg=FIELD, fg=TEXT, activebackground=SELECT, relief='flat', bd=0, font=self._font(9, True), padx=14, pady=7, command=lambda: (win.destroy(), setattr(self, '_settings_win', None))).pack(side='left')
        ttk.Button(actions, text='По умолчанию', style='Settings.TButton', command=lambda: reset_settings()).pack(side='left', padx=6)
        ttk.Button(actions, text='Применить', style='Settings.TButton', command=lambda: apply_changes(False)).pack(side='right', padx=6)
        ttk.Button(actions, text='Сохранить', style='Settings.Accent.TButton', command=lambda: apply_changes(True)).pack(side='right')

        def apply_changes(close=False):
            self.settings['theme'] = theme_var.get()
            self.settings['custom_colors'] = dict(self._pending_colors)
            self.settings['ui_style'] = {'Минималистичный': 'minimal', 'Legal Tech': 'legal', 'Neon': 'neon', 'Монохромный': 'monochrome', 'Paper Dark': 'paper'}.get(vars['ui_style_label'].get(), 'legal')
            self.settings['glow'] = {'Выкл.': 'off', 'Слабое': 'low', 'Среднее': 'medium', 'Сильное': 'high'}.get(vars['glow'].get(), 'low')
            self.settings['density'] = {'Компактная': 'compact', 'Обычная': 'normal', 'Увеличенная': 'large'}.get(vars['density_label'].get(), 'normal')
            self.settings['list_mode'] = {'Только название': 'title_only', 'Название + описание': 'title_preview'}.get(vars['list_mode'].get(), 'title_preview')
            self.settings['reader_position'] = {'Справа': 'right', 'По центру': 'center'}.get(vars['reader_position'].get(), 'right')
            self.settings['link_mode'] = 'history' if vars['link_mode'].get() == 'Сохранять историю' else 'nohistory'
            self.settings['startup'] = {x[1]: x[0] for x in startvals}.get(vars['startup'].get(), 'home')
            self.settings['quick_access'] = [k for k, v in qvars.items() if v.get()]
            rev = {lbl: k for k, lbl in qopts}
            self.settings['quick_order'] = [rev.get(lb.get(i), lb.get(i)) for i in range(lb.size())]
            for k in ['animations', 'font_scale', 'reader_width', 'show_preview', 'show_sanctions', 'show_related', 'show_article_source', 'remember_scroll', 'auto_scroll_search', 'uk_default', 'koap_default', 'history_limit', 'open_last', 'confirm_exit', 'check_on_start', 'developer_mode']:
                if k in vars:
                    self.settings[k] = vars[k].get()
            self.settings['history_limit'] = int(self.settings.get('history_limit', 50))
            save_settings(SETTINGS_PATH, self.settings)
            self.theme = self.settings['theme']
            self.font_scale = float(self.settings.get('font_scale', 1.0))
            idx = nb.index(nb.select())
            self._rebuild_after_settings(close_window=True, reopen=not close, tab_index=idx)

        def reset_settings():
            if not messagebox.askyesno('Сброс', 'Сбросить все настройки к исходным значениям?', parent=win):
                return
            self.settings = copy.deepcopy(DEFAULT_SETTINGS)
            save_settings(SETTINGS_PATH, self.settings)
            self.theme = self.settings['theme']
            self.font_scale = self.settings['font_scale']
            self._rebuild_after_settings(close_window=True, reopen=False)
        refresh_theme_preview()
        try:
            nb.select(min(int(tab_index), len(pages) - 1))
        except Exception:
            pass
        win.bind('<Escape>', lambda e: self._close_settings_window(win))
        win.protocol('WM_DELETE_WINDOW', lambda: (win.destroy(), setattr(self, '_settings_win', None)))
        for btn in palette_buttons.values():
            btn.configure(cursor='hand2')
        win.focus_force()

    def _close_settings_window(self, win):
        try:
            if win.winfo_exists():
                win.destroy()
        finally:
            self._settings_win = None
        return 'break'

    def _choose_settings_color(self, key, button, win, theme_var, swatches):
        current = self._pending_colors.get(key, self.palette().get(key, ACCENT))
        chosen = colorchooser.askcolor(color=current, parent=win, title=f'Цвет: {key}')[1]
        if chosen:
            self._pending_colors[key] = chosen
            button.configure(text=chosen, bg=chosen, activebackground=chosen)
            theme_var.set('custom')

    def _open_path(self, path):
        try:
            if os.name == 'nt':
                os.startfile(str(path))
        except Exception:
            pass

    def validate_database(self):
        try:
            problems = []
            for lid, title, kind, num, date in self.db.laws():
                arts = self.db.articles(lid)
                if not arts:
                    problems.append(f'Пустой документ: {title}')
                for aid, cid, at, body in arts:
                    if re.search('\\\\[.)]', at or ''):
                        problems.append(f'Экранирование в заголовке: {title} → {at}')
                    if not (body or '').strip():
                        problems.append(f'Пустая статья: {title} → {at}')
            d, a, b = self.db.stats()
            msg = f'Проверка базы\n\n✓ Документов: {d}\n✓ Статей: {a}\n✓ Закладок: {b}\n'
            if problems:
                msg += f'\n⚠ Проблем: {len(problems)}\n' + '\n'.join(problems[:12])
            else:
                msg += '\n✓ Явных проблем не найдено.'
            messagebox.showinfo('Проверка базы', msg, parent=self)
        except Exception as e:
            messagebox.showerror('Проверка базы', str(e), parent=self)

    def rebuild_database(self):
        try:
            self.db.rebuild()
            self.refresh_stats()
            messagebox.showinfo('База', 'Локальная база пересобрана.', parent=self)
        except Exception as e:
            messagebox.showerror('База', str(e), parent=self)

    def palette(self):
        theme = self.theme
        if theme in ('neon', 'pro'):
            theme = 'azure' if theme == 'neon' else 'graphite'
        if theme == 'custom':
            base = PALETTES['azure'].copy()
            base.update(self.settings.get('custom_colors') or {})
        else:
            base = PALETTES.get(theme, PALETTES['azure']).copy()
        style = self.settings.get('ui_style', 'legal')
        glow = self.settings.get('glow', 'low')
        if style == 'minimal':
            base['BORDER'] = '#20262d'
            base['SELECT'] = base['PANEL']
        elif style == 'monochrome':
            base.update(ACCENT='#b4bbc4', GREEN='#a8b0b8', SELECT='#30363f')
        elif style == 'neon':
            base['ACCENT'] = base['ACCENT']
            base['GREEN'] = base['GREEN']
        elif style == 'paper':
            base['BORDER'] = '#3a414b'
        if glow == 'off':
            base['BORDER'] = '#1e252d'
        return base

    def apply_palette(self):
        globals().update(self.palette())

    def build(self):
        self.apply_palette()
        self.configure(bg=BG)
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure('.', background=BG, foreground=TEXT, font=self._font(10))
        style.configure('TButton', background=PANEL, foreground=TEXT, padding=(8, 5), borderwidth=0)
        style.map('TButton', background=[('active', FIELD)])
        style.configure('Accent.TButton', background=ACCENT, foreground='#07131c', font=self._font(9, True), padding=(10, 6), borderwidth=0)
        style.map('Accent.TButton', background=[('active', ACCENT)])
        style.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight={'compact': 24, 'normal': 29, 'large': 34}.get(self.settings.get('density', 'normal'), 29), borderwidth=0, font=self._font(9))
        style.map('Treeview', background=[('selected', SELECT)], foreground=[('selected', TEXT)])
        style.configure('Dark.Vertical.TScrollbar', background=FIELD, troughcolor=BG, arrowcolor=MUTED, bordercolor=BG)
        header = tk.Frame(self, bg=BG)
        header.pack(fill='x', padx=18, pady=(10, 7))
        logo = RESOURCE_BASE / 'assets' / 'brand_logo.png'
        if logo.exists():
            self.brand_logo = tk.PhotoImage(file=str(logo))
            tk.Label(header, image=self.brand_logo, bg=BG).pack(side='left', padx=(0, 8))
        brand = tk.Frame(header, bg=BG)
        brand.pack(side='left')
        tk.Label(brand, text='Юридический помощник', bg=BG, fg=TEXT, font=self._font(18, True)).pack(anchor='w')
        tk.Label(brand, text='by Никита Ефремов', bg=BG, fg=MUTED, font=self._font(8)).pack(anchor='w')
        search_wrap = tk.Frame(header, bg=FIELD, highlightthickness=1, highlightbackground=BORDER)
        search_wrap.pack(side='left', fill='x', expand=True, padx=(34, 8))
        tk.Label(search_wrap, text='⌕', bg=FIELD, fg=MUTED, font=self._font(13)).pack(side='left', padx=(8, 4))
        self.q = tk.StringVar()
        self.search = tk.Entry(search_wrap, textvariable=self.q, bg=FIELD, fg=TEXT, insertbackground=TEXT, selectbackground=SELECT, relief='flat', highlightthickness=0, font=self._font(10))
        self.search.pack(side='left', fill='x', expand=True, ipady=7)
        self.search.insert(0, 'Поиск статьи, документа или нормы…')
        self.search_placeholder = True
        self.search.bind('<FocusIn>', self.search_focus)
        self.search.bind('<KeyRelease>', self.search_typed)
        self.search.bind('<Return>', lambda e: self.global_search())
        self.theme_btn = tk.Button(header, text='◐', bg=BG, fg=MUTED, activebackground=BG, activeforeground=ACCENT, relief='flat', bd=0, width=3, font=self._font(11), command=self.toggle_theme)
        self.theme_btn.pack(side='right')
        ToolTip(self.theme_btn, 'Dark Neon / Dark Pro')
        tk.Frame(self, bg=ACCENT, height=1).pack(fill='x', padx=18, pady=(0, 5))
        self.quickbar = tk.Frame(self, bg=BG)
        self.quickbar.pack(fill='x', padx=18, pady=(0, 6))
        quick_map = {'detention': ('Задержание', self.show_detention), 'uk': ('УК', self.show_uk), 'koap': ('КоАП', self.show_koap), 'pc': ('ПК', lambda: self.open_by_title('процессуальный кодекс')), 'upk': ('УПК', lambda: self.open_by_title('уголовно-процессуальный кодекс')), 'fsb': ('ФСБ', self.show_fsb), 'bookmarks': ('Закладки', self.show_bookmarks)}
        qsel = set(self.settings.get('quick_access', []))
        qorder = self.settings.get('quick_order', list(quick_map.keys()))
        for key in qorder:
            if key in qsel and key in quick_map:
                label, fn = quick_map[key]
                b = tk.Button(self.quickbar, text=label, bg=PANEL, fg=MUTED, activebackground=FIELD, activeforeground=ACCENT, relief='flat', bd=0, font=self._font(8, True), padx=9, pady=4, command=fn)
                b.pack(side='left', padx=(0, 4))
        self.body_pane = ttk.Panedwindow(self, orient='horizontal')
        self.body_pane.pack(fill='both', expand=True, padx=18, pady=(0, 6))
        self.side = ttk.Frame(self.body_pane, padding=8)
        self.mid = ttk.Frame(self.body_pane, padding=10)
        self.right = ttk.Frame(self.body_pane, padding=12)
        self.body_pane.add(self.side, weight=2)
        self.body_pane.add(self.mid, weight=5)
        self.body_pane.add(self.right, weight=7)
        tk.Label(self.side, text='БАЗА', bg=SIDE, fg=MUTED, font=self._font(8, True)).pack(anchor='w', padx=3, pady=(0, 5))
        self.nav = {}
        for key, label, fn, color in [('base', 'Законодательная база', self.show_home, '#5cb6ff'), ('detention', 'Порядок задержания', self.show_detention, '#55d6ff'), ('uk', 'Уголовный кодекс', self.show_uk, '#79b5ff'), ('koap', 'КоАП', self.show_koap, '#44dfc0'), ('fsb', 'ФСБ', self.show_fsb, '#8ea6ff')]:
            self._nav_item(self.side, key, label, fn, color)
        tk.Label(self.side, text='ПРОЧЕЕ', bg=SIDE, fg=MUTED, font=self._font(8, True)).pack(anchor='w', padx=3, pady=(11, 5))
        for key, label, fn, color in [('bookmark','Закладки',self.show_bookmarks,'#ffb568'),('history','История',self.show_recent,'#48dcc0'),('settings','Настройки',self.open_settings,'#9aa7ff')]:
            self._nav_item(self.side,key,label,fn,color)
        ttk.Separator(self.side).pack(fill='x', pady=10)
        self.side.bind('<Configure>', self._responsive_navigation)
        self.after_idle(self._responsive_navigation)
        self.stats_lbl = tk.Label(self.side, text='', bg=SIDE, fg=MUTED, font=self._font(8), justify='left')
        self.stats_lbl.pack(anchor='w', padx=3)
        tk.Label(self.side, text='Ctrl+F  поиск\nCtrl+G  переход\nCtrl+B  закладка\nAlt+←  назад\nEsc  сброс', bg=SIDE, fg=MUTED, font=self._font(8), justify='left').pack(anchor='w', padx=3, pady=(10, 0))
        self.center_title = tk.Label(self.mid, text='', bg=PANEL, fg=TEXT, font=self._font(15, True), anchor='w')
        self.center_title.pack(fill='x')
        self.center_hint = tk.Label(self.mid, text='', bg=PANEL, fg=MUTED, font=self._font(9), anchor='w')
        self.center_hint.pack(fill='x', pady=(2, 7))
        self.codebar = tk.Frame(self.mid, bg=PANEL)
        self.code_filter_var = tk.StringVar(value='Все')
        self.code_search = tk.StringVar()
        self.code_scope_buttons = {}
        self.code_search_row = tk.Frame(self.codebar, bg=PANEL)
        self.code_search_row.pack(fill='x')
        tk.Label(self.code_search_row, text='ПОИСК', bg=PANEL, fg=MUTED, font=self._font(8, True)).pack(side='left', padx=(0, 7))
        self.code_find_entry = tk.Entry(self.code_search_row, textvariable=self.code_search, bg=FIELD, fg=TEXT, insertbackground=TEXT, selectbackground=SELECT, relief='flat', highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT, font=self._font(9))
        self.code_find_entry.pack(side='left', fill='x', expand=True, ipady=4)
        self.code_find_entry.bind('<KeyRelease>', lambda e: self.refresh_code())
        self.code_find_entry.bind('<Return>', lambda e: self.refresh_code())
        self.filter_group = tk.Frame(self.codebar, bg=PANEL)
        self.filter_buttons = {}
        self.filter_specs = {'УК': [('Преступления', 'Преступления'), ('Общая часть', 'Общая часть'), ('Все', 'Все')], 'КоАП': [('Правонарушения', 'Административные правонарушения'), ('ПДД', 'ПДД'), ('Общая часть', 'Общая часть'), ('Все', 'Все')]}
        self.filter_buttons.update({})
        self.search_btn = tk.Button(self.code_search_row, text='Найти', bg=ACCENT, fg='#07131c', activebackground=ACCENT, relief='flat', bd=0, font=self._font(8, True), padx=10, pady=5, command=self.refresh_code)
        list_shell = tk.Frame(self.mid, bg=PANEL)
        list_shell.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(list_shell, show='tree', selectmode='browse')
        self.tree.pack(side='left', fill='both', expand=True)
        self.tree_scroll = ttk.Scrollbar(list_shell, orient='vertical', command=self.tree.yview, style='Dark.Vertical.TScrollbar')
        self.tree_scroll.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=self.tree_scroll.set)
        self.tree.tag_configure('section', foreground=MUTED, font=self._font(8, True))
        self.tree.tag_configure('chapter', foreground=TEXT, font=self._font(9, True))
        self.tree.tag_configure('article', foreground=TEXT, font=self._font(9))
        self.tree.tag_configure('dim', foreground=MUTED, font=self._font(9))
        self.tree.bind('<<TreeviewSelect>>', self.select_tree)
        self.tree.bind('<Motion>', self._tree_motion)
        self._hover_job=None
        self.tree.bind('<Button-2>', self._middle_down)
        self.tree.bind('<B2-Motion>', self._middle_move)
        self.tree.bind('<ButtonRelease-2>', self._middle_up)
        head = tk.Frame(self.right, bg=PANEL)
        head.pack(fill='x')
        self.back_button = tk.Button(head, text='←', bg=PANEL, fg=TEXT, activebackground=FIELD, activeforeground=ACCENT, relief='flat', bd=0, width=3, font=self._font(12), command=self.go_back, state='disabled')
        self.back_button.pack(side='left', padx=(0, 6))
        ToolTip(self.back_button, 'Назад')
        self.forward_button=tk.Button(head,text='→',bg=PANEL,fg=TEXT,activebackground=FIELD,activeforeground=ACCENT,relief='flat',bd=0,width=3,font=self._font(12),command=self.go_forward,state='disabled')
        self.forward_button.pack(side='left',padx=(0,6))
        ToolTip(self.forward_button,'Вперёд')
        self.rtitle = tk.Label(head, text='Выберите статью', bg=PANEL, fg=TEXT, font=self._font(17, True), anchor='w')
        self.rtitle.pack(side='left', fill='x', expand=True)
        action = tk.Frame(head, bg=PANEL)
        action.pack(side='right')
        for sym, tip, fn in [('☆', 'Закладка', self.toggle_bookmark), ('📌', 'Закрепить закладку', self.toggle_pin), ('⧉', 'Копировать', self.copy), ('⇩', 'Экспорт', self.export), ('↗', 'Открыть в новом окне', self.open_article_window), ('⛶', 'Режим чтения', self.toggle_read_mode)]:
            b = tk.Button(action, text=sym, bg=PANEL, fg=MUTED, activebackground=FIELD, activeforeground=ACCENT, relief='flat', bd=0, width=3, font=self._font(10), command=fn)
            b.pack(side='left')
            ToolTip(b, tip)
            if sym == '☆':
                self.star = b
        self.meta = tk.Label(self.right, text='', bg=PANEL, fg=MUTED, font=self._font(9), anchor='w')
        self.meta.pack(fill='x', pady=(4, 1))
        self.crumbs = tk.Frame(self.right, bg=PANEL)
        self.crumbs.pack(fill='x', pady=(0, 4))
        self.workspacebar=tk.Frame(self.right,bg=PANEL)
        self.workspacebar.pack(fill='x',pady=(0,5))
        self._workspace={}
        shell = tk.Frame(self.right, bg=READER)
        shell.pack(fill='both', expand=True)
        self.reader = ScrolledText(shell, wrap='word', bg=READER, fg=TEXT, insertbackground=TEXT, selectbackground=SELECT, relief='flat', font=self._font(10), padx=24, pady=20)
        self.reader.pack(side='left', fill='both', expand=True)
        self.reader_scroll = ttk.Scrollbar(shell, orient='vertical', command=self.reader.yview, style='Dark.Vertical.TScrollbar')
        self.reader_scroll.pack(side='right', fill='y')
        self.reader.configure(yscrollcommand=self.reader_scroll.set)
        self.reader.tag_configure('head', foreground=GREEN, font=self._font(15, True))
        self.reader.tag_configure('subhead', foreground=TEXT, font=self._font(10, True))
        self.reader.tag_configure('body', foreground=TEXT, font=self._font(10), spacing3=5)
        self.reader.tag_configure('measure', foreground=RED, font=self._font(10, True), spacing1=4, spacing3=5)
        self.reader.tag_configure('measure_label', foreground=RED, font=self._font(8, True))
        self.reader.tag_configure('ref', foreground=ACCENT, underline=True)
        self.reader.bind('<Button-2>', self._middle_down)
        self.reader.bind('<B2-Motion>', self._middle_move)
        self.reader.bind('<ButtonRelease-2>', self._middle_up)
        self.reader.configure(state='disabled')
        self.refs_box = tk.Frame(self.right, bg=PANEL)
        if self.settings.get('show_related', True):
            self.refs_box.pack(fill='x', pady=(7, 0))
        tk.Label(self.refs_box, text='СВЯЗАННЫЕ НОРМЫ', bg=PANEL, fg=MUTED, font=self._font(8, True)).pack(anchor='w')
        self.refs_inner = tk.Frame(self.refs_box, bg=PANEL)
        self.refs_inner.pack(fill='x', pady=(3, 0))
        self.status = tk.Label(self, text='', bg=BG, fg=MUTED, font=self._font(8), anchor='w')
        self.status.pack(fill='x', padx=18, pady=(0, 5))

    def _nav_item(self, parent, key, label, fn, color):
        row = tk.Frame(parent, bg=SIDE, cursor='hand2')
        row.pack(fill='x', pady=1)
        stripe = tk.Frame(row, bg=color, width=2)
        stripe.pack(side='left', fill='y')
        short_map = {'Законодательная база':'База', 'Порядок задержания':'Задерж', 'Уголовный кодекс':'УК', 'КоАП':'КоАП', 'ФСБ':'ФСБ', 'Закладки':'Закл.', 'История':'Ист.', 'Настройки':'Настр.'}
        icon_map = {'Законодательная база':'Б', 'Порядок задержания':'З', 'Уголовный кодекс':'УК', 'КоАП':'КА', 'ФСБ':'ФС', 'Закладки':'★', 'История':'И', 'Настройки':'⚙'}
        txt = tk.Label(row, text=label, bg=SIDE, fg=TEXT, font=self._font(9), anchor='w')
        txt.pack(side='left', fill='x', expand=True, padx=9, pady=6)
        ToolTip(row, label)
        txt._full_label = label
        txt._short_label = short_map.get(label, label)
        txt._icon_label = icon_map.get(label, label[:2])
        for w in (row, stripe, txt):
            w.bind('<Button-1>', lambda e, f=fn: f())
            w.bind('<Enter>', lambda e, r=row, c=color: self._nav_hover(r, c, True))
            w.bind('<Leave>', lambda e, r=row: self._nav_hover(r, None, False))
        self.nav[key] = (row, color)

    def _nav_hover(self, row, color, active):
        row.configure(bg=PANEL if active else SIDE)
        for w in row.winfo_children():
            if isinstance(w, tk.Label):
                w.configure(bg=PANEL if active else SIDE)

    def _responsive_navigation(self, event=None):
        try:
            w = self.side.winfo_width()
            compact = w < 165
            ultra = w < 105
            if ultra:
                try:
                    # Keep a usable navigation rail even when the user drags the pane very narrow.
                    self.body_pane.sashpos(0, 78)
                except Exception:
                    pass
            for row, _color in getattr(self, 'nav', {}).values():
                for child in row.winfo_children():
                    if isinstance(child, tk.Label) and hasattr(child, '_full_label'):
                        child.configure(text=(child._icon_label if ultra else (child._short_label if compact else child._full_label)), padx=(4 if ultra else (6 if compact else 9)), anchor='center' if ultra else 'w')
        except Exception:
            pass

    def _set_active(self, key):
        for k, (row, color) in getattr(self, 'nav', {}).items():
            active = k == key
            row.configure(bg=PANEL if active else SIDE)
            for w in row.winfo_children():
                if isinstance(w, tk.Label):
                    w.configure(bg=PANEL if active else SIDE, fg=color if active else TEXT)

    def _tree_motion(self,event=None):
        try:
            iid=self.tree.identify_row(event.y)
            if not iid or not iid.startswith('A'): return
            row=self.db.article(int(iid[1:]))
            if not row:return
            preview=re.sub(r'\s+',' ',row[3] or '').strip()
            if len(preview)>180: preview=preview[:180].rsplit(' ',1)[0]+'…'
            if preview:self.status.configure(text=preview)
        except Exception:pass

    def refresh_stats(self):
        d, a, b = self.db.stats()
        self.stats_lbl.configure(text=f'{d} документов\n{a} статей\n{b} закладок')

    def clear_tree(self):
        self._tree_lock = True
        self.tree.delete(*self.tree.get_children())
        try:
            self.after_idle(lambda: setattr(self, '_tree_lock', False))
        except Exception:
            self._tree_lock = False

    def clear_refs(self):
        for w in self.refs_inner.winfo_children():
            w.destroy()

    def set_reader(self, text):
        self.reader.configure(state='normal')
        self.reader.delete('1.0', 'end')
        self.reader.insert('end', text)
        self.reader.configure(state='disabled')

    def clear_crumbs(self):
        for w in self.crumbs.winfo_children():
            w.destroy()

    def crumb(self, text, fn=None, active=False):
        if self.crumbs.winfo_children():
            tk.Label(self.crumbs, text=' / ', bg=PANEL, fg=MUTED, font=self._font(8)).pack(side='left')
        if fn:
            b = tk.Button(self.crumbs, text=text, bg=PANEL, fg=ACCENT, activebackground=FIELD, activeforeground=ACCENT, relief='flat', bd=0, font=self._font(8), command=fn, cursor='hand2')
            b.pack(side='left')
        else:
            tk.Label(self.crumbs, text=text, bg=PANEL, fg=TEXT if active else MUTED, font=self._font(8, True)).pack(side='left')

    def placeholder(self, text='Выберите элемент в центральной панели.'):
        self.article_id = None
        self.rtitle.configure(text='Выберите статью')
        self.meta.configure(text='')
        self.clear_crumbs()
        self.set_reader(text)
        self.star.configure(text='☆')
        self.clear_refs()

    def search_focus(self, e=None):
        if self.search_placeholder:
            self.search.delete(0, 'end')
            self.search_placeholder = False

    def search_typed(self, e=None):
        self.search_focus()
        if self._search_job:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.after(250, lambda: self._show_search_hint(self.q.get().strip()))

    def _show_search_hint(self, q):
        if q:
            rows = self.db.search(q)[:3]
            names = [r[3] for r in rows]
            self.status.configure(text=('  •  '.join(names) if names else 'Ничего не найдено')[:180])

    def global_search(self, add_history=True):
        self._hide_dynamic_bars()
        if self.search_placeholder:
            return self.show_home(add_history=False)
        q = self.q.get().strip()
        if not q:
            return self.show_home(add_history=False)
        if add_history:
            self._save_view()
        self.mode = 'search'
        self.code = None
        self.codebar.pack_forget()
        self.clear_refs()
        self.clear_tree()
        if hasattr(self, 'fsbbar'):
            self.fsbbar.pack_forget()
        rows = self.db.search(q)
        for score, aid, lid, at, body, lt, num in rows[:800]:
            if not self.is_top_level_article(at):
                continue
            self.tree.insert('', 'end', iid=f'A{aid}', text=self.pretty_label(at, body), tags=('article',))
        self.center_title.configure(text='Поиск')
        self.center_hint.configure(text=f'{len(rows)} найдено')
        self.placeholder()
        self.status.configure(text=f'Поиск по базе: {len(rows)}')
        self._update_back()

    def open_by_title(self, needle):
        for lid, title, kind, num, date in self.db.laws():
            if needle.lower() in (title or '').lower():
                return self.open_doc(lid)
        self.status.configure(text=f'Не найден документ: {needle}')

    def show_home(self, add_history=True):
        self._hide_dynamic_bars()
        if add_history:
            self._save_view()
        self._set_active('base')
        self.mode = 'home'
        self.code = None
        self.codebar.pack_forget()
        self.clear_refs()
        self.clear_tree()
        if hasattr(self, 'fsbbar'):
            self.fsbbar.pack_forget()
        self.tree.heading('#0', text='Документы')
        self.tree.column('#0', width=700)
        groups = {'Основные акты': [], 'Федеральные законы': [], 'Кодексы': []}
        for lid, t, k, n, d in self.db.laws():
            title = (t or '').lower()
            if 'кодекс' in title or (k or '').lower() == 'кодекс':
                group = 'Кодексы'
            elif 'федеральный' in title or 'закон' in title:
                group = 'Федеральные законы'
            else:
                group = 'Основные акты'
            groups[group].append((lid, t, k, n, d))
        sid = self.tree.insert('', 'end', text='Основные акты', tags=('section',), open=True)
        quick = []
        for item in groups['Основные акты']:
            if 'конституция' in (item[1] or '').lower():
                quick.append(item)
                break
        for needle in ('уголовный кодекс', 'кодекс об административных правонарушениях', 'процессуальный кодекс российской федерации', 'уголовно-процессуальный кодекс'):
            for item in groups['Кодексы']:
                if needle in (item[1] or '').lower() and item not in quick:
                    quick.append(item)
                    break
        for lid, t, k, n, d in quick:
            self.tree.insert(sid, 'end', iid=f'L{lid}', text=t, tags=('article',))
        quick_ids = {item[0] for item in quick}
        for group in ('Федеральные законы', 'Кодексы'):
            rows = groups[group]
            if not rows:
                continue
            sid = self.tree.insert('', 'end', text=group, tags=('section',), open=group == 'Федеральные законы')
            for lid, t, k, n, d in sorted(rows, key=lambda x: (x[1] or '').lower()):
                if lid in quick_ids:
                    continue
                self.tree.insert(sid, 'end', iid=f'L{lid}', text=t, tags=('article',))
        total = sum((len(v) for v in groups.values()))
        self.center_title.configure(text='Законодательная база')
        self.center_hint.configure(text=f'{total} документов · 5 основных актов сверху · полный список кодексов внизу')
        self.placeholder('Выберите документ, чтобы открыть его оглавление.')
        self.refresh_stats()
        self.status.configure(text='Законодательная база')
        self._update_back()

    def show_detention(self, add_history=True):
        self._hide_dynamic_bars()
        if add_history:
            self._save_view()
        self._set_active('detention')
        self.mode = 'detention'
        self.code = None
        self.law_id = None
        self.article_id = None
        self.codebar.pack_forget()
        self.clear_refs()
        self.clear_tree()
        if hasattr(self, 'fsbbar'):
            try:
                self.fsbbar.pack_forget()
            except Exception:
                pass
        if hasattr(self, 'detbar'):
            try:
                self.detbar.destroy()
            except Exception:
                pass
        self.detbar = tk.Frame(self.mid, bg=PANEL)
        self.detbar.pack(fill='x', pady=(0, 8), before=self.tree.master)
        for title, value in [('МАКСИМУМ', '60 мин'), ('ПРЕДВАРИТЕЛЬНОЕ', '15 мин'), ('ГОСАДВОК', '5 + 5 мин'), ('ТЕЛЕФОН', 'до 2 мин')]:
            box = tk.Frame(self.detbar, bg=FIELD)
            box.pack(side='left', padx=(0, 5))
            tk.Label(box, text=title, bg=FIELD, fg=MUTED, font=self._font(7, True)).pack(padx=7, pady=(5, 0), anchor='w')
            tk.Label(box, text=value, bg=FIELD, fg=GREEN, font=self._font(10, True)).pack(padx=7, pady=(0, 5), anchor='w')
        self.tree.heading('#0', text='Порядок действий')
        self.tree.column('#0', width=780)
        steps = [('01', 'Проверить основание', 'ПК 7', 'Есть законное основание?'), ('02', 'Представиться', 'ПК 10.1', 'Должность → звание → фамилия; при сокрытии личности — жетон и позывной.'), ('03', 'Назвать статьи', 'ПК 10.1', 'Огласить все инкриминируемые статьи.'), ('04', 'Провести личный обыск', 'ПК 10.1', 'Проверить наличие нелегальных предметов.'), ('05', 'Предложить реализовать права', 'ПК 8.3–8.4', 'Предложить госадвоката; разъяснить доступные права.'), ('06', 'Реализовать заявленные права', 'ПК 9', 'Госадвокат 5+5 мин; телефон до 2 мин; беседа — отдельно.'), ('07', 'Доставить', 'ПК 10.1', 'Доставить в следствие, дознание или правоохранительный орган.'), ('08', 'Принять решение', 'ПК 13', 'Арест / иное решение в пределах полномочий.'), ('09', 'Освободить при основании', 'ПК 14', 'Освободить при отсутствии оснований или при истечении срока.')]
        self._detention_steps = {x[0]: x for x in steps}
        for num, title, art, desc in steps:
            self.tree.insert('', 'end', iid=f'D{num}', text=f'{num}   {title}', tags=('article',))
        self.center_title.configure(text='Порядок задержания')
        self.center_hint.configure(text='9 последовательных шагов · короткая шпаргалка · полная норма открывается справа')
        self._render_detention_quick('01')
        self.status.configure(text='Порядок задержания')
        self._update_back()

    def select_detention_step(self, step):
        self._render_detention_quick(step)

    def show_code(self, code, add_history=True, submode=None):
        self._hide_dynamic_bars()
        if add_history:
            self._save_view()
        self.mode = 'code'
        self.code = code
        if hasattr(self, 'fsbbar'):
            self.fsbbar.pack_forget()
        self.codebar.pack(fill='x', pady=(0, 8), before=self.tree.master)
        self.code_search.set('')
        self.search_btn.pack(side='left', padx=(6, 0))
        self.filter_group.pack(fill='x', pady=(7, 0))
        for w in self.filter_group.winfo_children():
            w.destroy()
        self.filter_buttons = {}
        specs = self.filter_specs.get(code, [('Все', 'Все')])
        default = (self.settings.get('uk_default', 'Преступления') if code == 'УК' else self.settings.get('koap_default', 'Правонарушения')) if submode is None else submode
        allowed = [x[0] for x in specs]
        self.code_filter_var.set(default if default in allowed else allowed[0])
        for val, label in specs:
            b = tk.Button(self.filter_group, text=label, bg=PANEL, fg=MUTED, activebackground=FIELD, activeforeground=TEXT, relief='flat', bd=0, font=self._font(8), padx=8, pady=4, command=lambda x=val: self.select_code_filter(x))
            b.pack(side='left', padx=1)
            self.filter_buttons[val] = b
        self._paint_code_filter()
        self.center_title.configure(text='Уголовный кодекс' if code == 'УК' else 'КоАП')
        self.refresh_code()
        self._update_back()

    def select_code_filter(self, val):
        self.code_filter_var.set(val)
        self._paint_code_filter()
        self.refresh_code()

    def _paint_code_filter(self):
        current = self.code_filter_var.get()
        for val, b in self.filter_buttons.items():
            if val == current:
                b.configure(bg=ACCENT, fg='#07131c')
            else:
                b.configure(bg=PANEL, fg=MUTED)

    def refresh_code(self):
        if self.mode != 'code':
            return
        q = self.code_search.get().strip()
        filt = self.code_filter_var.get()
        rows = self.db.search(q, self.code, filt)
        practical_filters = ('Преступления', 'Правонарушения', 'ПДД')
        if filt in practical_filters:

            def _article_sort_key(r):
                n = self.db.article_number(r[3])
                parts = [int(x) for x in re.findall('\\d+', n)] if n else [9999]
                return parts
            rows = sorted(rows, key=_article_sort_key)
        self.clear_tree()
        self.tree.heading('#0', text='Статьи')
        last_chapter = None
        sid = ''
        shown = 0
        all_titles = [r[3] for r in rows]
        for score, aid, lid, at, body, lt, num in rows[:1000]:
            if not self.is_top_level_article(at, all_titles):
                continue
            chapter_row = self.db.c.execute('SELECT c.title FROM chapters c JOIN articles a ON a.chapter_id=c.id WHERE a.id=?', (aid,)).fetchone()
            chapter = chapter_row[0] if chapter_row else ''
            if filt in ('Преступления', 'Правонарушения', 'ПДД') and chapter and (chapter != last_chapter):
                sid = self.tree.insert('', 'end', text=chapter, tags=('section',), open=True)
                last_chapter = chapter
            parent = sid if filt in ('Преступления', 'Правонарушения', 'ПДД') and chapter else ''
            self.tree.insert(parent, 'end', iid=f'A{aid}', text=self.pretty_label(at, body), tags=('article',))
            shown += 1
        if self.code == 'КоАП':
            hint = {'Все': 'Все статьи', 'Правонарушения': 'Только составы с наказанием', 'ПДД': 'ПДД · только составы 9.x', 'Общая часть': 'Общие нормы'}[filt]
        else:
            hint = {'Все': 'Все статьи', 'Преступления': 'Только составы с наказанием', 'Общая часть': 'Общие нормы'}[filt]
        self.center_hint.configure(text=f'{len(rows)} статей · {hint}')
        self.placeholder('Выберите статью справа для просмотра текста и связанных норм.')
        self.status.configure(text=f'{self.code} · {len(rows)}')
        self._update_back()

    def pretty_label(self, at, body, show_sanction=False):
        return self.article_list_label(at, body)

    def article_list_label(self, title, body):
        """Compact catalogue label. Full parts stay in the reader."""
        title = re.sub('\\s+', ' ', title or '').strip()
        body = clean_md(re.sub('\\s+', ' ', body or '').strip())
        mode = self.settings.get('list_mode', 'title_preview')
        if mode == 'title_only':
            return title if len(title) <= 140 else title[:140].rsplit(' ', 1)[0] + '…'
        if mode in ('title_preview', 'title_measure') and re.fullmatch('Статья\\s+\\d+(?:[-.]\\d+)*\\.?', title, re.I) and body:
            preview = re.split('(?<=[.!?])\\s+', body, 1)[0].strip(' -–—')
            lim = max(40, int(self.settings.get('preview_chars', 110)))
            if len(preview) > lim:
                preview = preview[:lim].rsplit(' ', 1)[0] + '…'
            if preview and mode == 'title_preview':
                return f'{title} — {preview}'
            if preview and mode == 'title_measure':
                measure = self._extract_first_measure(body)
                return f'{title} — {measure}' if measure else f'{title} — {preview}'
        return title if len(title) <= 140 else title[:140].rsplit(' ', 1)[0] + '…'

    def _extract_first_measure(self, body):
        txt = clean_md(body or '')
        m = re.search('(?im)^\\s*(?:наказывается|влечет|влечёт|предусматривает|назначается).{0,160}', txt)
        return re.sub('\\s+', ' ', m.group(0)).strip(' .—-;:') if m else ''

    def is_top_level_article(self, title, all_titles=None):
        """Every parsed `Статья ...` heading is a standalone article.

        The parser only creates an Article record for an explicit article heading.
        Parts such as 65-1.1 that appear in the body are therefore not accidentally
        promoted to articles, while real headings such as `Статья 65-1` remain visible.
        """
        return bool(re.match(r'^\s*Статья\s+\d+(?:-\d+)?(?:\.\d+)*', title or '', re.I))

    def open_doc(self, lid, add_history=True):
        self._hide_dynamic_bars()
        if add_history:
            self._save_view()
        self.mode = 'articles'
        self.law_id = lid
        self.article_id = None
        self.codebar.pack_forget()
        self.clear_refs()
        self.clear_tree()
        if hasattr(self, 'fsbbar'):
            self.fsbbar.pack_forget()
        law = self.db.c.execute('SELECT title,kind,number,date FROM laws WHERE id=?', (lid,)).fetchone()
        arts = self.db.articles(lid)
        self.tree.heading('#0', text='Содержание')
        self.tree.column('#0', width=760)
        parents = {}
        for cid, ct in self.db.chapters(lid):
            parents[cid] = self.tree.insert('', 'end', iid=f'C{cid}', text=ct, tags=('chapter',), open=True)
        all_titles = [a[2] for a in arts]
        for aid, cid, at, body in arts:
            if cid in parents and self.is_top_level_article(at, all_titles):
                self.tree.insert(parents[cid], 'end', iid=f'A{aid}', text=self.article_list_label(at, body), tags=('article',))
        self.center_title.configure(text=law[0])
        self.center_hint.configure(text=f"{law[1]} · {law[3] or '—'} · {len(arts)} статей")
        self.rtitle.configure(text=law[0])
        self.meta.configure(text=f"{law[1]} · {law[3] or '—'}")
        self.clear_crumbs()
        self.crumb(law[0], None, active=True)
        self.set_reader(f"{law[0]}\n\n{law[1]}\n\n{law[3] or ''}\n\n{len(arts)} статей\n\nВыберите статью в содержании.")
        self.star.configure(text='☆')
        self.status.configure(text='Документ открыт')
        self._update_back()

    def _save_reader_position(self):
        if not getattr(self, 'article_id', None) or not self.settings.get('remember_scroll', True) or not hasattr(self, 'reader'):
            return
        try:
            self._reader_scroll[int(self.article_id)] = self.reader.yview()
        except Exception:
            pass

    def _restore_reader_position(self, aid):
        if not self.settings.get('remember_scroll', True) or not hasattr(self, 'reader'):
            return
        pos = self._reader_scroll.get(int(aid))
        if not pos:
            return
        try:
            self.reader.yview_moveto(float(pos[0]))
        except Exception:
            pass

    def open_article(self, aid, add_history=True):
        if self.mode == 'article' and self.article_id == aid:
            return
        self._save_reader_position()
        self._hide_dynamic_bars()
        if add_history and self.settings.get('link_mode', 'history') == 'history':
            self._save_view()
        row = self.db.article(aid)
        if not row:
            return
        self.mode = 'article'
        self.article_id = aid
        self.law_id = row[1]
        self.code = None
        self.codebar.pack_forget()
        self.db.add_recent(row[1], aid)
        self.rtitle.configure(text=row[2] or self.article_number(row[2]) or 'Статья')
        self.meta.configure(text=f"{row[4]} · {row[8]} · {row[7] or '—'}" if self.settings.get('show_article_source', True) else f"{row[8]} · {row[7] or '—'}")
        self.clear_crumbs()
        self._add_workspace_tab(aid)
        self.crumb(row[4], lambda lid=row[1]: self.open_doc(lid))
        self.crumb(row[8], None, active=True)
        self.render_article(row)
        self.after_idle(lambda a=aid: self._restore_reader_position(a))
        self.build_refs(extract_refs(row[3]))
        self.star.configure(text='★' if self.db.bookmarked(row[1], aid) else '☆')
        self.status.configure(text='Статья открыта')
        self._update_back()

    def _add_ref_button(self, label, aid):
        b = tk.Button(self.refs_inner, text=label, bg=FIELD, fg=ACCENT, activebackground=SELECT, activeforeground=TEXT, relief='flat', bd=0, font=self._font(8), padx=7, pady=3, command=lambda a=aid: self.open_article(a))
        b.pack(side='left', padx=2, pady=2)

    def build_refs(self, refs):
        self.clear_refs()
        if not self.settings.get('show_related', True):
            return
        for c, n in refs[:24]:
            found = self.db.find_ref(c, n)
            b = tk.Button(self.refs_inner, text=f'{c} · ст. {n}', bg=FIELD, fg=ACCENT if found else MUTED, activebackground=SELECT, activeforeground=TEXT, relief='flat', bd=0, font=self._font(8), padx=7, pady=3, command=(lambda a=found[0]: self.open_article(a)) if found else lambda cc=c, nn=n: self.jump_ref(cc, nn))
            b.pack(side='left', padx=2, pady=2)
        # Reverse links: show a compact list of articles that reference the current norm.
        if self.article_id:
            row=self.db.article(self.article_id)
            if row:
                law=row[4].lower(); code='УК' if 'уголовный кодекс' in law else ('КоАП' if 'административ' in law and 'кодекс' in law else None)
                num=self.db.article_number(row[2])
                if code and num:
                    backs=self.db.backlinks(code,num,limit=8)
                    if backs:
                        tk.Label(self.refs_inner,text='  ←  ссылаются:',bg=PANEL,fg=MUTED,font=self._font(8,True)).pack(side='left',padx=(8,3))
                        for aid,lid,at,lt in backs:
                            label=self.db.article_number(at) or at
                            b=tk.Button(self.refs_inner,text=f'{lt.split(" — ")[0]} {label}',bg=FIELD,fg=ACCENT,activebackground=SELECT,activeforeground=TEXT,relief='flat',bd=0,font=self._font(8),padx=6,pady=3,command=lambda a=aid:self.open_article(a))
                            b.pack(side='left',padx=2,pady=2)

    def jump_ref(self, c, n):
        found = self.db.find_ref(c, n)
        if not found and re.fullmatch('\\d+\\.\\d+', str(n)):
            found = self.db.find_ref(c, str(n).split('.')[0])
        if not found and re.fullmatch('\\d+-\\d+', str(n)):
            found = self.db.find_ref(c, str(n).split('-')[0])
        if found:
            self.open_article(found[0])
            return
        self.search_placeholder = False
        self.q.set(f'{c} {n}')
        self.global_search()

    def show_bookmarks(self, add_history=True):
        self._hide_dynamic_bars()
        if add_history:
            self._save_view()
        self._set_active('bookmark')
        self.mode = 'bookmarks'
        self.code = None
        self.codebar.pack_forget()
        self.clear_refs()
        self.clear_tree()
        if hasattr(self, 'fsbbar'):
            self.fsbbar.pack_forget()
        self.tree.heading('#0', text='Сохранённые статьи')
        rows = self.db.bookmarks()
        current_law = None
        for lid, aid, pinned, lt, at, body in rows:
            if lid != current_law:
                current_law = lid
                sid = self.tree.insert('', 'end', text=lt, tags=('section',), open=True)
                parent = sid
            else:
                parent = sid
            self.tree.insert(parent, 'end', iid=f'A{aid}', text=('📌  ' if pinned else '') + self.article_list_label(at, self.db.article(aid)[3] if self.db.article(aid) else ''), tags=('article',))
        self.center_title.configure(text='Закладки')
        self.center_hint.configure(text=f'{len(rows)} сохранённых')
        self.placeholder('Выберите сохранённую статью.')
        self.status.configure(text='Закладки')
        self._update_back()

    def show_recent(self, add_history=True):
        self._hide_dynamic_bars()
        if add_history:
            self._save_view()
        self._set_active('history')
        self.mode = 'recent'
        self.code = None
        self.codebar.pack_forget()
        self.clear_refs()
        self.clear_tree()
        if hasattr(self, 'fsbbar'):
            self.fsbbar.pack_forget()
        self.tree.heading('#0', text='Последние открытия')
        rows = self.db.recent(int(self.settings.get('history_limit', 50) or 50))
        for lid, aid, lt, at, opened_at in rows:
            ts = time.strftime('%d.%m %H:%M', time.localtime(opened_at))
            self.tree.insert('', 'end', iid=f'A{aid}', text=f'{ts}  ·  ' + self.article_list_label(at, self.db.article(aid)[3] if self.db.article(aid) else ''), tags=('article',))
        self.center_title.configure(text='История')
        self.center_hint.configure(text=f'{len(rows)} последних')
        self.placeholder('Выберите запись из истории.')
        self.status.configure(text='История')
        self._update_back()

    def toggle_read_mode(self):
        self._read_mode = not self._read_mode
        try:
            if self._read_mode:
                self.attributes('-zoomed', True)
                self.status.configure(text='Режим чтения · нажмите ⛶ для выхода')
            else:
                self.attributes('-zoomed', False)
        except Exception:
            pass

    def toggle_theme(self):
        cycle = ['azure', 'graphite', 'emerald', 'violet', 'amber', 'crimson', 'cyan', 'midnight', 'paper']
        try:
            i = cycle.index(self.theme)
        except ValueError:
            i = 0
        self.theme = cycle[(i + 1) % len(cycle)]
        self.settings['theme'] = self.theme
        save_settings(SETTINGS_PATH, self.settings)
        article = self.article_id
        state = (self.mode, self.code, self.law_id, self.article_id)
        for w in list(self.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass
        self.build()
        mode, code, law, article = state
        if mode == 'article' and article:
            self.open_article(article, add_history=False)
        elif mode == 'detention':
            self.show_detention(add_history=False)
        elif mode == 'fsb':
            self.show_fsb(add_history=False)
        elif mode == 'bookmarks':
            self.show_bookmarks(add_history=False)
        elif mode == 'recent':
            self.show_recent(add_history=False)
        elif code == 'УК':
            self.show_uk(add_history=False)
        elif code == 'КоАП':
            self.show_koap(add_history=False)
        else:
            self.show_home(add_history=False)
        self._update_back()

    def toggle_bookmark(self):
        if not self.article_id:
            return
        row = self.db.article(self.article_id)
        on = self.db.toggle_bm(row[1], row[0])
        self.star.configure(text='★' if on else '☆')
        self.refresh_stats()

    def toggle_pin(self):
        if not self.article_id:
            return
        row = self.db.article(self.article_id)
        if not row:
            return
        if not self.db.bookmarked(row[1], row[0]):
            self.db.toggle_bm(row[1], row[0])
        pinned = self.db.pin_bm(row[1], row[0])
        self.status.configure(text='Закладка закреплена' if pinned else 'Закладка откреплена')
        self.refresh_stats()
        if self.mode == 'bookmarks':
            self.show_bookmarks(add_history=False)

    def copy(self):
        if not self.article_id:
            return
        row = self.db.article(self.article_id)
        self.clipboard_clear()
        self.clipboard_append(f"{row[2]}\n\n{row[3] or ''}")
        self.update()
        self.status.configure(text='Скопировано')

    def export(self):
        if not self.article_id:
            return
        row = self.db.article(self.article_id)
        p = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Текст', '*.txt')], title='Экспорт статьи')
        if p:
            Path(p).write_text(f"{row[2]}\n\n{row[3] or ''}", encoding='utf-8')
            self.status.configure(text='Экспортировано')

    def _middle_down(self, e):
        self._middle_widget = e.widget
        self._middle_y = e.y_root
        self._middle_active = True
        return 'break'

    def _middle_move(self, e):
        if not self._middle_active or not self._middle_widget:
            return 'break'
        dy = e.y_root - self._middle_y
        steps = max(-18, min(18, int(dy / 8)))
        if steps:
            try:
                self._middle_widget.yview_scroll(-steps, 'units')
            except Exception:
                pass
        self._middle_y = e.y_root
        return 'break'

    def _middle_up(self, e):
        self._middle_active = False
        self._middle_widget = None
        return 'break'

    def _hide_dynamic_bars(self):
        """Hide transient toolbars so one section cannot leak UI into another."""
        for name in ('codebar','detbar','fsbbar'):
            w = getattr(self, name, None)
            if w is not None:
                try:
                    w.pack_forget()
                except Exception:
                    pass

    def reset(self):
        self.search.delete(0, 'end')
        self.search.insert(0, 'Поиск статьи, документа или нормы…')
        self.search_placeholder = True
        self.show_home(add_history=False)
        self.search.focus_force()

    def _render_detention_quick(self, step):
        item = getattr(self, '_detention_steps', {}).get(step)
        if not item:
            return
        num, title, art, desc = item
        self.mode = 'detention'
        self.article_id = None
        self.law_id = None
        self._det_step = step
        self.rtitle.configure(text=title)
        self.meta.configure(text=f'{art} · краткая памятка')
        self.clear_crumbs()
        self.crumb('Порядок задержания', lambda: self.show_detention(add_history=False))
        self.crumb(title, None, active=True)
        self.reader.configure(state='normal')
        self.reader.delete('1.0', 'end')
        self.reader.insert('end', f'{num}  {title}\n\n', 'head')
        self.reader.insert('end', 'ДЕЙСТВИЕ\n', 'subhead')
        self.reader.insert('end', desc + '\n\n', 'body')
        timings = {'01': 'Максимум: 60 минут с момента фактического задержания. Предварительное задержание: 15 минут.', '05': 'Право на государственного адвоката сотрудник обязан предложить.', '06': 'Госадвокат: 5 минут ожидания ответа + 5 минут ожидания прибытия. Телефон: до 2 минут. Конфиденциальная беседа — в отдельном помещении без сотрудника.', '09': 'Проверить основания освобождения до истечения максимально допустимого срока.'}
        if step in timings:
            self.reader.insert('end', 'СРОК / ТАЙМИНГ\n', 'subhead')
            self.reader.insert('end', timings[step] + '\n\n', 'measure')
        self.reader.insert('end', 'ИСТОЧНИК\n', 'subhead')
        found = self.db.find_ref('ПК', art.split(' ', 1)[-1].split('.')[0])
        if found:
            tag = f'det_ref_{time.time_ns()}'
            self.reader.insert('end', art, ('ref', tag))
            self.reader.tag_bind(tag, '<Button-1>', lambda e, a=found[0]: self.open_article(a))
        else:
            self.reader.insert('end', art, 'body')
        self.reader.configure(state='disabled')
        parent = art.split(' ', 1)[-1].split('.')[0]
        self.build_refs([('ПК', parent)])
        self._update_back()

    def _hide_all_special_bars(self):
        if hasattr(self, 'fsbbar'):
            try:
                self.fsbbar.pack_forget()
            except Exception:
                pass
        if hasattr(self, 'detbar'):
            try:
                self.detbar.destroy()
            except Exception:
                pass

    def _fsb_tile(self, parent, key, title, desc, active=False, command=None):
        bg = SELECT if active else PANEL
        border = ACCENT if active else BORDER
        card = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=border, highlightcolor=ACCENT, cursor='hand2')
        card.grid_propagate(True)
        icon = tk.Label(card, text='›' if not active else '●', bg=bg, fg=ACCENT, font=self._font(10, True))
        icon.grid(row=0, column=0, rowspan=2, sticky='nw', padx=(10, 6), pady=(9, 0))
        ttl = tk.Label(card, text=title, bg=bg, fg=TEXT, font=self._font(10, True), anchor='w', justify='left')
        ttl.grid(row=0, column=1, sticky='ew', padx=(0, 8), pady=(8, 0))
        sub = tk.Label(card, text=desc, bg=bg, fg=MUTED, font=self._font(8), anchor='w', justify='left', wraplength=260)
        sub.grid(row=1, column=1, sticky='ew', padx=(0, 8), pady=(1, 8))
        card.columnconfigure(1, weight=1)
        fn = command or (lambda: None)
        for w in (card, icon, ttl, sub):
            w.bind('<Button-1>', lambda e, f=fn: f())
            w.bind('<Enter>', lambda e, c=card: c.configure(highlightbackground=ACCENT, highlightcolor=ACCENT))
            w.bind('<Leave>', lambda e, c=card, b=border: c.configure(highlightbackground=b, highlightcolor=ACCENT))
        return card

    def _fsb_subtile(self, parent, key, title, desc='', active=False, command=None):
        bg = SELECT if active else PANEL
        border = ACCENT if active else BORDER
        card = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=border, highlightcolor=ACCENT, cursor='hand2')
        card.pack_propagate(True)
        ttl = tk.Label(card, text=title, bg=bg, fg=TEXT, font=self._font(9, True), anchor='w', justify='left')
        ttl.pack(anchor='w', padx=10, pady=(7, 1))
        if desc:
            sub = tk.Label(card, text=desc, bg=bg, fg=MUTED, font=self._font(7), anchor='w', justify='left', wraplength=190)
            sub.pack(anchor='w', fill='x', padx=10, pady=(0, 7))
        else:
            ttl.pack(anchor='w', padx=10, pady=7)
        fn = command or (lambda: None)
        for w in card.winfo_children():
            w.bind('<Button-1>', lambda e, f=fn: f())
            w.bind('<Enter>', lambda e, c=card: c.configure(highlightbackground=ACCENT, highlightcolor=ACCENT))
            w.bind('<Leave>', lambda e, c=card, b=border: c.configure(highlightbackground=b, highlightcolor=ACCENT))
        return card

    def show_fsb(self, add_history=True, tab='Обзор', management='М', det_view='Общее', ord_view='Все ОРМ'):
        self._hide_dynamic_bars()
        if add_history:
            self._save_view()
        self._set_active('fsb')
        self.mode = 'fsb'
        self.code = None
        self.law_id = None
        self.article_id = None
        self.codebar.pack_forget()
        self.clear_refs()
        self.clear_tree()
        if hasattr(self, 'detbar'):
            try: self.detbar.destroy()
            except Exception: pass
        if hasattr(self, 'fsbbar'):
            try: self.fsbbar.destroy()
            except Exception: pass

        self._fsb_tab = tab
        self._fsb_management = management
        self._fsb_det_view = det_view
        self._fsb_ord_view = ord_view

        self.fsbbar = tk.Frame(self.mid, bg=PANEL)
        self.fsbbar.pack(fill='x', pady=(0, 8), before=self.tree.master)

        # Search stays compact and persistent. Main navigation is now a set of larger tiles.
        sr = tk.Frame(self.fsbbar, bg=PANEL)
        sr.pack(fill='x', pady=(0, 8))
        tk.Label(sr, text='ФСБ', bg=PANEL, fg=TEXT, font=self._font(12, True)).pack(side='left', padx=(0, 10))
        self.fsb_search_var = tk.StringVar()
        self.fsb_search = tk.Entry(sr, textvariable=self.fsb_search_var, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief='flat', highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT, font=self._font(9))
        self.fsb_search.pack(side='left', fill='x', expand=True, ipady=6)
        self.fsb_search.bind('<KeyRelease>', lambda e: self._refresh_fsb_content())

        nav_title = tk.Frame(self.fsbbar, bg=PANEL)
        nav_title.pack(fill='x')
        tk.Label(nav_title, text='РАЗДЕЛЫ ФСБ', bg=PANEL, fg=MUTED, font=self._font(8, True)).pack(anchor='w')
        self.fsb_nav = tk.Frame(self.fsbbar, bg=PANEL)
        self.fsb_nav.pack(fill='x', pady=(4, 2))
        main_tiles = [
            ('Обзор', 'Обзор', 'Назначение, направления, обязанности и права.'),
            ('Управления', 'Управления', 'М · К · А · О · АПС и их задачи.'),
            ('Полномочия', 'Полномочия', 'Ключевые права и действия сотрудников.'),
            ('Задержание', 'Задержание', 'Перечни статей и процессуальные нормы.'),
            ('Под прикрытием', 'Под прикрытием', 'Сокрытие личности, внедрение и спецмероприятия.'),
            ('ОРД / ОРМ', 'ОРД / ОРМ', 'Мероприятия, оформление и сроки.'),
            ('Контроль', 'Контроль', 'Надзор, государственный контроль и обжалование.'),
        ]
        for i, (key, title, desc) in enumerate(main_tiles):
            r, c = divmod(i, 2)
            self.fsb_nav.columnconfigure(c, weight=1)
            tile = self._fsb_tile(self.fsb_nav, key, title, desc, active=(tab == key), command=lambda x=key: self.show_fsb(add_history=False, tab=x, management=management, det_view=det_view, ord_view=ord_view))
            tile.grid(row=r, column=c, sticky='ew', padx=(0 if c == 0 else 4, 4 if c == 0 else 0), pady=3)

        # Contextual tiles only appear when a section has a second level. No duplicate overflow bars.
        self.fsb_sub = tk.Frame(self.fsbbar, bg=PANEL)
        self.fsb_sub.pack(fill='x', pady=(4, 0))
        subtile_specs = []
        if tab == 'Управления':
            subtile_specs = [(k, k, d, management == k, lambda x=k: self.show_fsb(add_history=False, tab='Управления', management=x, det_view=det_view, ord_view=ord_view)) for k, _, d, _, _ in self.FSB_MANAGEMENTS]
        elif tab == 'Задержание':
            labels = {'Общее':'Все применимые составы по ПК 13.2', 'М':'Спецперечень управления М', 'К':'Спецперечень управления К', 'Передача в ФСБ':'Передача задержанного сотрудникам ФСБ'}
            subtile_specs = [(k, k, labels.get(k,''), det_view == k, lambda x=k: self.show_fsb(add_history=False, tab='Задержание', management=management, det_view=x, ord_view=ord_view)) for k in ['Общее','М','К','Передача в ФСБ']]
        elif tab == 'ОРД / ОРМ':
            labels = {'Все ОРМ':'14 мероприятий', 'Кто подписывает':'Поручение и постановление', 'Сроки':'Временные рамки', 'Основания / прикрытие':'Оформление и сокрытие личности', 'М':'Специфика управления М', 'К':'Специфика управления К'}
            subtile_specs = [(k, k, labels[k], ord_view == k, lambda x=k: self.show_fsb(add_history=False, tab='ОРД / ОРМ', management=management, det_view=det_view, ord_view=x)) for k in labels]
        if subtile_specs:
            tk.Label(self.fsb_sub, text='ВНУТРИ РАЗДЕЛА', bg=PANEL, fg=MUTED, font=self._font(8, True)).pack(anchor='w')
            grid = tk.Frame(self.fsb_sub, bg=PANEL)
            grid.pack(fill='x', pady=(3, 0))
            for i, (key, title, desc, active, fn) in enumerate(subtile_specs):
                c = i % 3
                r = i // 3
                grid.columnconfigure(c, weight=1)
                tile = self._fsb_subtile(grid, key, title, desc, active=active, command=fn)
                tile.grid(row=r, column=c, sticky='ew', padx=(0, 3 if c < 2 else 0), pady=3)

        self._render_fsb_tab()
        self.status.configure(text=f'ФСБ · {tab}')
        self._update_back()

    def _fsb_ref(self, code, num, label=None):
        if code == 'ФЗ':
            found = self.db.find_law_ref('федеральной службе безопасности', num)
        else:
            found = self.db.find_ref(code, num)
        text = label or f'{code} · ст. {num}'
        if found:
            tag = f'fsb_ref_{code}_{num}_{time.time_ns()}'
            self.reader.insert('end', text, ('ref', tag))
            self.reader.tag_bind(tag, '<Button-1>', lambda e, a=found[0]: self.open_article(a))
        else:
            self.reader.insert('end', text, 'body')

    def _fsb_set_reader(self, title, meta, sections):
        self.rtitle.configure(text=title)
        self.meta.configure(text=meta)
        self.clear_crumbs()
        self.crumb('ФСБ', lambda: self.show_fsb(add_history=False, tab=self._fsb_tab, management=self._fsb_management, det_view=self._fsb_det_view, ord_view=self._fsb_ord_view))
        self.crumb(title, None, active=True)
        self.reader.configure(state='normal')
        self.reader.delete('1.0', 'end')
        self.reader.insert('end', title + '\n\n', 'head')
        for sec_title, paras, refs in sections:
            self.reader.insert('end', sec_title.upper() + '\n', 'subhead')
            for para in paras:
                self.reader.insert('end', para + '\n', 'body')
            if refs:
                self.reader.insert('end', 'Нормы: ', 'body')
                for idx, (c, n) in enumerate(refs):
                    self._fsb_ref(c, n)
                    if idx < len(refs) - 1:
                        self.reader.insert('end', '   ', 'body')
                self.reader.insert('end', '\n')
            self.reader.insert('end', '\n', 'body')
        self.reader.configure(state='disabled')
        bottom = []
        for _, _, refs in sections:
            bottom.extend(refs)
        self.clear_refs()
        seen = set()
        for c, n in bottom[:20]:
            key = (c, n)
            if key in seen:
                continue
            seen.add(key)
            if c == 'ФЗ':
                found = self.db.find_law_ref('федеральной службе безопасности', n)
            else:
                found = self.db.find_ref(c, n)
            b = tk.Button(self.refs_inner, text=f'{c} · ст. {n}', bg=FIELD, fg=ACCENT if found else MUTED, activebackground=SELECT, activeforeground=TEXT, relief='flat', bd=0, font=self._font(8), padx=7, pady=3, command=(lambda a=found[0]: self.open_article(a)) if found else lambda cc=c, nn=n: self.jump_ref(cc, nn))
            b.pack(side='left', padx=2, pady=2)

    def _render_fsb_tab(self):
        self.clear_tree()
        self.clear_refs()
        self.tree.heading('#0', text='Раздел')
        q = self.fsb_search_var.get().strip().lower() if hasattr(self, 'fsb_search_var') else ''
        tab = self._fsb_tab
        if tab == 'Обзор':
            rows = [('Foverview', 'Назначение'), ('Fdirection', 'Направления деятельности'), ('Fduties', 'Обязанности органов'), ('Frights', 'Права органов')]
            for iid, label in rows:
                self.tree.insert('', 'end', iid=iid, text=label, tags=('article',))
            self.center_title.configure(text='ФСБ')
            self.center_hint.configure(text='Обзор функций и прав · без смешивания со структурами и процессом')
            if not q:
                self._fsb_item_detail('overview')
        elif tab == 'Управления':
            self.center_title.configure(text=f'ФСБ · Управление «{self._fsb_management}»')
            self.center_hint.configure(text='Каждое управление — отдельная вкладка')
            data = {k: (label, desc) for k, label, desc, _, _ in self.FSB_MANAGEMENTS}[self._fsb_management]
            self.tree.insert('', 'end', iid=f'Fmg_{self._fsb_management}', text=data[0], tags=('article',))
            if not q:
                self._fsb_item_detail('management', self._fsb_management)
        elif tab == 'Полномочия':
            # Ст. 12 ФЗ — один источник, 14 самостоятельных пунктов. Показываем их плоским,
            # но читаемым списком; каждая строка раскрывает конкретный пункт, без смешения норм.
            rows = [
                ('Fpower1', 'Конфиденциальное сотрудничество', 'п. 1'),
                ('Fpower2', 'Дознание и предварительное следствие', 'п. 2'),
                ('Fpower3', 'Административные производства', 'п. 3'),
                ('Fpower4', 'Ограничение движения', 'п. 4'),
                ('Fpower5', 'Проверка документов', 'п. 5'),
                ('Fpower6', 'Изучение документов и материалов', 'п. 6'),
                ('Fpower7', 'Экспертизы и исследования', 'п. 7'),
                ('Fpower8', 'Меры собственной безопасности', 'п. 8'),
                ('Fpower9', 'Задержание и обыск', 'п. 9'),
                ('Fpower10', 'Сила, оружие и спецсредства', 'п. 10'),
                ('Fpower11', 'Летальное огнестрельное оружие', 'п. 11'),
                ('Fpower12', 'Сокрытие принадлежности для М / К', 'п. 12'),
                ('Fpower13', 'Изъятие ограниченных предметов', 'п. 13'),
                ('Fpower14', 'Обязательные законные требования', 'п. 14'),
            ]
            for iid, label, part in rows:
                self.tree.insert('', 'end', iid=iid, text=f'{label}   ·   {part}', tags=('article',))
            self.center_title.configure(text='ФСБ · Полномочия')
            self.center_hint.configure(text='ФЗ · статья 12 · 14 отдельных полномочий')
            if not q:
                self._fsb_item_detail('power', 'Fpower1')
        elif tab == 'Задержание':
            title, nums, ref = self.FSB_DETENTION_LISTS[self._fsb_det_view]
            self.center_title.configure(text=f'ФСБ · {title}')
            self.center_hint.configure(text=f'Источник: {ref} · {len(nums)} уголовных статей')
            for n in nums:
                found = self.db.find_ref('УК', n)
                if found:
                    self.tree.insert('', 'end', iid=f'A{found[0]}', text=f'УК {n}', tags=('article',))
                else:
                    self.tree.insert('', 'end', iid=f'Fmissing_{n}', text=f'УК {n}   ·   нет статьи в локальном тексте УК', tags=('dim',))
            self._fsb_det_detail(self._fsb_det_view)
        elif tab == 'Под прикрытием':
            rows = [('Fcover1', 'Что считается работой под прикрытием'), ('Fcover2', 'Кто может скрывать личность'), ('Fcover3', 'Контрольная закупка и внедрение'), ('Fcover4', 'Порядок оформления ОРМ'), ('Fcover5', 'Что происходит после ОРМ')]
            for iid, label in rows:
                self.tree.insert('', 'end', iid=iid, text=label, tags=('article',))
            self.center_title.configure(text='ФСБ · Под прикрытием')
            self.center_hint.configure(text='Сокрытие личности, внедрение, контрольные закупки и оформление ОРМ')
            if not q:
                self._fsb_item_detail('cover', 'Fcover1')
        elif tab == 'ОРД / ОРМ':
            self.center_title.configure(text=f'ФСБ · {self._fsb_ord_view}')
            self.center_hint.configure(text='ОРД — деятельность; ОРМ — отдельное мероприятие')
            if self._fsb_ord_view == 'Все ОРМ':
                for num, label, desc in self.FSB_ORM:
                    self.tree.insert('', 'end', iid=f'Form_{num}', text=f'{num}  {label}', tags=('article',))
                self._fsb_item_detail('orm', 'all')
            else:
                rows = {'Кто подписывает': [('Form_sign', 'Инициализация и подписание', '65-3 / 65-5')], 'Сроки': [('Form_time', 'Сроки проведения ОРМ', '65-4')], 'Основания / прикрытие': [('Form_cover', 'Сокрытие личности и режим прикрытия', '65-1 / 65-3')], 'М': [('Form_M', 'ОРМ управления «М»', '65-1.1 / 65-5.4')], 'К': [('Form_K', 'ОРМ управления «К»', '65-1.1 / 24 ФЗ')]}[self._fsb_ord_view]
                for iid, label, sub in rows:
                    self.tree.insert('', 'end', iid=iid, text=f'{label}  ·  {sub}', tags=('article',))
                self._fsb_item_detail('orm', self._fsb_ord_view)
        elif tab == 'Контроль':
            rows = [('Fcontrol1', 'Судебный и прокурорский надзор'), ('Fcontrol2', 'Государственный контроль'), ('Fcontrol3', 'Обжалование действий сотрудников')]
            for iid, label in rows:
                self.tree.insert('', 'end', iid=iid, text=label, tags=('article',))
            self.center_title.configure(text='ФСБ · Контроль')
            self.center_hint.configure(text='Надзор и порядок обжалования')
            if not q:
                self._fsb_item_detail('control', 'Fcontrol1')
        if q:
            self._filter_fsb_tree(q)

    def _refresh_fsb_content(self):
        self._render_fsb_tab()

    def _filter_fsb_tree(self, q):
        for iid in list(self.tree.get_children()):
            label = self.tree.item(iid, 'text').lower()
            if q not in label:
                self.tree.delete(iid)
        self.placeholder(f'Фильтр ФСБ: {q}')

    def select_fsb_item(self, key):
        if key.startswith('Fmg_'):
            self.show_fsb(add_history=False, tab='Управления', management=key[4:])
            return
        if key.startswith('Form_'):
            sub = key[5:]
            if sub.isdigit():
                item = next((x for x in self.FSB_ORM if x[0] == sub), None)
                if item:
                    self._fsb_set_reader(f'ОРМ {item[0]} · {item[1]}', 'УПК · ст. 65', [('Суть', [item[2] + '.'], [('УПК', '65')])])
                return
            self._fsb_item_detail('orm', {'sign': 'Кто подписывает', 'time': 'Сроки', 'cover': 'Основания / прикрытие', 'M': 'М', 'K': 'К'}.get(sub, sub))
            return
        if key.startswith('Fpower'):
            self._fsb_item_detail('power', key)
            return
        if key.startswith('Fcover'):
            self._fsb_item_detail('cover', key)
            return
        if key.startswith('Fcontrol'):
            self._fsb_item_detail('control', key)
            return
        if key.startswith('Fmissing_'):
            num = key.split('_', 1)[1]
            self._fsb_set_reader(f'УК {num}', 'Ссылка из ПК · статья не найдена в локальном тексте УК', [('Проверка', [f'ПК ссылается на статью УК {num}, но отдельная статья с таким номером отсутствует в текущем локальном тексте Уголовного кодекса.'], [('ПК', '16.2') if self._fsb_det_view == 'К' else ('ПК', '16.1')])])
            return
        if key in ('Foverview', 'Fdirection', 'Fduties', 'Frights'):
            data = {'Foverview': ('Назначение ФСБ', ['Единая централизованная система органов безопасности; деятельность направлена на обеспечение безопасности Российской Федерации и защиту прав и свобод человека и гражданина.'], [('ФЗ', '1')]), 'Fdirection': ('Направления деятельности', ['Терроризм · экстремизм · коррупция · незаконный оборот оружия и наркотрафик · организованная преступность.'], [('ФЗ', '6')]), 'Fduties': ('Обязанности органов ФСБ', ['Выявление, предупреждение, пресечение и раскрытие преступлений; дознание и предварительное следствие; пресечение административных правонарушений; розыск.'], [('ФЗ', '11')]), 'Frights': ('Права органов ФСБ', ['Дознание и следствие; административные производства; проверка документов; ограничение движения; задержание и обыск; применение силы и оружия; изъятие.'], [('ФЗ', '12')])}
            title, paras, refs = data[key]
            self._fsb_set_reader(title, 'ФЗ · обзор', [('Содержание', paras, refs)])
            return
        self._fsb_item_detail('tree', key)

    def _fsb_item_detail(self, kind, key=None):
        if kind == 'overview':
            self._fsb_set_reader('Федеральная служба безопасности', 'ФЗ · общая характеристика', [('Назначение', ['Единая централизованная система органов безопасности; деятельность направлена на обеспечение безопасности и защиту прав и свобод от преступных и иных посягательств.'], [('ФЗ', '1')]), ('Направления', ['Терроризм · экстремизм · коррупция · незаконный оборот оружия и наркотрафик · организованная преступность.'], [('ФЗ', '6')])])
        elif kind == 'management':
            self._fsb_management_detail(key)
        elif kind == 'power':
            powers = {
                'Fpower1': ('Конфиденциальное сотрудничество', 'Устанавливать на конфиденциальной основе отношения сотрудничества с лицами, давшими на то согласие.', [('ФЗ', '12')]),
                'Fpower2': ('Дознание и предварительное следствие', 'Осуществлять дознание и предварительное следствие в соответствии с уголовно-процессуальным законодательством.', [('ФЗ', '12')]),
                'Fpower3': ('Административные производства', 'Составлять протоколы об административных правонарушениях, выносить определения и постановления, назначать административные наказания и осуществлять иные полномочия по делам об административных правонарушениях.', [('ФЗ', '12')]),
                'Fpower4': ('Ограничение движения', 'Временно ограничивать или запрещать передвижение граждан и транспортных средств в установленных законом целях.', [('ФЗ', '12')]),
                'Fpower5': ('Проверка документов', 'Проверять у лиц документы, удостоверяющие их личность.', [('ФЗ', '12')]),
                'Fpower6': ('Изучение документов и материалов', 'Знакомиться с необходимыми документами и материалами, включая персональные данные граждан, имеющими отношение к расследованию и производству по делам об административных правонарушениях.', [('ФЗ', '12')]),
                'Fpower7': ('Экспертизы и исследования', 'Проводить криминалистические и другие экспертизы и исследования.', [('ФЗ', '12')]),
                'Fpower8': ('Меры собственной безопасности', 'Осуществлять меры по обеспечению собственной безопасности.', [('ФЗ', '12')]),
                'Fpower9': ('Задержание и обыск', 'Производить задержание, обыск и другие действия согласно процессуальному законодательству.', [('ФЗ', '12'), ('ПК', '13')]),
                'Fpower10': ('Сила, оружие и спецсредства', 'Применять боевую технику, оружие, специальные средства и физическую силу, а также разрешать сотрудникам ФСБ хранение и ношение табельного оружия и специальных средств.', [('ФЗ', '12')]),
                'Fpower11': ('Летальное огнестрельное оружие', 'Применять летальное огнестрельное оружие в случаях возникновения угрозы жизни гражданским и иным лицам или риска сокрытия подозреваемого.', [('ФЗ', '12')]),
                'Fpower12': ('Сокрытие принадлежности для М / К', 'Разрешать сотрудникам первой и второй оперативно-следственных служб использовать форму и транспорт без знаков принадлежности к ФСБ в целях наблюдения, переговоров, задержания и проведения специальных операций (ОРМ) в установленном порядке.', [('ФЗ', '12'), ('УПК', '65-1')]),
                'Fpower13': ('Изъятие ограниченных предметов', 'Изымать у граждан и должностных лиц вещи, изъятые из гражданского оборота или ограниченно оборотоспособные, находящиеся у них без специального разрешения.', [('ФЗ', '12')]),
                'Fpower14': ('Обязательные законные требования', 'Выдвигать обязательные к исполнению законные требования в порядке, предусмотренном законодательством.', [('ФЗ', '12')]),
            }
            title, desc, refs = powers.get(key, powers['Fpower1'])
            self._fsb_set_reader(title, 'ФЗ · статья 12 · п. ' + key.replace('Fpower', ''), [('Полномочие', [desc], refs)])
        elif kind == 'cover':
            self._fsb_cover_detail(key)
        elif kind == 'orm':
            self._fsb_orm_detail(key)
        elif kind == 'control':
            controls = {'Fcontrol1': ('Судебный и прокурорский надзор', [('ФЗ', '32')]), 'Fcontrol2': ('Государственный контроль', [('ФЗ', '33')]), 'Fcontrol3': ('Обжалование действий сотрудников', [('ФЗ', '34')])}
            title, refs = controls.get(key, controls['Fcontrol1'])
            self._fsb_set_reader(title, 'ФЗ · контроль', [('Норма', ['Раздел показывает только соответствующую процедуру без смешивания с полномочиями и структурами.'], refs)])
        else:
            self._fsb_set_reader('ФСБ', 'Выберите пункт слева', [('Подсказка', ['Для управления, полномочия, задержания и ОРМ используйте отдельные вкладки сверху.'], [])])

    def _fsb_management_detail(self, key):
        if key == 'М':
            sections = [('Назначение', ['Следственная и инспекторская деятельность. Также антикоррупционная работа.'], [('ФЗ', '18')]), ('Полномочия', ['Следствие по подследственным делам ФСБ, экспертизы и исследования, инспекции правоохранительных органов, возбуждение уголовных дел в пределах подследственности.'], [('ФЗ', '20')]), ('Задержание', ['Специальный перечень уголовных статей закреплён в ПК 16.1.'], [('ПК', '16.1')]), ('Под прикрытием', ['Для определённых ОРМ М может скрывать личность при наличии предусмотренного поручения; по отдельной норме М может проводить ряд ОРМ без поручения в рамках возбужденного уголовного дела.'], [('УПК', '65-1'), ('УПК', '65-5')])]
        elif key == 'К':
            sections = [('Назначение', ['Следственная деятельность и контроль за оборотом наркотиков, оружия и контрабанды.'], [('ФЗ', '23')]), ('Полномочия', ['Контрольные закупки, рейды, контроль оборота наркосодержащих препаратов, внедрения и следствие.'], [('ФЗ', '25')]), ('Задержание', ['Специальный перечень уголовных статей закреплён в ПК 16.2.'], [('ПК', '16.2')]), ('Под прикрытием', ['Сотрудники К могут проводить контрольные закупки, внедрения и иные мероприятия с сокрытием принадлежности; удостоверение должно быть при сотруднике.'], [('ФЗ', '24'), ('УПК', '65-1')])]
        elif key == 'А':
            sections = [('Назначение', ['Основное силовое подразделение по защите конституционного строя, борьбе с терроризмом и экстремизмом.'], [('ФЗ', '26')]), ('Полномочия', ['Антитеррористические операции, силовое сопровождение ОРД и следственных мероприятий, переговоры и освобождение заложников, задержание и арест террористов и особо опасных преступников.'], [('ФЗ', '26'), ('ФЗ', '27')]), ('Задержание', ['В просмотренном корпусе отдельного перечня УК для А по номеру управления нет. Для передачи задержанного в ФСБ используется перечень ПК 13.3: 53, 55, 72–75, 78.'], [('ПК', '13.3')])]
        elif key == 'О':
            sections = [('Назначение', ['Организационно-кадровая работа и организация деятельности Академии ФСБ.'], [('ФЗ', '28')]), ('Задержание', ['В просмотренном корпусе специальный перечень уголовных статей для Управления «О» не установлен.'], [])]
        else:
            sections = [('Назначение', ['Прикомандирование сотрудников к государственным организациям, наблюдение, контроль и выполнение особых поручений.'], [('ФЗ', '29')]), ('Полномочия', ['Прикомандированный сотрудник сохраняет службу в ФСБ, получает полномочия прикомандированной организации и может направлять рапорты о нарушениях.'], [('ФЗ', '30'), ('ФЗ', '31')]), ('Задержание', ['В просмотренном корпусе отдельный перечень уголовных статей для АПС не установлен.'], [])]
        self._fsb_set_reader(f'Управление «{key}»', 'ФСБ · профиль управления', sections)

    def _fsb_det_detail(self, key):
        title, nums, ref = self.FSB_DETENTION_LISTS[key]
        text = [f'Вкладка содержит только уголовные составы, перечисленные в {ref}.', 'Нажатие на номер статьи открывает её полный текст в УК.']
        if key == 'Передача в ФСБ':
            text.append('Здесь показаны составы, по которым задержание передаётся сотрудникам ФСБ.')
        refs = [('ПК', ref.split()[-1])]
        self._fsb_set_reader(title, 'ФСБ · задержание', [('Как читать', text, refs)])

    def _fsb_cover_detail(self, key):
        data = {'Fcover1': ('Работа под прикрытием', ['В вашем корпусе она описывается через сокрытие причастности к ФСБ при определённых оперативно-розыскных мероприятиях. Это не отдельный универсальный режим для всех действий.'], [('ФЗ', '5'), ('УПК', '65-1')]), 'Fcover2': ('Кто может скрывать личность', ['УПК прямо выделяет сотрудников управлений «К» и «М» ФСБ для сокрытия личности при ОРМ, перечисленных в ст. 65, если это установлено поручением. По первому требованию следователя СК или прокуратуры удостоверение предъявляется.'], [('УПК', '65-1')]), 'Fcover3': ('Контрольная закупка и внедрение', ['Контрольная закупка/контролируемая поставка и оперативное внедрение входят в перечень ОРМ. Для К и М предусмотрены специальные правила; ФЗ о ФСБ отдельно описывает контрольные закупки и внедрения для К.'], [('УПК', '65'), ('ФЗ', '24'), ('ФЗ', '25')]), 'Fcover4': ('Оформление ОРМ', ['ОРД инициируется письменным поручением или постановлением. Для отдельных ОРМ документ должен указывать конкретного сотрудника. Обычное поручение может быть не опубликовано до проведения, но после мероприятия должно быть доступно в установленный срок.'], [('УПК', '65-3')]), 'Fcover5': ('После ОРМ', ['Для М и К действия, на которые распространяется специальная защита, должны быть строго сформулированы и обоснованы в рамках конкретного ОРМ; выход за его цели и пределы прекращает специальную защиту.'], [('УПК', '65-2'), ('УПК', '65-3')])}
        title, paras, refs = data[key]
        self._fsb_set_reader(title, 'ФСБ · под прикрытием', [('Порядок', paras, refs)])

    def _fsb_orm_detail(self, key):
        if key == 'all':
            paras = [f'{num}. {label} — {desc}.' for num, label, desc in self.FSB_ORM]
            self._fsb_set_reader('ОРМ · полный перечень', 'УПК 65.1', [('14 мероприятий', paras, [('УПК', '65')])])
            return
        data = {'Кто подписывает': ('Кто подписывает поручение / постановление', ['Поручение: начальник регионального подразделения ФСБ/ФСИН/угрозыска/собственной безопасности МВД или руководитель территориального ОВД. Постановление: руководитель следственного органа или следователь СК.'], [('УПК', '65-5')]), 'Сроки': ('Сроки ОРМ', ['Обычное ОРМ — до 5 часов; в исключительном случае с санкцией прокурора — до 12 часов. Для ОРМ 1,2,5,6,9,10,12 — до 3 суток, с санкцией прокурора — до 7 суток.'], [('УПК', '65-4')]), 'Основания / прикрытие': ('Основания и прикрытие', ['ОРД инициируется письменным поручением или постановлением. Для ОРМ 4,6,12,14 документ оформляется на конкретного сотрудника; распределение на службу или группу не допускается.'], [('УПК', '65-3')]), 'М': ('ОРМ управления «М»', ['УПК позволяет следователю управления «М» проводить ряд ОРМ без отдельного поручения в рамках возбужденного уголовного дела: п.1,2,3,5,7 ч.1 ст.65. Для определённых ОРМ действует режим сокрытия личности.'], [('УПК', '65-5'), ('УПК', '65-1')]), 'К': ('ОРМ управления «К»', ['Управление «К» проводит контрольные закупки, внедрения и другие мероприятия с сокрытием принадлежности в предусмотренном порядке. Удостоверение должно присутствовать у сотрудника.'], [('ФЗ', '24'), ('ФЗ', '25'), ('УПК', '65-1')])}
        title, paras, refs = data[key]
        self._fsb_set_reader(title, 'ФСБ · ОРД / ОРМ', [('Правила', paras, refs)])

    def open_command_palette(self, event=None):
        win = tk.Toplevel(self)
        win.title('Командная палитра')
        win.geometry('640x500')
        win.minsize(540, 420)
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        outer = tk.Frame(win, bg=BG)
        outer.pack(fill='both', expand=True, padx=16, pady=14)
        tk.Label(outer, text='Командная палитра', bg=BG, fg=TEXT, font=self._font(18, True)).pack(anchor='w')
        tk.Label(outer, text='Ctrl+K · поиск по статьям, разделам и инструментам', bg=BG, fg=MUTED, font=self._font(8)).pack(anchor='w', pady=(2, 8))
        q = tk.StringVar()
        ent = tk.Entry(outer, textvariable=q, bg=FIELD, fg=TEXT, insertbackground=TEXT, selectbackground=SELECT, relief='flat', highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT, font=self._font(10))
        ent.pack(fill='x', ipady=8)
        ent.focus_set()
        tree = tk.Listbox(outer, bg=FIELD, fg=TEXT, selectbackground=SELECT, selectforeground=TEXT, relief='flat', highlightthickness=0, font=self._font(9), activestyle='none')
        tree.pack(fill='both', expand=True, pady=(10, 0))
        commands = [('Порядок задержания', lambda: self.show_detention()), ('УК', lambda: self.show_uk()), ('КоАП', lambda: self.show_koap()), ('ПК', lambda: self.open_by_title('процессуальный кодекс')), ('УПК', lambda: self.open_by_title('уголовно-процессуальный кодекс')), ('ФСБ', lambda: self.show_fsb()), ('Закладки', lambda: self.show_bookmarks()), ('История', lambda: self.show_recent()), ('Законодательная база', lambda: self.show_home()), ('Настройки', lambda: self.open_settings())]

        def refresh(*_):
            tree.delete(0, 'end')
            term = q.get().strip().lower()
            hits = []
            if term:
                hits = [(i, label, fn) for i, (label, fn) in enumerate(commands) if term in label.lower()]
                for row in self.db.search(term)[:30]:
                    _score, aid, lid, at, body, lt, num = row
                    hits.append((1000 + aid, f'{lt} · {at}', lambda a=aid: self.open_article(a)))
            else:
                hits = [(i, label, fn) for i, (label, fn) in enumerate(commands)]
            dedup=[]; seen=set()
            for item in hits:
                key=item[1]
                if key in seen: continue
                seen.add(key); dedup.append(item)
            self._palette_hits = dedup
            for _, label, _ in dedup:
                tree.insert('end', label)

        def run(_=None):
            sel = tree.curselection()
            if not sel:
                return
            _, label, fn = self._palette_hits[sel[0]]
            win.destroy()
            self.after(20, fn)
        q.trace_add('write', refresh)
        tree.bind('<Double-1>', run)
        tree.bind('<Return>', run)
        ent.bind('<Return>', lambda e: (tree.focus_set(), run()))
        refresh()
        win.bind('<Escape>', lambda e: (win.destroy(), 'break')[-1])

    def open_article_window(self):
        if not self.article_id:
            return
        row = self.db.article(self.article_id)
        if not row:
            return
        win = tk.Toplevel(self)
        win.title(f'{row[2]} · Юридический помощник')
        win.geometry('900x720')
        win.configure(bg=BG)
        tk.Label(win, text=row[2], bg=BG, fg=TEXT, font=self._font(17, True)).pack(anchor='w', padx=16, pady=(14, 4))
        tk.Label(win, text=f"{row[4]} · {row[8]} · {row[7] or '—'}", bg=BG, fg=MUTED, font=self._font(8)).pack(anchor='w', padx=16)
        txt = ScrolledText(win, wrap='word', bg=READER, fg=TEXT, insertbackground=TEXT, selectbackground=SELECT, relief='flat', font=self._font(10), padx=24, pady=20)
        txt.pack(fill='both', expand=True, padx=16, pady=12)
        txt.insert('1.0', f"{row[2]}\n\n{row[3] or ''}")
        txt.tag_configure('head', font=self._font(15, True), foreground=TEXT)
        txt.configure(state='disabled')

    def export_settings(self):
        p = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json')], title='Экспорт настроек')
        if p:
            Path(p).write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding='utf-8')
            self.status.configure(text='Настройки экспортированы')

    def import_settings(self):
        p = filedialog.askopenfilename(filetypes=[('JSON', '*.json')], title='Импорт настроек')
        if not p:
            return
        try:
            data = json.loads(Path(p).read_text(encoding='utf-8'))
            new = copy.deepcopy(DEFAULT_SETTINGS)
            new.update(data or {})
            self.settings = new
            save_settings(SETTINGS_PATH, new)
            self.theme = new.get('theme', 'azure')
            self.font_scale = float(new.get('font_scale', 1.0))
            self._rebuild_after_settings(close_window=True, reopen=False)
            messagebox.showinfo('Настройки', 'Настройки импортированы.', parent=self)
        except Exception as e:
            messagebox.showerror('Импорт настроек', str(e), parent=self)

    def _refresh_workspace_tabs(self):
        if not hasattr(self,'workspacebar'): return
        for w in self.workspacebar.winfo_children(): w.destroy()
        for aid,title in self._workspace.items():
            active=(aid==self.article_id)
            b=tk.Button(self.workspacebar,text=('• ' if active else '')+title,bg=SELECT if active else FIELD,fg=TEXT if active else MUTED,activebackground=SELECT,activeforeground=TEXT,relief='flat',bd=0,font=self._font(8),padx=7,pady=3,command=lambda a=aid:self.open_workspace_tab(a))
            b.pack(side='left',padx=(0,2))
            x=tk.Button(self.workspacebar,text='×',bg=SELECT if active else FIELD,fg=MUTED,activebackground=SELECT,activeforeground=TEXT,relief='flat',bd=0,font=self._font(8),padx=3,pady=3,command=lambda a=aid:self.close_workspace_tab(a))
            x.pack(side='left',padx=(0,4))

    def _add_workspace_tab(self,aid):
        row=self.db.article(aid)
        if not row:return
        num=self.db.article_number(row[2])
        label=(f'{num} · '+re.sub(r'^Статья\s+','',row[2],flags=re.I)) if num else row[2]
        self._workspace[aid]=label[:44]
        while len(self._workspace)>8:
            oldest=next(iter(self._workspace))
            if oldest==aid: break
            self._workspace.pop(oldest,None)
        self._refresh_workspace_tabs()

    def open_workspace_tab(self,aid):
        try:self.open_article(int(aid),add_history=False)
        except Exception:pass

    def close_workspace_tab(self,aid):
        try:aid=int(aid)
        except Exception:return
        self._workspace.pop(aid,None)
        if self.article_id==aid:
            if self._workspace:self.open_workspace_tab(next(reversed(self._workspace)))
            else:self.placeholder()
        else:self._refresh_workspace_tabs()

    def show_uk(self, add_history=True):
        self._set_active('uk')
        return self.show_code('УК', add_history=add_history)

    def show_koap(self, add_history=True):
        self._set_active('koap')
        return self.show_code('КоАП', add_history=add_history)

    def select_tree(self, e=None):
        if getattr(self, '_tree_lock', False):
            return
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid.startswith('L'):
            self.open_doc(int(iid[1:]))
        elif iid.startswith('A'):
            self.open_article(int(iid[1:]))
        elif iid.startswith('F'):
            self.select_fsb_item(iid)
        elif iid.startswith('D'):
            self.select_detention_step(iid[1:])
        elif iid.startswith('W'):
            self.open_workspace_tab(iid[1:])

    def _save_view(self):
        if self._restoring:
            return
        self._save_reader_position()
        snap = {'mode': self.mode, 'code': self.code, 'law_id': self.law_id, 'article_id': self.article_id, 'q': self.q.get(), 'code_search': self.code_search.get(), 'code_filter': self.code_filter_var.get(), 'fsb_tab': getattr(self, '_fsb_tab', 'Обзор'), 'fsb_management': getattr(self, '_fsb_management', 'М'), 'fsb_det_view': getattr(self, '_fsb_det_view', 'Общее'), 'fsb_ord_view': getattr(self, '_fsb_ord_view', 'Все ОРМ'), 'det_step': getattr(self, '_det_step', '01')}
        if self._history and self._history[-1] == snap:
            return
        self._history.append(snap)
        self._forward_history = []
        self._last_view = snap

    def render_article(self, row):
        body = row[3] or ''
        self.reader.configure(state='normal')
        self.reader.delete('1.0', 'end')
        self.reader.insert('end', row[2] + '\n\n', 'head')
        ref_pattern = re.compile('(?i)\\b(УК|КоАП|ПК|УПК|ТК|БК|ИК)\\b\\s*(?:ст\\.?|статья|статьи)?\\s*(\\d+(?:\\.\\d+)*|\\d+-\\d+)|(?i:ст\\.?|статья|статьи)\\s*(\\d+(?:\\.\\d+)*|\\d+-\\d+)\\s*\\b(УК|КоАП|ПК|УПК|ТК|БК|ИК)\\b')
        sanction_re = re.compile('(?i)\\b(?:наказыва(?:ется|ются)|влеч(?:ет|ёт)\\s+наложение|влеч(?:ет|ёт)\\s+административн|штраф[а-яё]*\\s+в\\s+размере|назнача(?:ется|ются)\\s+наказани)')
        ref_i = 0
        for line in body.splitlines(True):
            pos = 0
            for m in ref_pattern.finditer(line):
                before = line[pos:m.start()]
                if before:
                    self.reader.insert('end', before, 'measure' if self.settings.get('show_sanctions', True) and sanction_re.search(before) else 'body')
                g1, g2, g3, g4 = (m.group(1), m.group(2), m.group(3), m.group(4))
                if g1:
                    code, num = (g1.upper(), g2)
                else:
                    code, num = (g4.upper(), g3)
                tag = f'ref_{ref_i}'
                ref_i += 1
                self.reader.insert('end', m.group(0), ('ref', tag))
                self.reader.tag_bind(tag, '<Button-1>', lambda e, c=code, n=num: self.jump_ref(c, n))
                pos = m.end()
            tail = line[pos:]
            if tail:
                self.reader.insert('end', tail, 'measure' if self.settings.get('show_sanctions', True) and sanction_re.search(tail) else 'body')
        self.reader.configure(state='disabled')

    def _state_snapshot(self):
        return {
            'mode':self.mode,'code':self.code,'law_id':self.law_id,'article_id':self.article_id,
            'q':self.q.get(),'code_search':self.code_search.get(),'code_filter':self.code_filter_var.get(),
            'fsb_tab':getattr(self,'_fsb_tab','Обзор'),'fsb_management':getattr(self,'_fsb_management','М'),
            'fsb_det_view':getattr(self,'_fsb_det_view','Общее'),'fsb_ord_view':getattr(self,'_fsb_ord_view','Все ОРМ'),
            'det_step':getattr(self,'_det_step','01')
        }

    def _restore_snapshot(self,snap):
        mode=snap.get('mode')
        if mode=='articles' and snap.get('law_id'): self.open_doc(snap['law_id'],add_history=False)
        elif mode=='code' and snap.get('code'):
            self.show_code(snap['code'],add_history=False,submode=snap.get('code_filter'))
            self.code_search.set(snap.get('code_search','')); self.refresh_code()
        elif mode=='search' and snap.get('q'):
            self.search_placeholder=False; self.q.set(snap['q']); self.global_search(add_history=False)
        elif mode=='fsb':
            self.show_fsb(add_history=False,tab=snap.get('fsb_tab','Обзор'),management=snap.get('fsb_management','М'),det_view=snap.get('fsb_det_view','Общее'),ord_view=snap.get('fsb_ord_view','Все ОРМ'))
        elif mode=='detention':
            self.show_detention(add_history=False); self.select_detention_step(snap.get('det_step','01'))
        elif mode=='bookmarks': self.show_bookmarks(add_history=False)
        elif mode=='recent': self.show_recent(add_history=False)
        elif mode=='home': self.show_home(add_history=False)
        elif mode=='article' and snap.get('article_id'): self.open_article(snap['article_id'],add_history=False)
        else: self.show_home(add_history=False)

    def go_back(self):
        if not self._history:return
        current=self._state_snapshot(); snap=self._history.pop()
        self._forward_history.append(current)
        self._restoring=True
        try:self._restore_snapshot(snap)
        finally:
            self._restoring=False; self._update_back(); self._update_forward()

    def go_forward(self):
        if not self._forward_history:return
        current=self._state_snapshot(); snap=self._forward_history.pop()
        self._history.append(current)
        self._restoring=True
        try:self._restore_snapshot(snap)
        finally:
            self._restoring=False; self._update_back(); self._update_forward()

    def _update_back(self):
        if hasattr(self,'back_button'):self.back_button.configure(state='normal' if self._history else 'disabled')

    def _update_forward(self):
        if hasattr(self,'forward_button'):self.forward_button.configure(state='normal' if self._forward_history else 'disabled')
