# -*- coding: utf-8 -*-
# project_BT_reference_tool_fr.py -- French version of project_BT_reference_tool.py
# (user-visible strings in French; keep the logic in step with the English file).
import checking
import codecs
import os
import shutil
import sys
import unicodedata
import xml.etree.ElementTree as ET

# --- Option guards ---
try:
    AddMissing
except NameError:
    AddMissing = u'No'
if isinstance(AddMissing, str):
    AddMissing = AddMissing.decode('utf-8')

try:
    UseAllBiblicalTerms
except NameError:
    UseAllBiblicalTerms = u'Yes'
if isinstance(UseAllBiblicalTerms, str):
    UseAllBiblicalTerms = UseAllBiblicalTerms.decode('utf-8')

try:
    UseBiblicalTerms
except NameError:
    UseBiblicalTerms = u'Yes'
if isinstance(UseBiblicalTerms, str):
    UseBiblicalTerms = UseBiblicalTerms.decode('utf-8')

try:
    IgnoreDC
except NameError:
    IgnoreDC = u'Yes'
if isinstance(IgnoreDC, str):
    IgnoreDC = IgnoreDC.decode('utf-8')

try:
    IncludeHebrew
except NameError:
    IncludeHebrew = u'Yes'
if isinstance(IncludeHebrew, str):
    IncludeHebrew = IncludeHebrew.decode('utf-8')

try:
    IncludeGreek
except NameError:
    IncludeGreek = u'Yes'
if isinstance(IncludeGreek, str):
    IncludeGreek = IncludeGreek.decode('utf-8')

try:
    Project
except NameError:
    Project = u''
if isinstance(Project, str):
    Project = Project.decode('utf-8')

# --- Reference file paths (per spec) ---
ALL_TERMS = u'C:\\Program Files\\Paratext 9\\Terms\\Lists\\AllBiblicalTerms.xml'
BT_TERMS  = u'C:\\Program Files\\Paratext 9\\Terms\\Lists\\BiblicalTerms.xml'

# --- Book names (from convert_codes.py) ---
BOOK_NAMES = [
    None,
    u'GEN', u'EXO', u'LEV', u'NUM', u'DEU', u'JOS', u'JDG', u'RUT',
    u'1SA', u'2SA', u'1KI', u'2KI', u'1CH', u'2CH', u'EZR', u'NEH',
    u'EST', u'JOB', u'PSA', u'PRO', u'ECC', u'SNG', u'ISA', u'JER',
    u'LAM', u'EZK', u'DAN', u'HOS', u'JOL', u'AMO', u'OBA', u'JON',
    u'MIC', u'NAM', u'HAB', u'ZEP', u'HAG', u'ZEC', u'MAL', u'MAT',
    u'MRK', u'LUK', u'JHN', u'ACT', u'ROM', u'1CO', u'2CO', u'GAL',
    u'EPH', u'PHP', u'COL', u'1TH', u'2TH', u'1TI', u'2TI', u'TIT',
    u'PHM', u'HEB', u'JAS', u'1PE', u'2PE', u'1JN', u'2JN', u'3JN',
    u'JUD', u'REV',
]


def convert_code(code):
    code = code.strip()
    if len(code) < 9:
        return None
    try:
        book_num = int(code[0:3])
        chapter  = int(code[3:6])
        verse    = int(code[6:9])
    except ValueError:
        return None
    if book_num < 1 or book_num > 66:
        return None
    return u'{} {}:{}'.format(BOOK_NAMES[book_num], chapter, verse)


def norm(code):
    """Normalize verse code to 9-digit BBB+CCC+VVV comparison key."""
    return code.strip()[:9]


def has_hebrew(tid):
    return any(unichr(0x0590) <= c <= unichr(0x05ff) for c in tid)


def has_greek(tid):
    return any((unichr(0x0370) <= c <= unichr(0x03ff)) or
               (unichr(0x1f00) <= c <= unichr(0x1fff)) for c in tid)


def parse_terms(path, ignore_dc=False, include_hebrew=True, include_greek=True):
    """Returns dict: {term_id (unicode, NFD-normalised): set of 9-digit norm codes}"""
    result = {}
    open_path = path.encode('mbcs') if isinstance(path, type(u'')) else path
    with open(open_path, 'rb') as f:
        data = f.read()
    root = ET.fromstring(data)
    for term in root.iter(u'Term'):
        tid = term.get(u'Id', u'')
        if not isinstance(tid, type(u'')):
            tid = tid.decode('utf-8')
        tid = unicodedata.normalize('NFD', tid)
        if ignore_dc and u'(DC)' in tid:
            continue
        if not include_hebrew and has_hebrew(tid):
            continue
        if not include_greek and has_greek(tid):
            continue
        verses = set()
        refs = term.find(u'References')
        if refs is not None:
            for v in refs.findall(u'Verse'):
                if v.text:
                    verses.add(norm(v.text.strip()))
        result[tid] = verses
    return result


def find_project_xml(project_name):
    """Try common Paratext project directory locations (PT8 and PT9)."""
    candidates = [
        os.path.expanduser(u'~\\My Paratext 9 Projects\\' + project_name + u'\\ProjectBiblicalTerms.xml'),
        os.path.expanduser(u'~\\My Paratext 8 Projects\\' + project_name + u'\\ProjectBiblicalTerms.xml'),
        u'C:\\My Paratext 9 Projects\\' + project_name + u'\\ProjectBiblicalTerms.xml',
        u'C:\\My Paratext 8 Projects\\' + project_name + u'\\ProjectBiblicalTerms.xml',
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def _he(s):
    return s.replace(u'&', u'&amp;').replace(u'<', u'&lt;').replace(u'>', u'&gt;')


def write_html_report(html_path, project_name, rows, show_all, show_bt):
    lines = []
    lines.append(u'<!DOCTYPE html>')
    lines.append(u'<html lang="fr"><head><meta charset="utf-8">')
    lines.append(u'<title>Comparaison des références des termes bibliques {} {}</title>'.format(unichr(0x2013), _he(project_name)))
    lines.append(u'<style>')
    lines.append(u'body{font-family:sans-serif;font-size:13px}')
    lines.append(u'table{border-collapse:collapse}')
    lines.append(u'th,td{border:1px solid #bbb;padding:3px 8px}')
    lines.append(u'th{background:#ddd}')
    lines.append(u'.hi{background:#ffd0d0}')
    lines.append(u'</style></head><body>')
    lines.append(u'<h2>Comparaison des références des termes bibliques</h2>')
    lines.append(u'<p>Projet : <b>{}</b> &nbsp; {} terme(s) avec des différences</p>'.format(
        _he(project_name), len(rows)))
    lines.append(u'<table><tr><th>Terme</th><th>Projet</th>')
    if show_all:
        lines.append(u'<th>AllBiblicalTerms</th>')
    if show_bt:
        lines.append(u'<th>BiblicalTerms</th>')
    lines.append(u'</tr>')
    for tid_display, proj_count, all_count, bt_count in rows:
        lines.append(u'<tr>')
        lines.append(u'<td>{}</td>'.format(_he(tid_display)))
        lines.append(u'<td>{}</td>'.format(proj_count))
        if show_all:
            css = u' class="hi"' if all_count is not None and all_count != proj_count else u''
            cell = u'{}'.format(all_count) if all_count is not None else unichr(0x2013)
            lines.append(u'<td{}>{}</td>'.format(css, cell))
        if show_bt:
            css = u' class="hi"' if bt_count is not None and bt_count != proj_count else u''
            cell = u'{}'.format(bt_count) if bt_count is not None else unichr(0x2013)
            lines.append(u'<td{}>{}</td>'.format(css, cell))
        lines.append(u'</tr>')
    lines.append(u'</table></body></html>')
    html = u'\n'.join(lines)
    open_path = html_path.encode('mbcs') if isinstance(html_path, type(u'')) else html_path
    with open(open_path, 'wb') as f:
        f.write(html.encode('utf-8'))


# --- Main ---
checking.setupCheck()
sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

project_xml_path = find_project_xml(Project)
if project_xml_path is None:
    sys.stdout.write(u"# Erreur : ProjectBiblicalTerms.xml introuvable pour le projet « {} »\n".format(Project))
    _ok = False
else:
    _ok = True

if _ok:
    ignore_dc      = IgnoreDC.strip().lower()       == u'yes'
    include_hebrew = IncludeHebrew.strip().lower()  == u'yes'
    include_greek  = IncludeGreek.strip().lower()   == u'yes'
    project_terms = parse_terms(project_xml_path, ignore_dc, include_hebrew, include_greek)

    all_term_counts = {}
    bt_term_counts  = {}

    ref_terms = {}
    if UseAllBiblicalTerms.strip().lower() == u'yes':
        if os.path.isfile(ALL_TERMS):
            parsed = parse_terms(ALL_TERMS, ignore_dc, include_hebrew, include_greek)
            all_term_counts = {tid: len(v) for tid, v in parsed.items()}
            for tid, verses in parsed.items():
                ref_terms.setdefault(tid, set()).update(verses)
        else:
            sys.stdout.write(u'# Avertissement : AllBiblicalTerms.xml introuvable ici : {}\n'.format(ALL_TERMS))
    if UseBiblicalTerms.strip().lower() == u'yes':
        if os.path.isfile(BT_TERMS):
            parsed = parse_terms(BT_TERMS, ignore_dc, include_hebrew, include_greek)
            bt_term_counts = {tid: len(v) for tid, v in parsed.items()}
            for tid, verses in parsed.items():
                ref_terms.setdefault(tid, set()).update(verses)
        else:
            sys.stdout.write(u'# Avertissement : BiblicalTerms.xml introuvable ici : {}\n'.format(BT_TERMS))

    # --- Compute missing references ---
    missing_by_term = {}
    for tid, project_verses in project_terms.items():
        ref_verses = ref_terms.get(tid)
        if ref_verses is None:
            continue  # term not in reference files; skip
        missing = ref_verses - project_verses
        if missing:
            missing_by_term[tid] = sorted(missing)

    if AddMissing.strip().lower() != u'yes':
        show_all = UseAllBiblicalTerms.strip().lower() == u'yes'
        show_bt  = UseBiblicalTerms.strip().lower()   == u'yes'
        html_rows = []
        for tid, proj_verses in sorted(project_terms.items()):
            proj_count = len(proj_verses)
            all_count  = all_term_counts.get(tid) if show_all else None
            bt_count   = bt_term_counts.get(tid)  if show_bt  else None
            if all_count is None and bt_count is None:
                continue
            differs = (all_count is not None and all_count != proj_count) or \
                      (bt_count  is not None and bt_count  != proj_count)
            if not differs:
                continue
            html_rows.append((tid, proj_count, all_count, bt_count))
        html_path = os.path.join(os.path.dirname(project_xml_path), u'RapportReferencesTB.html')
        if html_rows:
            write_html_report(html_path, Project, html_rows, show_all, show_bt)
            os.startfile(html_path)
            sys.stdout.write(u'# Rapport enregistré dans {}\n'.format(html_path))
            sys.stdout.write(u'# {} terme(s) dont le nombre de références diffère\n'.format(len(html_rows)))
        else:
            sys.stdout.write(u'# Aucune différence de nombre de références n’a été trouvée.\n')

    # --- Optional: write missing refs back to ProjectBiblicalTerms.xml ---
    if AddMissing.strip().lower() == u'yes' and missing_by_term:
        open_path = project_xml_path.encode('mbcs') if isinstance(project_xml_path, type(u'')) else project_xml_path
        # Back up the file as ProjectBiblicalTerms.xml.1, .2, etc.
        n = 1
        while True:
            backup_path = open_path + (u'.{}'.format(n)).encode('mbcs') if isinstance(open_path, bytes) else open_path + u'.{}'.format(n)
            if not os.path.isfile(backup_path):
                break
            n += 1
        shutil.copy2(open_path, backup_path)
        sys.stdout.write(u'# Copie de sauvegarde enregistrée sous {}\n'.format(project_xml_path + u'.{}'.format(n)))
        with open(open_path, 'rb') as f:
            tree = ET.parse(f)
        root = tree.getroot()
        added = 0
        for term_elem in root.iter(u'Term'):
            tid = term_elem.get(u'Id', u'')
            if not isinstance(tid, type(u'')):
                tid = tid.decode('utf-8')
            tid = unicodedata.normalize('NFD', tid)
            if ignore_dc and u'(DC)' in tid:
                continue
            if not include_hebrew and has_hebrew(tid):
                continue
            if not include_greek and has_greek(tid):
                continue
            if tid not in missing_by_term:
                continue
            refs = term_elem.find(u'References')
            if refs is None:
                refs = ET.SubElement(term_elem, u'References')
            existing_verses = refs.findall(u'Verse')
            if existing_verses:
                verse_tail = existing_verses[0].tail if existing_verses[0].tail else u'\n      '
                closing_tail = existing_verses[-1].tail if existing_verses[-1].tail else u'\n    '
                existing_verses[-1].tail = verse_tail
            else:
                verse_tail = refs.text if (refs.text and refs.text.strip() == u'') else u'\n      '
                closing_tail = u'\n    '
                refs.text = verse_tail
            new_verse_elems = []
            for norm_code in missing_by_term[tid]:
                project_code = norm_code + u'00'
                v = ET.SubElement(refs, u'Verse')
                v.text = project_code
                v.tail = verse_tail
                new_verse_elems.append(v)
                added += 1
            if new_verse_elems:
                new_verse_elems[-1].tail = closing_tail
            all_verses = list(refs)
            all_verses.sort(key=lambda v: v.text or u'')
            for v in list(refs):
                refs.remove(v)
            for i, v in enumerate(all_verses):
                v.tail = verse_tail if i < len(all_verses) - 1 else closing_tail
                refs.append(v)
        with open(open_path, 'wb') as f:
            tree.write(f, encoding='utf-8', xml_declaration=True)
        sys.stdout.write(u'# {} référence(s) manquante(s) ajoutée(s) à {}\n'.format(added, project_xml_path))
