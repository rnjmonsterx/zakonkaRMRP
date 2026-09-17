import ast, collections
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def test_no_duplicate_methods():
    for path in [ROOT/'main.py',ROOT/'ui'/'app.py',ROOT/'core'/'database.py']:
        tree=ast.parse(path.read_text(encoding='utf8'))
        for cls in [n for n in tree.body if isinstance(n,ast.ClassDef)]:
            names=[n.name for n in cls.body if isinstance(n,ast.FunctionDef)]
            dup=[x for x,c in collections.Counter(names).items() if c>1]
            assert not dup,(path,dup)

def test_no_removed_features():
    text=(ROOT/'ui'/'app.py').read_text(encoding='utf8')
    for bad in ('show_authority','show_scenarios','show_penalty_search','ORG_DATA','orgbar','penaltybar'):
        assert bad not in text,bad

def main():
    test_no_duplicate_methods(); test_no_removed_features(); print('STATIC REFACTOR TEST OK')
if __name__=='__main__':main()
