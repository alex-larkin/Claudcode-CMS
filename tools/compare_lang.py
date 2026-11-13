# -*- coding: utf-8 -*-
"""Runs an English CMS check and a translated copy (Spanish/French) on the same project
through Project Checker's offline harness, and checks that both report the same places.

    C:\\Python27\\python.exe CMS\\tools\\compare_lang.py EN.cms XX.cms [--project DIR]
        [--books GEN,MAT|all] [--engine ipy|cpython] [--options OPTS.json] [--keep DIR]

Each side gets its own .cms option defaults (overlaid with --options). The script of each
side is the \\script of its .cms, found beside the .cms. Both run on their own scratch copy
of the project (default: Project_Checker\\tests\\fixtures\\PDT15, whose parent holds
usfm.sty). Compared: every outputError (book, chapter, begin, end), errors, and the names
of the HTML files written. Messages and HTML text differ by design and are only shown
(first few) so a reader can check the translation. Exit code 0 = same places.
"""
import codecs
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HARNESS = os.path.join(REPO, 'Project_Checker', 'tests', 'harness')
FIXTURES = os.path.join(REPO, 'Project_Checker', 'tests', 'fixtures')
PY27 = r'C:\Python27\python.exe'


def read_cms(path):
    text = io.open(path, encoding='utf-8-sig').read()
    script = re.search(r'^\\script\s+(.+?)\s*$', text, re.M).group(1)
    opts = {}
    name = None
    for line in text.splitlines():
        m = re.match(r'\\optionName\s+(\S+)', line)
        if m:
            name = m.group(1)
            opts[name] = u''
            continue
        m = re.match(r'\\optionDefault(?:\s+(.*))?$', line)
        if m and name:
            opts[name] = (m.group(1) or u'').strip()
    return os.path.join(os.path.dirname(path), script), opts


def run(cms, project, books, engine, extra, work, tag):
    script, opts = read_cms(cms)
    opts.update(extra)
    # Copy the script folder's .py files next to each other (a check may import a sibling,
    # e.g. ptx_goto) into a private folder, so .pyc files and reports stay out of the repo.
    sdir = os.path.join(work, tag + '_scripts')
    os.makedirs(sdir)
    for d in (os.path.dirname(script), os.path.join(REPO, 'CMS', 'ptx_goto')):
        for fn in os.listdir(d):
            if fn.lower().endswith('.py') and not os.path.exists(os.path.join(sdir, fn)):
                shutil.copy(os.path.join(d, fn), sdir)
    pdir = os.path.join(work, tag, os.path.basename(project))
    os.makedirs(os.path.dirname(pdir))
    shutil.copytree(project, pdir)
    sty = os.path.join(os.path.dirname(project), 'usfm.sty')
    if os.path.exists(sty):
        shutil.copy(sty, os.path.dirname(pdir))
    optfile = os.path.join(work, tag + '_opts.json')
    with open(optfile, 'wb') as f:
        f.write(json.dumps(opts))
    out = os.path.join(work, tag + '.json')
    args = [os.path.join(HARNESS, 'cms_harness.py'), '--script', os.path.join(sdir, os.path.basename(script)),
            '--project', pdir, '--books', books, '--options', optfile, '--out', out]
    if engine == 'ipy':
        # -File would bind '--out' to PowerShell's -OutVariable; quoted -Command passes it through.
        q = lambda s: "'" + s.replace("'", "''") + "'"
        cmd = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command',
               '& ' + ' '.join(q(x) for x in [os.path.join(HARNESS, 'ipy_run.ps1')] + args)]
    else:
        cmd = [PY27] + args
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=open(os.devnull))
    so, se = p.communicate()
    if not os.path.exists(out):
        sys.stderr.write(se)
        raise SystemExit('%s: harness wrote nothing' % tag)
    return json.load(io.open(out, encoding='utf-8'))


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        raise SystemExit(__doc__)
    en, xx = a[0], a[1]
    o = {'--project': os.path.join(FIXTURES, 'PDT15'), '--books': 'all', '--engine': 'ipy',
         '--options': '', '--keep': ''}
    i = 2
    while i < len(a):
        o[a[i]] = a[i + 1]
        i += 2
    extra = json.load(io.open(o['--options'], encoding='utf-8')) if o['--options'] else {}
    work = o['--keep'] or tempfile.mkdtemp(prefix='cmp_lang_')
    if o['--keep'] and os.path.exists(work):
        shutil.rmtree(work)
    if not os.path.exists(work):
        os.makedirs(work)
    r1 = run(en, o['--project'], o['--books'], o['--engine'], extra, work, 'en')
    r2 = run(xx, o['--project'], o['--books'], o['--engine'], extra, work, 'xx')
    ok = True
    for tag, r in (('en', r1), ('xx', r2)):
        if r['error']:
            ok = False
            print('%s ERROR:\n%s' % (tag, r['error'].encode('utf-8')))
    k1 = [(f['book'], f['chapter'], f['begin'], f['end']) for f in r1['findings']]
    k2 = [(f['book'], f['chapter'], f['begin'], f['end']) for f in r2['findings']]
    print('findings: en %d, translated %d' % (len(k1), len(k2)))
    if k1 != k2:
        ok = False
        s1, s2 = set(k1), set(k2)
        print('  only en: %d, only translated: %d, same set: %s' % (len(s1 - s2), len(s2 - s1), s1 == s2))
    seen = set()
    shown = 0
    for f1, f2 in zip(r1['findings'], r2['findings']):
        if f1['msg'] in seen:
            continue
        seen.add(f1['msg'])
        print((u'  %s\n   -> %s' % (f1['msg'], f2['msg'])).encode('utf-8'))
        shown += 1
        if shown >= 8:
            break
    h1, h2 = sorted(r1['html']), sorted(r2['html'])
    print('html: en %s, translated %s' % (h1, [h.encode('utf-8') for h in h2]))
    if len(h1) != len(h2):
        ok = False
    for h in h2:
        path = os.path.join(work, 'xx', h)
        io.open(os.path.join(work, 'xx_' + h), 'w', encoding='utf-8').write(r2['html'][h])
    print('work folder: %s' % work)
    print('SAME PLACES' if ok else 'DIFFERENT')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
