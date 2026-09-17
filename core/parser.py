from __future__ import annotations
import re

ARTICLE_RE = re.compile(r'^Статья\s+(\d+(?:-\d+)?(?:\.\d+)*)\.?(?:\s+(.*?))?\s*$', re.I)


def clean_md(s: str) -> str:
    s=s.replace("\u200b","").replace("\ufeff","")
    # Remove markdown links but keep visible label.
    s=re.sub(r'\[([^\]]+)\]\([^)]+\)',r'\1',s)
    s=re.sub(r'https?://\S+','',s)
    s=s.replace('**','').replace('__','')
    s=re.sub(r'`([^`]*)`',r'\1',s)
    s=re.sub(r'\\([\\`*{}\[\]()#+.!_\-])',r'\1',s)
    return s


def normalize(s: str) -> str:
    s=s.replace('\r\n','\n').replace('\r','\n')
    s=re.sub(r'[ \t]+',' ',s)
    s=re.sub(r'\n{3,}','\n\n',s)
    return s.strip()


def strip_prefix(s: str) -> str:
    s=clean_md(s).strip()
    s=re.sub(r'^\s*#{1,6}\s*','',s)
    return s.strip()


def _article_num_pattern() -> str:
    # 65-1 is an independent article; 65-1.1 is a part of article 65-1.
    return r"\d+(?:-\d+)?(?:\.\d+)*"


def _split_plain_inline(num: str, rest: str):
    """Parse sources like '**Статья 2.1.** Title. Body...'.

    The source does not mark the title separately, so we use a conservative
    sentence heuristic: the first sentence is the title; a very short second
    sentence is kept as part of the title (e.g. '... (далее – СМИ). Основные
    понятия.'). Everything after that becomes article body.
    """
    rest=normalize(rest)
    if not rest:
        return f'Статья {num}.', ''
    # Split on sentence-ending period followed by whitespace + an uppercase/Cyrillic
    # letter. Keep punctuation in the fragments.
    parts=re.split(r'(?<=[.!?])\s+(?=[А-ЯЁA-Z])', rest)
    if len(parts)==1:
        return f'Статья {num}. {rest}', ''
    title_parts=[parts[0]]
    # Short follow-up sentence often belongs to the heading itself.
    if len(parts)>1 and len(parts[1])<=48:
        title_parts.append(parts[1])
        body_parts=parts[2:]
    else:
        body_parts=parts[1:]
    title_tail=' '.join(x.strip() for x in title_parts if x.strip())
    body=' '.join(x.strip() for x in body_parts if x.strip())
    return f'Статья {num}. {title_tail}'.strip(), body


def article_heading(line: str):
    """Return (normalized_title, inline_body, is_structural_heading).

    Supports both linked Markdown headings and plain '**Статья N.** ...' lines.
    The distinction matters for the СМИ source where the article title and part of
    its body are placed on the same physical line.
    """
    raw=line.strip().replace('\u200b','')
    # Linked/heading forms: the visible linked text is the complete article title.
    linked = bool(re.match(r'^\s*#{0,6}\s*\[\s*\*\*Статья\s+', raw, re.I))
    markdown_heading = bool(re.match(r'^\s*#{1,6}\s*Статья\s+', raw, re.I))
    plain_bold = bool(re.match(r'^\s*\*\*Статья\s+', raw, re.I))
    visible=strip_prefix(raw)
    visible=normalize(visible)
    m=ARTICLE_RE.match(visible)
    if not m or len(visible)>5000:
        return None
    num=m.group(1); rest=(m.group(2) or '').strip()
    if linked or markdown_heading or (not plain_bold and visible==f'Статья {num}.'):
        return f"Статья {num}." + (f" {rest}" if rest else ''), '', True
    if plain_bold:
        title, inline=_split_plain_inline(num,rest)
        return normalize(title), inline, True
    return f"Статья {num}." + (f" {rest}" if rest else ''), '', True


def chapter_heading(line: str):
    s=line.strip().replace('\u200b','')
    m=re.match(r'^\s*#{0,6}\s*\[\s*\*\*(Глава\s+.+?)\*\*\s*\]\([^)]+\)\s*$',s,re.I)
    if m:return normalize(m.group(1))
    p=strip_prefix(s)
    m=re.match(r'^(Глава\s+.+)$',p,re.I)
    if m and len(p)<550:return normalize(m.group(1))
    return None


def noise(s: str) -> bool:
    s=s.strip()
    return bool(re.fullmatch(r'(?:RCtx4Sr\.png|\d{10,})',s,re.I) or re.fullmatch(r'\[\s*\d{10,}\s*\]\([^)]*\)',s,re.I) or re.fullmatch(r'https?://\S+',s,re.I) or s in {'---','___'})


def parse_document(raw: str):
    lines=raw.replace('\r\n','\n').replace('\r','\n').split('\n')
    chapters=[]; events=[]; current=None
    for i,line in enumerate(lines):
        if noise(line):continue
        ch=chapter_heading(line)
        if ch:
            current={'title':ch,'line':i,'articles':[]}; chapters.append(current); events.append(('chapter',i,current)); continue
        art=article_heading(line)
        if art:
            if current is None:
                current={'title':'Общие положения','line':i,'articles':[]}; chapters.append(current); events.append(('chapter',i,current))
            item={'title':art[0],'line':i,'inline':art[1]}; current['articles'].append(item); events.append(('article',i,item)); continue
    structural=sorted(events,key=lambda x:x[1]); article_events=[x for x in structural if x[0]=='article']
    for _,aline,item in article_events:
        end=len(lines)
        for typ,ln,_ in structural:
            if ln>aline: end=ln; break
        body=[]
        if item.get('inline'): body.append(item['inline'])
        body.extend(lines[aline+1:end])
        keep=[]
        for rawline in body:
            if noise(rawline) or chapter_heading(rawline): continue
            # Headings from nested Markdown should never leak into article body.
            cleaned=re.sub(r'^\s*#{1,6}\s*', '', rawline)
            keep.append(cleaned)
        item['body']=normalize(clean_md('\n'.join(keep)))
        if not item['body'] and re.search(r'утратила\s+силу',item['title'],re.I): item['body']='Утратила силу.'
    return chapters
