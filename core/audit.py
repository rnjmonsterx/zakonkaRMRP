from __future__ import annotations
import json,re
from collections import Counter,defaultdict
from pathlib import Path
from .parser import parse_document
from .references import extract_refs

EXPECTED_TITLES={
1:'Конституция Российской Федерации',2:'Уголовный кодекс Российской Федерации',3:'Кодекс об административных правонарушениях Российской Федерации',4:'Процессуальный кодекс Российской Федерации',5:'Уголовно-процессуальный кодекс Российской Федерации',6:'Трудовой кодекс Российской Федерации',7:'Бюджетный кодекс Российской Федерации',8:'Избирательный кодекс Российской Федерации',9:'Федеральный конституционный закон «О Правительстве»',10:'Федеральный конституционный закон «О судебной системе»',11:'Федеральный конституционный закон «Об особых правовых режимах»',12:'Федеральный закон «О воздушном пространстве»',13:'Федеральный закон «Об оружии»',14:'Федеральный закон «О полиции»',15:'Федеральный закон «О прокуратуре»',16:'Федеральный закон «О Федеральной службе охраны»',17:'Федеральный закон «О документообороте»',18:'Федеральный закон «Правила дорожного движения»',19:'Федеральный закон «О государственной тайне»',20:'Федеральный закон «О государственной собственности, закрытых и охраняемых территориях»',21:'Федеральный закон «О Федеральной службе войск национальной гвардии»',22:'Федеральный закон «О средствах массовой информации»',23:'Федеральный закон «Об охране здоровья»',24:'Федеральный закон «Об организации дорожного движения»',25:'Федеральный закон «Об обороне»',26:'Федеральный закон «Об адвокатской деятельности и адвокатуре»',27:'Федеральный закон «Об учреждениях и органах исполнения уголовных наказаний»',28:'Федеральный закон «О Федеральной службе безопасности»',29:'Федеральный закон «О государственной службе»',30:'Федеральный закон «О Следственном комитете»',
}
EXPECTED_NUMBERS={2:'34-ФКЗ',3:'4-ФКЗ',4:'69-ФКЗ',5:'74-ФКЗ',6:'35-ФКЗ',7:'67-ФКЗ',8:'34-ФКЗ',9:'2-ФКЗ',10:'64-ФКЗ',11:'28-ФКЗ',12:'95-ФЗ',13:'34-ФЗ',14:'74-ФЗ',15:'14-ФЗ',16:'22-ФЗ',17:'42-ФЗ',18:'90-ФЗ',19:'10-ФЗ',20:'86-ФЗ',21:'18-ФЗ',23:'29-ФЗ',24:'74-ФЗ',25:'52-ФЗ',26:'50-ФЗ',27:'66-ФЗ',28:'78-ФЗ',29:'54-ФЗ',30:'88-ФЗ'}
MISSING_EXPECTED=['Федеральный закон «О коммерческой деятельности» — исходного файла нет в текущем наборе data/laws; не создавать заглушку.']

def footer_identity(raw):
    tail='\n'.join(raw.splitlines()[-45:])
    num=(re.findall(r'№\s*([0-9]+-[А-ЯA-ZЁ]+)',tail) or [None])[-1]
    date=(re.findall(r'\b\d{1,2}\s+[А-Яа-яЁё]+\s+202[456]\s*(?:года)?',tail) or [None])[-1]
    return num, date.replace(' года','') if date else None

def run(root: Path):
    root=Path(root); meta=json.loads((root/'data/metadata.json').read_text(encoding='utf-8'))
    problems=[]; info=[]; counts={}; ref_targets=defaultdict(int); unresolved=[]
    for m in sorted(meta,key=lambda x:x['id']):
        p=root/'data'/'laws'/m['file']
        if not p.exists(): problems.append(f'MISSING FILE {m["file"]}'); continue
        raw=p.read_text(encoding='utf-8',errors='replace')
        arts=[a for c in parse_document(raw) for a in c['articles']]
        counts[m['id']]=len(arts)
        nums=[re.search(r'^Статья\s+([0-9]+(?:[.\-][0-9]+)*)',a['title'],re.I).group(1) for a in arts if re.search(r'^Статья\s+([0-9]+(?:[.\-][0-9]+)*)',a['title'],re.I)]
        dup=[n for n,c in Counter(nums).items() if c>1]
        # Duplicate article numbers can exist in the source itself (e.g. 17.md has two
        # Article 4 headings for different subjects). Keep them as source anomalies rather
        # than treating them as parser/database corruption.
        n_actual,d_actual=footer_identity(raw)
        if m['id'] in EXPECTED_NUMBERS and n_actual and EXPECTED_NUMBERS[m['id']]!=n_actual:
            problems.append(f'NUMBER {m["file"]}: expected {EXPECTED_NUMBERS[m["id"]]} source_footer={n_actual}')
        if m['id'] in EXPECTED_TITLES and m['title']!=EXPECTED_TITLES[m['id']]:
            problems.append(f'METADATA TITLE {m["file"]}: got {m["title"]!r}')
        # Collect references and resolve later using DB-independent title maps.
        for a in arts:
            for c,n in extract_refs(a['body']): ref_targets[(c,n)]+=1
        info.append((m['file'],m['title'],len(arts),n_actual,d_actual,dup))
    # Build article index from source files.
    index=defaultdict(list)
    for m in meta:
        p=root/'data'/'laws'/m['file']
        raw=p.read_text(encoding='utf-8',errors='replace')
        for a in [a for c in parse_document(raw) for a in c['articles']]:
            mm=re.search(r'^Статья\s+([0-9]+(?:[.\-][0-9]+)*)',a['title'],re.I)
            if mm:index[m['title'],mm.group(1)].append(m['file'])
    for (code,num),cnt in sorted(ref_targets.items()):
        title_key={'УК':'Уголовный кодекс Российской Федерации','КоАП':'Кодекс об административных правонарушениях Российской Федерации','ПК':'Процессуальный кодекс Российской Федерации','УПК':'Уголовно-процессуальный кодекс Российской Федерации','ТК':'Трудовой кодекс Российской Федерации','БК':'Бюджетный кодекс Российской Федерации','ИК':'Избирательный кодекс Российской Федерации'}.get(code)
        if title_key and not index.get((title_key,num)):
            unresolved.append((code,num,cnt))
    return {'problems':problems,'unresolved':unresolved,'documents':info,'article_count':sum(counts.values()),'document_count':len(info),'missing_expected':MISSING_EXPECTED}
