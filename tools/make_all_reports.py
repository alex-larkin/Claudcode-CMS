# -*- coding: utf-8 -*-
"""Writes the Spanish and French All Reports from the English one:

    python CMS\\tools\\make_all_reports.py

  CMS/Spanish_Tools/All_Reports_sp.cms + All_Reports_sp.py
  CMS/French_Tools/All_Reports_fr.cms  + All_Reports_fr.py

The .py is the English All_Reports.py with exact string replacements (each must match once),
so the logic stays the English logic: the localized sub-scripts and their report files, the
section titles and notes, and one change of behaviour: the sub-script is decoded as UTF-8
before compile(), because compile() of raw bytes ignores the '# -*- coding: utf-8 -*-' line
under IronPython and the translated reports came out garbled. Rerun after changing the
English All Reports. Output: UTF-8 with BOM, the English file's line endings.
"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CMS = os.path.dirname(HERE)
EN_PY = os.path.join(CMS, 'all_reports', 'All_Reports.py')
EN_CMS = os.path.join(CMS, 'all_reports', 'All_Reports.cms')

# English script -> (title, script, report file) per language, in the English order.
CHECKS = [
    ('toc_examiner.py', 'TocExaminerReport.html',
     (u'Informe de los TOC', 'toc_examiner_sp.py', u'InformeExaminadorTOC.html'),
     (u'Rapport de la table des matières', 'toc_examiner_fr.py', u'RapportTableMatieres.html')),
    ('Find_Titles.py', 'FindTitlesReport.html',
     (u'Informe de los títulos', 'Find_Titles_sp.py', u'InformeTitulos.html'),
     (u'Rapport des titres', 'Find_Titles_fr.py', u'RapportTitres.html')),
    ('find_section_heads.py', 'FindSectionHeadsReport.html',
     (u'Informe de los encabezados de sección', 'find_section_heads_sp.py', u'InformeEncabezadosSeccion.html'),
     (u'Rapport des titres de section', 'find_section_heads_fr.py', u'RapportTitresSection.html')),
    ('quotation_examiner.py', 'QuotationExaminerReport.html',
     (u'Informe de comillas', 'quotation_examiner_sp.py', u'InformeExaminadorComillas.html'),
     (u'Rapport des guillemets', 'quotation_examiner_fr.py', u'RapportExamenGuillemets.html')),
    ('q_error.py', 'QErrorsReport.html',
     (u'Informe de errores en q', 'q_error_sp.py', u'InformeErroresQ.html'),
     (u'Rapport des erreurs de poésie', 'q_error_fr.py', u'RapportErreursQ.html')),
    ('report_nested_styles.py', 'NestedStylesReport.html',
     (u'Informe de estilos anidados', 'report_nested_styles_sp.py', u'InformeEstilosAnidados.html'),
     (u'Rapport des styles imbriqués', 'report_nested_styles_fr.py', u'RapportStylesImbriques.html')),
    # The Spanish Marker Space check runs the English MarkerSpace.py.
    ('MarkerSpace.py', 'MarkerSpaceReport.html',
     (u'Informe de espacios en marcadores', 'MarkerSpace.py', u'MarkerSpaceReport.html'),
     (u'Rapport des espaces autour des marqueurs', 'MarkerSpace_fr.py', u'RapportEspacesMarqueurs.html')),
    ('find_footnotes.py', 'FootnotesReport.html',
     (u'Informe de las notas al pie', 'find_footnotes_sp.py', u'InformeNotasAlPie.html'),
     (u'Rapport des notes de bas de page', 'find_footnotes_fr.py', u'RapportNotesBasDePage.html')),
    ('Find_caption.py', 'FigureCaptions.html',
     (u'Informe de leyendas de figuras', 'Find_caption_sp.py', u'InformeDeFigura.html'),
     (u'Rapport des légendes d’illustrations', 'Find_caption_fr.py', u'LegendesIllustrations.html')),
    ('capital_at_verse.py', 'CapitalAtVerseReport.html',
     (u'Informe de mayúscula al inicio de versículo', 'capital_at_verse_sp.py', u'CapitalAtVerseReport.html'),
     (u'Rapport des majuscules en début de verset', 'capital_at_verse_fr.py', u'RapportMajusculeDebutVerset.html')),
]
EN_TITLES = [u'Report of TOC', u'Report of Titles', u'Report of Section Heads', u'Report of Quotation marks',
             u'Report of Poetry errors', u'Report of Nested Styles', u'Report of Marker Spaces',
             u'Report of Footnotes', u'Report of Figure Captions', u'Report of Capital at Verse']

LANGS = {
    'es': {
        'col': 2, 'folder': 'Spanish_Tools', 'suffix': '_sp',
        'skipped': u'Omitido (desactivado por una opción).',
        'notfound': u'No se encontró el script: puede que esta verificación aún no esté instalada.',
        'crashed': u'No se pudo ejecutar esta verificación: vea AllReportsDebug.log.',
        'noreport': u'No se produjo ningún archivo de informe.',
        'showing': (u'<p style="color:red;font-weight:bold">Se muestran los primeros {0} de {1} '
                    u'problemas encontrados. Ejecute "{2}" por separado para ver el resto.</p>'),
        'title': u'Todos los informes', 'project': u'<p>Proyecto: <b>{0}</b></p>',
        'report': u'InformeTodosLosInformes.html',
        'out_ok': u'# Ejecute cada verificacion por separado para ver la lista de problemas.\\n',
        'out_err': u'# Error al escribir el informe combinado; vea AllReportsDebug.log\\n',
        'out_nodir': u'# Error: no se pudo determinar la carpeta del proyecto; no se escribio ningun informe.\\n',
    },
    'fr': {
        'col': 3, 'folder': 'French_Tools', 'suffix': '_fr',
        'skipped': u'Ignoré (désactivé par une option).',
        'notfound': u'Script introuvable : cette vérification n’est peut-être pas encore installée.',
        'crashed': u'Cette vérification n’a pas pu s’exécuter : voir AllReportsDebug.log.',
        'noreport': u'Aucun fichier de rapport n’a été produit.',
        'showing': (u'<p style="color:red;font-weight:bold">Affichage des {0} premiers problèmes '
                    u'sur {1}. Exécutez « {2} » seul pour voir les autres.</p>'),
        'title': u'Tous les rapports', 'project': u'<p>Projet : <b>{0}</b></p>',
        'report': u'RapportTousLesRapports.html',
        'out_ok': u'# Executez chaque verification seule pour voir la liste des problemes.\\n',
        'out_err': u'# Erreur en ecrivant le rapport combine ; voir AllReportsDebug.log\\n',
        'out_nodir': u'# Erreur : dossier du projet introuvable ; aucun rapport ecrit.\\n',
    },
}

DECODE_OLD = u"""            with open(_script_path, 'rb') as _f:
                _src = _f.read()
            _code = compile(_src, _script_path, 'exec')"""
DECODE_NEW = u"""            with open(_script_path, 'rb') as _f:
                _src = _f.read()
            # The translated scripts hold accented text. compile() of raw bytes ignores their
            # coding line under IronPython (the text came out garbled), so decode them first and
            # blank the coding cookie, which a unicode source may not carry (same line count).
            _src = _src.decode('utf-8')
            if _src.startswith(u'\\ufeff'):
                _src = _src[1:]
            _src = re.sub(u'^([ \\t\\f]*#.*?)coding[:=]', u'\\\\1c0ding ', _src, count=2, flags=re.M)
            _code = compile(_src, _script_path, 'exec')"""


def make_py(lang):
    L = LANGS[lang]
    raw = io.open(EN_PY, encoding='utf-8-sig', newline='').read()
    nl = '\r\n' if '\r\n' in raw else '\n'
    s = raw.replace('\r\n', '\n')

    def sub(old, new, count=1):
        global_s = s
        n = global_s.count(old)
        if n != count:
            raise SystemExit('%s: expected %d of %r, found %d' % (lang, count, old[:60], n))
        return global_s.replace(old, new)

    s = sub(u'import os\nimport sys as _sys\n', u'import os\nimport re\nimport sys as _sys\n')
    for (en_py, en_html, es, fr), en_title in zip(CHECKS, EN_TITLES):
        title, py, html = es if lang == 'es' else fr
        # _CHECKS row
        row_old = u"(u'%s', '%s', " % (en_title, en_py)
        s = sub(row_old, u"(u'%s', '%s', " % (title, py))
        s = sub(u"u'%s')," % en_html, u"u'%s')," % html)
        # _include / _TRUNCATE_CONFIG keys and the special cases
        n = s.count(u"'%s'" % en_py)
        s = s.replace(u"'%s':" % en_py, u"'%s':" % py)
        s = s.replace(u"_filename == '%s'" % en_py, u"_filename == '%s'" % py)
    # Every row's dev-repo folder: the localized scripts all sit in one folder.
    for sub_folder in (u'toc_examiner', u'find_titles', u'find_section_heads', u'quotation_examiner',
                       u'q_errors', u'report_nested_styles', u'marker_space', u'find_footnotes',
                       u'figure_caption', u'capital_at_verse'):
        s = sub(u", '%s', u'" % sub_folder, u", '%s', u'" % L['folder'])
    s = sub(DECODE_OLD, DECODE_NEW)
    s = sub(u"'note': u'Skipped (disabled by option).'", u"'note': u'%s'" % L['skipped'])
    s = sub(u"'note': u'Script not found -- this check may not be deployed yet.'", u"'note': u'%s'" % L['notfound'])
    s = sub(u"'note': u'This check could not be run -- see AllReportsDebug.log.'", u"'note': u'%s'" % L['crashed'])
    s = sub(u"'note': u'No report file was produced.'", u"'note': u'%s'" % L['noreport'])
    s = sub(u"""                    u'<p style="color:red;font-weight:bold">Showing the first {0} of {1} '
                    u'issues found. Run "{2}" individually to see the rest.</p>'""",
            u"                    u'%s'" % L['showing'].replace(u"'", u"\\'"))
    s = sub(u"u'<title>All Reports</title>'", u"u'<title>%s</title>'" % L['title'])
    s = sub(u"u'<h1>All Reports</h1>'", u"u'<h1>%s</h1>'" % L['title'])
    s = sub(u"u'<p>Project: <b>{0}</b></p>'", u"u'%s'" % L['project'])
    s = sub(u"u'AllReportsReport.html'", u"u'%s'" % L['report'])
    s = sub(u"u'# Run individual checks to see a list of issues.\\n'", u"u'%s'" % L['out_ok'])
    s = sub(u"u'# Error writing combined report; see AllReportsDebug.log\\n'", u"u'%s'" % L['out_err'])
    s = sub(u"u'# Error: could not determine project directory; no report written.\\n'", u"u'%s'" % L['out_nodir'])
    # Non-ASCII only inside u'' strings: check every line holding some is a string line.
    for i, line in enumerate(s.split('\n')):
        if any(ord(ch) > 127 for ch in line) and u"u'" not in line:
            raise SystemExit('%s: non-ASCII outside a u string on line %d' % (lang, i + 1))
    out = os.path.join(CMS, L['folder'], 'All_Reports%s.py' % L['suffix'])
    io.open(out, 'w', encoding='utf-8-sig', newline='').write(s.replace('\n', nl))
    return out


CMS_TEXT = {
    'es': {
        'check': u'Todos los informes',
        'submenu': u'Herramientas_Español',
        'description': (u'Ejecuta el Informe de los TOC, de los títulos, de los encabezados de sección, de comillas, '
                        u'de errores en q, de estilos anidados, de espacios en marcadores, de las notas al pie, de '
                        u'leyendas de figuras y de mayúscula al inicio de versículo, en ese orden, y reúne sus '
                        u'informes HTML en un solo InformeTodosLosInformes.html (se abre automáticamente). Esta lista '
                        u'de resultados es a propósito solo un mensaje de estado: ejecute una verificación por '
                        u'separado si necesita su lista detallada de problemas. Una verificación cuyo script no se '
                        u'encuentra aparece como sección omitida en lugar de detener la ejecución. Las opciones '
                        u'Incluir permiten desactivar verificaciones para una ejecución; todas son Sí por defecto. '
                        u'Las demás opciones son las de Mayúscula al inicio de versículo, que se le pasan cuando se '
                        u'ejecuta.'),
        'include': u'Incluir {0}', 'skip': u'Elija No para omitir {0} en esta ejecución.',
        'forward': u'Se pasa al Informe de mayúscula al inicio de versículo.',
    },
    'fr': {
        'check': u'Tous les rapports',
        'submenu': u'Outils_Français',
        'description': (u'Exécute le rapport de la table des matières, des titres, des titres de section, des '
                        u'guillemets, des erreurs de poésie, des styles imbriqués, des espaces autour des marqueurs, '
                        u'des notes de bas de page, des légendes d’illustrations et des majuscules en début de '
                        u'verset, dans cet ordre, et réunit leurs rapports HTML en un seul '
                        u'RapportTousLesRapports.html (ouvert automatiquement). Cette liste de résultats n’est '
                        u'volontairement qu’un message d’état : exécutez une vérification seule pour avoir sa liste '
                        u'détaillée de problèmes. Une vérification dont le script est introuvable apparaît comme '
                        u'section ignorée, sans arrêter l’exécution. Les options Inclure permettent de désactiver '
                        u'des vérifications pour une exécution ; elles sont toutes à Oui par défaut. Les autres '
                        u'options sont celles des majuscules en début de verset, qui lui sont transmises quand il '
                        u's’exécute.'),
        'include': u'Inclure : {0}', 'skip': u'Choisissez Non pour ne pas exécuter « {0} » cette fois.',
        'forward': u'Transmis au rapport des majuscules en début de verset.',
    },
}
INCLUDE_ORDER = ['IncludeToc', 'IncludeTitles', 'IncludeSectionHeads', 'IncludeQuotationMarks',
                 'IncludePoetryErrors', 'IncludeNestedStyles', 'IncludeMarkerSpaces', 'IncludeFootnotes',
                 'IncludeFigureCaptions', 'IncludeCapitalAtVerse']


def make_cms(lang):
    """The English .cms with \\check/\\submenu/\\script/\\description and the option texts changed.
    The Capital at Verse options take their texts from that check's own translated .cms."""
    L = LANGS[lang]
    T = CMS_TEXT[lang]
    raw = io.open(EN_CMS, encoding='utf-8-sig', newline='').read()
    nl = '\r\n' if '\r\n' in raw else '\n'
    cav = io.open(os.path.join(CMS, L['folder'], 'capital_at_verse%s.cms' % L['suffix']),
                  encoding='utf-8-sig').read().replace('\r\n', '\n')
    cav_opts = {}
    name = None
    for line in cav.split('\n'):
        if line.startswith(u'\\optionName '):
            name = line.split(None, 1)[1].strip()
            cav_opts[name] = {}
        elif name and line.startswith(u'\\optionLocalizedName '):
            cav_opts[name]['loc'] = line.split(None, 1)[1]
        elif name and line.startswith(u'\\optionDescription '):
            cav_opts[name]['desc'] = line.split(None, 1)[1]
    titles = [(c[2] if lang == 'es' else c[3])[0] for c in CHECKS]
    out_lines = []
    name = None
    for line in raw.replace('\r\n', '\n').split('\n'):
        if line.startswith(u'\\check '):
            line = u'\\check ' + T['check']
        elif line.startswith(u'\\submenu '):
            line = u'\\submenu ' + T['submenu']
        elif line.startswith(u'\\script '):
            line = u'\\script All_Reports%s.py' % L['suffix']
        elif line.startswith(u'\\description '):
            line = u'\\description ' + T['description']
        elif line.startswith(u'\\optionName '):
            name = line.split(None, 1)[1].strip()
        elif name and (line.startswith(u'\\optionLocalizedName ') or line.startswith(u'\\optionDescription ')):
            loc = line.startswith(u'\\optionLocalizedName ')
            if name in INCLUDE_ORDER:
                t = titles[INCLUDE_ORDER.index(name)]
                text = T['include'].format(t) if loc else T['skip'].format(t)
            elif name in cav_opts:
                o = cav_opts[name]
                text = o['loc'] if loc else T['forward'] + u' ' + o['desc']
            else:
                raise SystemExit('%s: no text for option %s' % (lang, name))
            line = (u'\\optionLocalizedName ' if loc else u'\\optionDescription ') + text
        out_lines.append(line)
    out = os.path.join(CMS, L['folder'], 'All_Reports%s.cms' % L['suffix'])
    io.open(out, 'w', encoding='utf-8-sig', newline='').write(nl.join(out_lines))
    return out


if __name__ == '__main__':
    for lang in ('es', 'fr'):
        print(make_py(lang))
        print(make_cms(lang))
