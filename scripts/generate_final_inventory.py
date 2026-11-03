"""Export schema/API/source inventory from an isolated fresh database, never a user database."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
    output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lepka-inventory-') as folder:
        os.environ.update(LEPKA_DATA_DIR=folder,LEPKA_MAIL_API_KEY='',LEPKA_NOTIFICATION_MAIL_ENABLED='0')
        import database as db
        previous=db.DATABASE_PATH;db.DATABASE_PATH=Path(folder)/'inventory.db'
        try:
            db.initializeDatabase()
            with db.openDatabase() as c:
                tables=[]
                for row in c.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
                    name=row['name']
                    tables.append(dict(name=name,sql=row['sql'],columns=[dict(v) for v in c.execute('PRAGMA table_info("'+name+'")')],
                        foreignKeys=[dict(v) for v in c.execute('PRAGMA foreign_key_list("'+name+'")')],
                        indexes=[{**dict(v),'columns':[dict(col) for col in c.execute('PRAGMA index_info("'+v['name']+'")')]} for v in c.execute('PRAGMA index_list("'+name+'")')]))
                schema=dict(foreignKeysEnabled=c.execute('PRAGMA foreign_keys').fetchone()[0],integrity=c.execute('PRAGMA integrity_check').fetchone()[0],
                    foreignKeyViolations=[list(v) for v in c.execute('PRAGMA foreign_key_check')],tables=tables,
                    internalTables=[dict(v) for v in c.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name LIKE 'sqlite_%'")],
                    triggers=[dict(v) for v in c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'")],
                    indexes=[dict(v) for v in c.execute("SELECT name,tbl_name,sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name")])
            (output/'schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            from backend.main import createApp
            api=createApp().openapi()
            (output/'openapi.json').write_text(json.dumps(api,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        finally:db.DATABASE_PATH=previous
    from scripts.prepare_android import MODULES,VIEWS
    from scripts.prepare_server import MODULES as SERVER
    inventory=[]
    for path in sorted([*ROOT.glob('*.py'),*ROOT.joinpath('views').glob('*.py'),*ROOT.joinpath('backend').glob('*.py'),*ROOT.joinpath('scripts').glob('*.py')]):
        source=path.read_text(encoding='utf-8');tree=ast.parse(source);name=path.relative_to(ROOT).as_posix()
        inventory.append(dict(path=name,lines=len(source.splitlines()),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            description=(ast.get_docstring(tree) or '').split('\n')[0],
            functions=[n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))],
            android=(path.stem in MODULES if path.parent==ROOT else path.parent==ROOT/'views' and path.stem in VIEWS),
            server=path.stem in SERVER if path.parent==ROOT else path.parent==ROOT/'backend'))
    (output/'modules.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'source_state.json').write_text(json.dumps(dict(baseCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        changedFiles=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True).splitlines()),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"Tables: {len(schema['tables'])}; declared foreign keys: {sum(len(t['foreignKeys']) for t in tables)}; API paths: {len(api['paths'])}; Python files: {len(inventory)}")

if __name__=='__main__':main()
