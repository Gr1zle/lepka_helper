"""Generate UML with Pyreverse, then partition its actual DOT graph without dropping edges.
No application modules are executed; only project-owned Python source paths are passed.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
GROUPS = {
    '01_client_community': ('Клиент: сообщество и уведомления', ['community_gateway', 'challenge_gateway', 'moderation_gateway', 'notification_center', 'api_client']),
    '02_server_accounts': ('API: авторизация и аккаунт', ['backend.main']),
    '03_server_community': ('API: публикации и комментарии', ['backend.community']),
    '04_server_challenges': ('API: задания сообщества', ['backend.challenges']),
    '05_server_moderation': ('API: модерация и роли', ['backend.moderation']),
    '06_server_catalog_personal': ('API: каталог, снимки и доставка', ['backend.catalog', 'backend.personal', 'backend.delivery']),
    '07_learning_colors_3d': ('Каталог, таймер и геометрия', ['catalog_client', 'learning_catalog', 'clay_tools', 'mesh_renderer']),
    '08_ui_native_controls': ('Интерфейс и нативный мост', ['views.discovery', 'pull_refresh', 'secure_device']),
    '10_asset_generation': ('Генерация встроенных 3D-ресурсов', ['scripts.generate_learning_models']),
    '09_sync_domain_errors': ('Синхронизация и ошибки сервисов', ['personal_sync', 'personal_vault', 'offline_mutations', 'mail_service', 'role_service']),
}
NODE = re.compile(r'^"([^"]+)" \[')
EDGE = re.compile(r'^"([^"]+)" -> "([^"]+)" (\[.*\]);$')


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs)


def source_inventory():
    # Explicit source roots. Never recurse into tests, venv, vendor or docs.
    paths = sorted([*ROOT.glob('*.py'), *(ROOT/'views').glob('*.py'),
                    *(ROOT/'backend').glob('*.py'),
                    *(p for p in (ROOT/'scripts').glob('*.py') if p.name != 'run_final_checks.py')])
    classes = {}
    for path in paths:
        module = '.'.join(path.relative_to(ROOT).with_suffix('').parts)
        tree = ast.parse(path.read_text(encoding='utf-8'))
        imports = {}
        for item in tree.body:
            if isinstance(item, ast.ImportFrom) and item.module:
                for alias in item.names: imports[alias.asname or alias.name] = item.module+'.'+alias.name
            elif isinstance(item, ast.Import):
                for alias in item.names: imports[alias.asname or alias.name] = alias.name
        for item in ast.walk(tree):
            if isinstance(item, ast.ClassDef):
                assert item in tree.body, 'Nested class requires explicit qualification: '+str(path)
                bases = [ast.unparse(b) for b in item.bases]
                resolved = []
                for base in bases:
                    first, *rest = base.split('.')
                    resolved.append('.'.join([imports.get(first, module+'.'+first), *rest]))
                classes[module+'.'+item.name] = dict(module=module, file=path.relative_to(ROOT).as_posix(),
                    line=item.lineno, bases=bases, resolvedBases=resolved, annotatedFields=[dict(name=field.target.id, annotation=ast.unparse(field.annotation),
                        referencedTypes=[imports.get(n.id,module+'.'+n.id) for n in ast.walk(field.annotation) if isinstance(n,ast.Name)],
                        limits={k.arg:ast.literal_eval(k.value) for k in field.value.keywords if k.arg in ('min_length','max_length') and isinstance(k.value,ast.Constant)} if isinstance(field.value,ast.Call) else {})
                        for field in item.body if isinstance(field,ast.AnnAssign) and isinstance(field.target,ast.Name)])
    for record in classes.values():
        record['externalBases'] = [b for b,r in zip(record['bases'],record['resolvedBases']) if r not in classes]
    return paths, classes


def graph(title, nodes, edges, classes, compact=False):
    lines = ['digraph UML {', 'graph [rankdir=LR, charset="UTF-8", bgcolor="white", '
        'fontname="DejaVu Sans", fontsize=16, labelloc=t, label='+json.dumps(title,ensure_ascii=False)+', '
        'pad="0.22", nodesep="0.25", ranksep="0.55", splines=polyline, dpi=300];',
        'node [fontname="DejaVu Sans", fontsize=10, color="#334155", fontcolor="#111827", penwidth=1.1];',
        'edge [fontname="DejaVu Sans", fontsize=9, color="#334155", fontcolor="#111827", penwidth=1.1];']
    for name, line in sorted(nodes.items()):
        if compact:
            label=name
            if classes[name]['externalBases']: label+='\nbase: '+', '.join(classes[name]['externalBases'])+' [external]'
            line=json.dumps(name)+' [shape=box, style="rounded", label='+json.dumps(label)+'];'
        else:
            # Keep Pyreverse fields/methods and relationships; change presentation and wrap long signatures.
            # HTML compartments stay vertical with rankdir=LR (record nodes rotate them).
            payload=re.search(r'label=<\{(.*)\}>, shape=',line).group(1)
            compartments=re.split(r'(?<!\\)\|',payload)
            assert len(compartments)==3,(name,compartments)
            def wrap(text):
                result=[]
                for row in re.split(r'<br ALIGN="LEFT"/>',text):
                    row=row.replace('\\|','|')
                    chunks=[];current=''
                    for token in re.split(r'(?<=,) ',row):
                        if current and len(current)+len(token)>74:
                            chunks.append(current);current='&#160;&#160;'+token
                        else:current+=(' ' if current else '')+token
                    if current:chunks.append(current)
                    result.extend(chunks)
                return '<BR ALIGN="LEFT"/>'.join(result)+'<BR ALIGN="LEFT"/>' if result else ''
            header='<B>'+compartments[0]+'</B>'
            if classes[name]['externalBases']:
                header+='<BR/>base: '+', '.join(classes[name]['externalBases'])+' [external]'
            rows=[header,wrap(compartments[1]),wrap(compartments[2])]
            table='<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="6">'+''.join('<TR><TD ALIGN="LEFT">'+(v or '&#160;')+'</TD></TR>' for v in rows)+'</TABLE>'
            line=json.dumps(name)+' [shape=plain, label=<'+table+'>];'
        lines.append(line)
    lines.extend(line.replace('fontcolor="green"','fontcolor="#111827"') for a,b,line in edges if a in nodes and b in nodes)
    return '\n'.join([*lines,'}'])+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pyreverse', default='pyreverse')
    parser.add_argument('--dot', default='dot')
    args=parser.parse_args()
    paths, classes=source_inventory()
    before={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    raw=OUT/'raw';editable=OUT/'editable';images=OUT/'images'
    for p in (raw,editable,images):p.mkdir(exist_ok=True)
    base=[args.pyreverse,'-p','LepkaHelper','-f','ALL','-m','y','-a','0','-s','0',
          '--source-roots',str(ROOT),'-d',str(raw)]
    inputs=[str(p.relative_to(ROOT)) for p in paths]
    logs=[]
    for fmt in ('dot','puml'):
        result=run([*base,'-o',fmt,*inputs],cwd=ROOT)
        logs.append('$ pyreverse '+ ' '.join(base[1:])+ ' -o '+fmt+f' <{len(paths)} explicit project paths>\n'+result.stdout+result.stderr)
    (OUT/'pyreverse.log').write_text('\n'.join(logs),encoding='utf-8')
    source=(raw/'classes_LepkaHelper.dot').read_text(encoding='utf-8')
    nodes={};edges=[]
    for line in source.splitlines():
        match=EDGE.match(line)
        if match:edges.append((match[1],match[2],line));continue
        match=NODE.match(line)
        if match:nodes[match[1]]=line
    assert set(nodes)==set(classes), ('Missing or external classes',set(classes)-set(nodes),set(nodes)-set(classes))
    expected={(n,b) for n,c in classes.items() for b in c['resolvedBases'] if b in classes}
    actual={(a,b) for a,b,line in edges if 'arrowhead="empty"' in line}
    assert actual==expected, ('Lost inheritance',expected-actual,actual-expected)
    # Pyreverse 3.3 does not emit associations through generic containers such as list[PhotoInput].
    # Restore ONLY explicit own-class field annotations, with provenance, never guessed domain links.
    annotated=[]
    for owner,record in classes.items():
        for field in record['annotatedFields']:
            for target in field['referencedTypes']:
                if target not in classes or target==owner:continue
                if any({a,b}=={owner,target} and 'label="'+field['name']+'"' in line for a,b,line in edges):continue
                limits=field['limits'];label=field['name']
                if 'min_length' in limits or 'max_length' in limits:
                    label+=' ['+str(limits.get('min_length',0))+'..'+str(limits.get('max_length','*'))+']'
                line=json.dumps(owner)+' -> '+json.dumps(target)+' [arrowhead="vee", arrowtail="none", label='+json.dumps(label)+', style="solid"];'
                edges.append((owner,target,line));annotated.append(dict(source=owner,target=target,field=field['name'],annotation=field['annotation'],limits=limits))
    # Retain only requested class outputs, not the separately emitted module/import diagrams.
    for suffix in ('dot','puml'):
        (raw/('packages_LepkaHelper.'+suffix)).unlink(missing_ok=True)
    counts=[];covered=set();edge_coverage=set()
    for stem,(title,modules) in GROUPS.items():
        subset={n:line for n,line in nodes.items() if classes[n]['module'] in modules}
        assert subset,stem
        covered.update(subset)
        edge_coverage.update((a,b,line) for a,b,line in edges if a in subset and b in subset)
        (editable/(stem+'.dot')).write_text(graph(title,subset,edges,classes),encoding='utf-8')
        counts.append(dict(name=stem,title=title,classes=sorted(subset),classCount=len(subset)))
    assert covered==set(nodes), ('Unassigned classes',set(nodes)-covered)
    cross=[(a,b,line) for a,b,line in edges if (a,b,line) not in edge_coverage]
    if cross:
        subset={n:nodes[n] for a,b,_ in cross for n in (a,b)}
        (editable/'10_cross_subsystem.dot').write_text(graph('Межподсистемные связи',subset,cross,classes),encoding='utf-8')
        counts.append(dict(name='11_cross_subsystem',title='Межподсистемные связи',classes=sorted(subset),classCount=len(subset)))
        edge_coverage.update(cross)
    assert edge_coverage==set(edges)
    (editable/'00_overview.dot').write_text(graph('Lepka Helper — обзор классов (без полей и методов)',nodes,edges,classes,compact=True),encoding='utf-8')
    # Full unmodified Pyreverse graph remains in raw/; render detail sheets, never a huge all-methods bitmap.
    render=[]
    for source_path in sorted(editable.glob('*.dot')):
        for fmt in ('svg','png','pdf'):
            output=images/(source_path.stem+'.'+fmt)
            run([args.dot,'-T'+fmt,str(source_path),'-o',str(output)])
            assert output.stat().st_size>0
        png=(images/(source_path.stem+'.png')).read_bytes()
        assert png[:8]==b'\x89PNG\r\n\x1a\n'
        width,height=struct.unpack('>II',png[16:24])
        render.append(dict(name=source_path.stem,pngWidth=width,pngHeight=height))
    after={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    assert after==before,'Application source changed during generation'
    manifest=dict(sourceCommit=run(['git','rev-parse','HEAD'],cwd=ROOT).stdout.strip(),
        generatedUTC=datetime.now(timezone.utc).isoformat(),
        pyreverseVersion=run([str(Path(args.pyreverse).parent/'pylint'),'--version']).stdout.strip(),
        graphvizVersion=run([args.dot,'-V']).stderr.strip(),
        pythonSourceFiles=before,classes=classes,classCount=len(classes),inheritanceCount=len(actual),
        associationCount=len(edges)-len(actual),pyreverseAssociationCount=len(edges)-len(actual)-len(annotated),
        annotatedAssociations=annotated,relationships=[dict(source=a,target=b,dot=line) for a,b,line in edges],
        groups=counts,rendered=render,externalClassNodes=0,applicationSourcesUnchanged=before==after,
        excluded=['tests/**','scripts/run_final_checks.py','docs/**','native/** (not Python)','venv/site-packages/vendor/**'],
        files={p.relative_to(OUT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for folder in (raw,editable,images) for p in sorted(folder.glob('*')) if p.is_file()})
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(classes)} classes, {len(actual)} inheritance links, {len(edges)-len(actual)} association links; {len(render)} sheets. Source unchanged.')


if __name__=='__main__':main()
