from __future__ import annotations
import re

CODE_SHORTS=['УК','КоАП','ПК','УПК','ТК','БК','ИК']
FULL_ALIASES={
    'уголовного кодекса':'УК',
    'уголовный кодекс':'УК',
    'кодекса об административных правонарушениях':'КоАП',
    'кодекс об административных правонарушениях':'КоАП',
    'процессуального кодекса':'ПК',
    'процессуальный кодекс':'ПК',
    'уголовно-процессуального кодекса':'УПК',
    'уголовно-процессуальный кодекс':'УПК',
    'трудового кодекса':'ТК',
    'трудовой кодекс':'ТК',
    'бюджетного кодекса':'БК',
    'бюджетный кодекс':'БК',
    'избирательного кодекса':'ИК',
    'избирательный кодекс':'ИК',
}

def _canon_code(code: str) -> str:
    c=code.strip().upper()
    return 'КоАП' if c=='КОАП' else c

def _add(out, code, num):
    pair=(_canon_code(code),str(num))
    if pair not in out: out.append(pair)

def _expand_range(a: str, b: str):
    try:
        ai=int(a); bi=int(b)
        if ai<=bi and bi-ai<=100:
            return [str(x) for x in range(ai,bi+1)]
    except ValueError:
        pass
    return [a,b]

def extract_refs(text: str):
    text=text or ''
    out=[]
    # Short code first: "КоАП 9.1", "УК ст. 37", "ст. 37 УК"
    pats=[
      r'(?i)\b(УК|КоАП|ПК|УПК|ТК|БК|ИК)\b\s*(?:ст\.?|статья|статьи)?\s*(\d+(?:-\d+)?(?:[.]\d+)*)',
      r'(?i)(?:ст\.?|статья|статьи)\s*(\d+(?:-\d+)?(?:[.]\d+)*)\s*\b(УК|КоАП|ПК|УПК|ТК|БК|ИК)\b'
    ]
    for p in pats:
        for m in re.finditer(p,text):
            code,num=(m.group(1),m.group(2)) if m.group(1).upper() in [x.upper() for x in CODE_SHORTS] else (m.group(2),m.group(1))
            _add(out,code,num)
    # Full-name references, including ranges: "статьями 37 - 49 Уголовного Кодекса"
    full_alt='|'.join(re.escape(x) for x in sorted(FULL_ALIASES,key=len,reverse=True))
    pat=rf'(?i)(?:ст\.?|статья|статьями|статьи)\s*(\d+(?:-\d+)?(?:[.]\d+)*)\s*(?:-|–|—)\s*(\d+(?:-\d+)?(?:[.]\d+)*)\s+({full_alt})'
    for m in re.finditer(pat,text):
        for n in _expand_range(m.group(1),m.group(2)):_add(out,FULL_ALIASES[m.group(3).lower()],n)
    pat_single=rf'(?i)(?:ст\.?|статья|статьями|статьи)\s*(\d+(?:-\d+)?(?:[.]\d+)*)\s+({full_alt})'
    for m in re.finditer(pat_single,text):
        _add(out,FULL_ALIASES[m.group(2).lower()],m.group(1))
    return out
