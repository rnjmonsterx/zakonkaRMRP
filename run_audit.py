from pathlib import Path
from core.audit import run
import json
root=Path(__file__).resolve().parent
report=run(root)
out=root/'AUDIT_REPORT.json'; out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('DOCUMENTS',report['document_count'])
print('ARTICLES',report['article_count'])
print('PROBLEMS',len(report['problems']))
for x in report['problems']: print(' -',x)
print('UNRESOLVED_REFS',len(report['unresolved']))
for x in report['unresolved'][:25]: print(' -',x)
print('MISSING_EXPECTED')
for x in report['missing_expected']: print(' -',x)
