from __future__ import annotations
import re, sqlite3, time, json
from pathlib import Path
from .parser import parse_document

CODE_ALIASES={
    'УК':'уголовный кодекс','КоАП':'кодекс об административных правонарушениях','КОАП':'кодекс об административных правонарушениях',
    'ПК':'процессуальный кодекс','УПК':'уголовно-процессуальный кодекс','ТК':'трудовой кодекс','БК':'бюджетный кодекс','ИК':'избирательный кодекс'
}

class DB:
    def __init__(self, db_path: Path, data_dir: Path, metadata_path: Path):
        self.path=db_path; self.data_dir=data_dir; self.meta_path=metadata_path
        self.c=sqlite3.connect(str(db_path))
        self.c.execute('PRAGMA foreign_keys=ON')
        self._init_schema()

    def _init_schema(self):
        self.c.executescript('''
        CREATE TABLE IF NOT EXISTS laws(
            id INTEGER PRIMARY KEY,
            filename TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            kind TEXT,
            number TEXT,
            date TEXT,
            raw TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chapters(
            id INTEGER PRIMARY KEY,
            law_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            ord INTEGER NOT NULL,
            FOREIGN KEY(law_id) REFERENCES laws(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS articles(
            id INTEGER PRIMARY KEY,
            law_id INTEGER NOT NULL,
            chapter_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            ord INTEGER NOT NULL,
            FOREIGN KEY(law_id) REFERENCES laws(id) ON DELETE CASCADE,
            FOREIGN KEY(chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS bookmarks(
            law_id INTEGER NOT NULL,
            article_id INTEGER NOT NULL,
            note TEXT DEFAULT '',
            created_at INTEGER,
            pinned INTEGER DEFAULT 0,
            PRIMARY KEY(law_id,article_id),
            FOREIGN KEY(law_id) REFERENCES laws(id) ON DELETE CASCADE,
            FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS recent(
            law_id INTEGER NOT NULL,
            article_id INTEGER NOT NULL,
            opened_at INTEGER,
            FOREIGN KEY(law_id) REFERENCES laws(id) ON DELETE CASCADE,
            FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_articles_law ON articles(law_id,ord);
        CREATE INDEX IF NOT EXISTS idx_articles_title ON articles(title);
        CREATE INDEX IF NOT EXISTS idx_recent_opened ON recent(opened_at DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_recent_article ON recent(law_id,article_id);
        ''')
        self._ensure_fts()
        self.c.commit()

    def _ensure_fts(self):
        try:
            self.c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(article_id UNINDEXED, law_id UNINDEXED, title, body, tokenize='unicode61')")
            self._fts=True
        except sqlite3.OperationalError:
            self._fts=False

    def close(self):
        try:self.c.close()
        except Exception:pass

    def rebuild(self):
        # Preserve user state by stable source identity, not transient DB ids.
        saved_bm=self.c.execute('''SELECT l.filename,a.title,b.note,COALESCE(b.pinned,0),COALESCE(b.created_at,?)
                                   FROM bookmarks b JOIN laws l ON l.id=b.law_id JOIN articles a ON a.id=b.article_id''',(int(time.time()),)).fetchall()
        saved_recent=self.c.execute('''SELECT l.filename,a.title,r.opened_at
                                      FROM recent r JOIN laws l ON l.id=r.law_id JOIN articles a ON a.id=r.article_id
                                      ORDER BY r.opened_at DESC LIMIT 200''').fetchall()
        meta=json.loads(self.meta_path.read_text(encoding='utf-8'))
        with self.c:
            self.c.execute('DELETE FROM bookmarks')
            self.c.execute('DELETE FROM recent')
            if self._fts:self.c.execute('DELETE FROM articles_fts')
            self.c.execute('DELETE FROM laws')
            for m in meta:
                raw=(self.data_dir/m['file']).read_text(encoding='utf-8',errors='replace')
                lid=int(m['id'])
                self.c.execute('INSERT INTO laws(id,filename,title,kind,number,date,raw) VALUES(?,?,?,?,?,?,?)',
                               (lid,m['file'],m['title'],m.get('kind',''),m.get('number',''),m.get('date','—'),raw))
                for ci,ch in enumerate(parse_document(raw)):
                    cid=self.c.execute('INSERT INTO chapters(law_id,title,ord) VALUES(?,?,?)',(lid,ch['title'],ci)).lastrowid
                    for ai,a in enumerate(ch['articles']):
                        aid=self.c.execute('INSERT INTO articles(law_id,chapter_id,title,body,ord) VALUES(?,?,?,?,?)',(lid,cid,a['title'],a['body'],ai)).lastrowid
                        if self._fts:
                            self.c.execute('INSERT INTO articles_fts(article_id,law_id,title,body) VALUES(?,?,?,?)',(aid,lid,a['title'],a['body']))
            self._restore_user_state(saved_bm,saved_recent)
        return self.stats()

    def _restore_user_state(self,saved_bm,saved_recent):
        for fn,at,note,pinned,created in saved_bm:
            row=self.c.execute('''SELECT l.id,a.id FROM laws l JOIN articles a ON a.law_id=l.id
                                  WHERE l.filename=? AND a.title=?''',(fn,at)).fetchone()
            if row:
                self.c.execute('''INSERT OR REPLACE INTO bookmarks(law_id,article_id,note,created_at,pinned) VALUES(?,?,?,?,?)''',
                               (row[0],row[1],note,int(created or time.time()),int(pinned or 0)))
        for fn,at,opened in reversed(saved_recent):
            row=self.c.execute('''SELECT l.id,a.id FROM laws l JOIN articles a ON a.law_id=l.id
                                  WHERE l.filename=? AND a.title=?''',(fn,at)).fetchone()
            if row:self.c.execute('INSERT INTO recent(law_id,article_id,opened_at) VALUES(?,?,?)',(row[0],row[1],int(opened or time.time())))

    def stats(self):
        return self.c.execute('''SELECT
            (SELECT COUNT(*) FROM laws),
            (SELECT COUNT(*) FROM articles),
            (SELECT COUNT(*) FROM bookmarks)''').fetchone()

    def laws(self):
        return self.c.execute('SELECT id,title,kind,number,date FROM laws ORDER BY title COLLATE NOCASE').fetchall()

    def chapters(self,lid):
        return self.c.execute('SELECT id,title FROM chapters WHERE law_id=? ORDER BY ord',(lid,)).fetchall()

    def articles(self,lid):
        return self.c.execute('SELECT id,chapter_id,title,body FROM articles WHERE law_id=? ORDER BY chapter_id,ord',(lid,)).fetchall()

    def article(self,aid):
        return self.c.execute('''SELECT a.id,a.law_id,a.title,a.body,l.title,l.kind,l.number,l.date,c.title
                                 FROM articles a JOIN laws l ON l.id=a.law_id JOIN chapters c ON c.id=a.chapter_id
                                 WHERE a.id=?''',(aid,)).fetchone()

    def code_ids(self,code):
        need=CODE_ALIASES.get((code or '').strip())
        if not need:return []
        return [lid for lid,title in self.c.execute('SELECT id,title FROM laws') if need in (title or '').lower()]

    @staticmethod
    def article_number(title):
        m=re.search(r'^\s*Статья\s+(\d+(?:-\d+)?(?:\.\d+)*)',title or '',re.I)
        return m.group(1) if m else ''

    @staticmethod
    def has_criminal_sanction(body):
        return bool(re.search(r'\bнаказыва(?:ется|ются)\b',body or '',re.I))

    @staticmethod
    def has_admin_sanction(body):
        return bool(re.search(r'\bвлеч(?:ет|ёт)\b.*(?:штраф|арест|лишен|конфиск)',body or '',re.I|re.S))

    def code_articles(self,code,filter_name='Все'):
        ids=self.code_ids(code)
        if not ids:return []
        qmarks=','.join('?'*len(ids))
        rows=self.c.execute(f'''SELECT a.id,a.law_id,a.title,a.body,l.title,l.number,c.ord,c.title
                                FROM articles a JOIN laws l ON l.id=a.law_id JOIN chapters c ON c.id=a.chapter_id
                                WHERE a.law_id IN ({qmarks}) ORDER BY c.ord,a.ord''',ids).fetchall()
        out=[]
        for row in rows:
            aid,lid,at,body,lt,num,chord,cht=row
            n=self.article_number(at)
            first=int(re.match(r'\d+',n).group()) if re.match(r'\d+',n) else -1
            if code=='УК':
                practical=self.has_criminal_sanction(body) and first>=37
                general=not practical
                pdd=False
            elif code=='КоАП':
                practical=self.has_admin_sanction(body)
                pdd=first==9
                general=not practical
            else:
                practical=False;general=True;pdd=False
            keep=True
            if code=='КоАП':
                if filter_name=='ПДД':keep=pdd and practical
                elif filter_name in ('Остальное','Правонарушения'):keep=(not pdd) and practical
                elif filter_name=='Общая часть':keep=general
            elif code=='УК':
                if filter_name=='Преступления':keep=practical
                elif filter_name=='Общая часть':keep=general
            if keep:out.append((aid,lid,at,body,lt,num,chord,cht,practical,pdd))
        return out

    def search(self,q,code=None,filter_name='Все'):
        q=(q or '').strip()
        if code:
            rows=self.code_articles(code,filter_name)
            return self._score_rows(rows,q)
        if self._fts and q:
            # FTS is used for speed; fall back to LIKE if the query is malformed.
            try:
                ids=[r[0] for r in self.c.execute('SELECT article_id FROM articles_fts WHERE articles_fts MATCH ? LIMIT 1000',(q,)).fetchall()]
                if ids:
                    qm=','.join('?'*len(ids))
                    rows=self.c.execute(f'''SELECT a.id,a.law_id,a.title,a.body,l.title,l.number
                                            FROM articles a JOIN laws l ON l.id=a.law_id WHERE a.id IN ({qm})''',ids).fetchall()
                    return self._score_rows(rows,q)
            except sqlite3.OperationalError:
                pass
        rows=self.c.execute('''SELECT a.id,a.law_id,a.title,a.body,l.title,l.number
                               FROM articles a JOIN laws l ON l.id=a.law_id ORDER BY l.title,a.id''').fetchall()
        return self._score_rows(rows,q)

    def _score_rows(self,rows,q):
        toks=[x for x in re.findall(r'[А-Яа-яЁёA-Za-z0-9.-]+',q.lower()) if len(x)>=1]
        out=[]
        for row in rows:
            aid,lid,at,body,lt,num,*_=row
            hay=(lt+' '+at+' '+body).lower()
            if toks and not all(t in hay for t in toks):continue
            score=sum((14 if t in at.lower() else 5) for t in toks)
            out.append((score,aid,lid,at,body,lt,num))
        out.sort(key=lambda x:(-x[0],x[3].lower()))
        return out

    def find_ref(self,code,num):
        code=(code or '').upper().replace('КОАП','КоАП')
        need=CODE_ALIASES.get(code)
        if not need:return None
        target=str(num).strip()
        for lid,title in self.c.execute('SELECT id,title FROM laws'):
            if need not in (title or '').lower():continue
            for aid,at in self.c.execute('SELECT id,title FROM articles WHERE law_id=? ORDER BY id',(lid,)):
                m=re.search(r'^\s*Статья\s+(\d+(?:-\d+)?(?:\.\d+)*)',at or '',re.I)
                if m and m.group(1)==target:return (aid,at)
            # A reference to a part such as 16.1 or 65-1.1 points to its parent
            # article when the part is not a separately titled article in the source.
            if re.fullmatch(r'\d+(?:-\d+)?(?:\.\d+)+',target):
                parent=target.rsplit('.',1)[0]
                for aid,at in self.c.execute('SELECT id,title FROM articles WHERE law_id=? ORDER BY id',(lid,)):
                    m=re.search(r'^\s*Статья\s+(\d+(?:-\d+)?(?:\.\d+)*)',at or '',re.I)
                    if m and m.group(1)==parent:return (aid,at)
        return None

    def find_law_ref(self,keyword,num):
        key=(keyword or '').strip().lower()
        target=str(num).strip() if num is not None else ''
        rows=self.c.execute('SELECT id,title,number,filename FROM laws ORDER BY id').fetchall()
        for lid,title,number,filename in rows:
            hay=' '.join([str(title or ''),str(number or ''),str(filename or '')]).lower()
            if key and key not in hay:
                continue
            if not target:
                return (None,None,title)
            for aid,at in self.c.execute('SELECT id,title FROM articles WHERE law_id=? ORDER BY id',(lid,)):
                m=re.search(r'^\s*Статья\s+(\d+(?:-\d+)?(?:\.\d+)*)',at or '',re.I)
                if m and m.group(1)==target:return (aid,at,title)
        return None

    def backlinks(self,code,num,limit=40):
        from .references import extract_refs
        target=((code or '').strip(),str(num).strip())
        out=[]
        rows=self.c.execute("SELECT a.id,a.law_id,a.title,a.body,l.title,l.number FROM articles a JOIN laws l ON l.id=a.law_id").fetchall()
        for aid,lid,at,body,lt,nm in rows:
            for ref_code,ref_num in extract_refs(body):
                if (ref_code,ref_num)==target:
                    out.append((aid,lid,at,lt))
                    if len(out)>=limit:return out
        return out

    def toggle_bm(self,lid,aid):
        if self.bookmarked(lid,aid):
            self.c.execute('DELETE FROM bookmarks WHERE law_id=? AND article_id=?',(lid,aid)); self.c.commit(); return False
        self.c.execute('INSERT OR REPLACE INTO bookmarks(law_id,article_id,note,created_at,pinned) VALUES(?,?,?,?,COALESCE((SELECT pinned FROM bookmarks WHERE law_id=? AND article_id=?),0))',
                       (lid,aid,'',int(time.time()),lid,aid)); self.c.commit(); return True

    def pin_bm(self,lid,aid):
        row=self.c.execute('SELECT pinned FROM bookmarks WHERE law_id=? AND article_id=?',(lid,aid)).fetchone()
        if not row:
            return False
        new_value=0 if int(row[0] or 0) else 1
        self.c.execute('UPDATE bookmarks SET pinned=? WHERE law_id=? AND article_id=?',(new_value,lid,aid)); self.c.commit()
        return bool(new_value)

    def bookmarked(self,lid,aid):
        return bool(self.c.execute('SELECT 1 FROM bookmarks WHERE law_id=? AND article_id=?',(lid,aid)).fetchone())

    def bookmarks(self):
        return self.c.execute('''SELECT b.law_id,b.article_id,b.pinned,l.title,a.title,a.body
                                 FROM bookmarks b JOIN laws l ON l.id=b.law_id JOIN articles a ON a.id=b.article_id
                                 ORDER BY b.pinned DESC,b.created_at DESC''').fetchall()

    def recent(self, limit=200):
        limit=max(1,min(int(limit or 200),1000))
        return self.c.execute('''SELECT r.law_id,r.article_id,l.title,a.title,r.opened_at
                                 FROM recent r JOIN laws l ON l.id=r.law_id JOIN articles a ON a.id=r.article_id
                                 ORDER BY r.opened_at DESC LIMIT ?''',(limit,)).fetchall()

    def add_recent(self,lid,aid):
        self.c.execute('DELETE FROM recent WHERE law_id=? AND article_id=?',(lid,aid))
        self.c.execute('INSERT INTO recent(law_id,article_id,opened_at) VALUES(?,?,?)',(lid,aid,int(time.time())))
        self.c.commit()

    def validate(self):
        problems=[]
        for lid,title,kind,num,date in self.laws():
            arts=self.articles(lid)
            if not arts:problems.append(f'Пустой документ: {title}')
            for aid,cid,at,body in arts:
                if re.search(r'\\[.)]',at or ''):problems.append(f'Экранирование в заголовке: {title} → {at}')
                if re.search(r'\\[.)]',body or ''):problems.append(f'Экранирование в тексте: {title} → {at}')
                # Some source documents place the full article text in the heading itself (notably
                # parts of the local СМИ law). Treat a descriptive title as non-empty content.
                visible_title = re.sub(r'^Статья\s+[^.]+\.?\s*', '', at or '', flags=re.I).strip(' .—-')
                if not (body or '').strip() and len(visible_title) < 8:
                    problems.append(f'Пустая статья: {title} → {at}')
        return problems

# Audit helpers are intentionally read-only; they never rewrite source files.
def _extract_source_identity(raw: str):
    import re
    title=''; number=''; date=''
    # Prefer the document-level title/number from its own HTML/Markdown source.
    for line in raw.splitlines()[:40]:
        x=re.sub(r'\[[^\]]+\]\([^)]+\)', '', line)
        x=re.sub(r'[*#_`]', '', x).strip()
        if x and not title and re.fullmatch(r'ФЕДЕРАЛЬНЫЙ ЗАКОН|КОНСТИТУЦИЯ.*|УГОЛОВНЫЙ КОДЕКС.*|КОДЕКС.*|ПРАВИЛА ДОРОЖНОГО ДВИЖЕНИЯ.*', x, re.I):
            title=x
    # For files whose title is in a linked heading or otherwise omitted, use distinctive phrases.
    if not title:
        markers=[
            ('Об охране здоровья','Федеральный закон «Об охране здоровья»'),
            ('об организации дорожного движения','Федеральный закон «Об организации дорожного движения»'),
            ('Законодательство Российской Федерации в области обороны','Федеральный закон «Об обороне»'),
            ('Адвокатской деятельностью является','Федеральный закон «Об адвокатской деятельности и адвокатуре»'),
            ('Федеральная служба исполнения наказаний','Федеральный закон «Об учреждениях и органах исполнения уголовных наказаний»'),
            ('Федеральная служба безопасности','Федеральный закон «О Федеральной службе безопасности»'),
        ]
        for needle,label in markers:
            if needle.lower() in raw.lower(): title=label; break
    nums=re.findall(r'№\s*([0-9]+-[А-ЯA-ZЁ]+)', raw)
    dates=re.findall(r'\b\d{1,2}\s+[А-Яа-яЁё]+\s+202[456]\s+года', raw)
    if nums: number=nums[-1]
    if dates: date=dates[-1].replace(' года','')
    return title,number,date


def audit_source_identity(self):
    meta=json.loads(self.meta_path.read_text(encoding='utf-8'))
    report=[]
    files={m['file']:m for m in meta}
    for m in meta:
        path=self.data_dir/m['file']
        raw=path.read_text(encoding='utf-8',errors='replace') if path.exists() else ''
        actual_title,actual_num,actual_date=_extract_source_identity(raw)
        mismatch=[]
        if not path.exists(): mismatch.append('missing-file')
        if actual_title and m['title'].lower() not in actual_title.lower() and actual_title.lower() not in m['title'].lower():
            # Some source headers are generic; treat a known marker-derived title as authoritative.
            if '«'+actual_title.split('«',1)[-1] not in m['title']:
                mismatch.append(f'title: meta={m["title"]!r} actual={actual_title!r}')
        if actual_num and m.get('number') and actual_num != m.get('number'): mismatch.append(f'number: meta={m.get("number")} actual={actual_num}')
        if actual_date and m.get('date') and actual_date != m.get('date'): mismatch.append(f'date: meta={m.get("date")} actual={actual_date}')
        report.append((m['file'],m['title'],m.get('number',''),m.get('date',''),actual_title,actual_num,actual_date,mismatch))
    return report

DB.audit_source_identity=audit_source_identity
