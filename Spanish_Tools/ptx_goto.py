# -*- coding: utf-8 -*-
# Shared by the CMS "Report of ..." checks: makes the references in their HTML
# reports clickable. A "ptxgoto:MAT.1.5" link runs ParatextGoTo.exe, which
# sends the reference to Paratext through SantaFe focus sharing (Paratext
# follows it when the text window's scroll group follows other programs).
#
# Deploy this file and ParatextGoTo.exe into the cms folder beside the
# checks. A check imports it inside try/except, so without this file its
# report keeps plain-text references.
import os
import re

_EXE = u'ParatextGoTo.exe'
_REF_RE = re.compile(r'^\s*([A-Z0-9]{3}) +(\d+):(\d+|-)', re.UNICODE)
_BOOK_RE = re.compile(r'^\s*([A-Z0-9]{3})\s*$', re.UNICODE)

_enabled = None   # cached result of enabled(); None = not checked yet


def _to_unicode(s):
    if s is None:
        return u''
    if isinstance(s, bytes):
        try:
            return s.decode('utf-8')
        except UnicodeDecodeError:
            return s.decode('mbcs', 'replace')
    return s


def _exists(path):
    try:
        return os.path.isfile(path.encode('mbcs') if isinstance(path, type(u'')) else path)
    except Exception:
        return False


def _find_exe(project_dir):
    dirs = []
    try:
        dirs.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    if project_dir:
        dirs.append(os.path.normpath(os.path.join(_to_unicode(project_dir), u'..', u'cms')))
    for d in dirs:
        p = os.path.join(_to_unicode(d), _EXE)
        if _exists(p):
            return p
    return None


def _set_reg_value(winreg, key_path, name, value):
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
    try:
        try:
            current = winreg.QueryValueEx(key, name)[0]
        except WindowsError:
            current = None
        if current != value:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    finally:
        winreg.CloseKey(key)


def enabled(project_dir=None):
    """True when ParatextGoTo.exe was found and the ptxgoto: link type is
    registered for the current user (HKCU, no admin rights). Checked once
    per process."""
    global _enabled
    if _enabled is None:
        _enabled = False
        try:
            exe = _find_exe(project_dir)
            if exe:
                import _winreg as winreg
                base = u'Software' + os.sep + u'Classes' + os.sep + u'ptxgoto'
                _set_reg_value(winreg, base, u'', u'URL:Paratext go to')
                _set_reg_value(winreg, base, u'URL Protocol', u'')
                command = os.sep.join([base, u'shell', u'open', u'command'])
                _set_reg_value(winreg, command, u'', u'"{0}" "%1"'.format(exe))
                _enabled = True
        except Exception:
            _enabled = False
    return _enabled


def target(ref):
    """'GEN 1:5', 'GEN 1:5-6' or 'GEN 1:5,6' -> 'GEN.1.5' (first verse);
    a verse of '-' (text before the first verse) -> verse 0. Anything else
    (no chapter, '?', 'Book 3') -> None."""
    m = _REF_RE.match(_to_unicode(ref))
    if not m:
        return None
    verse = m.group(3)
    if verse == u'-':
        verse = u'0'
    return u'{0}.{1}.{2}'.format(m.group(1), int(m.group(2)), int(verse))


def book_target(code):
    """'GEN' -> 'GEN.1.0', the book's header (for per-book report rows)."""
    m = _BOOK_RE.match(_to_unicode(code))
    if not m:
        return None
    return m.group(1) + u'.1.0'


def link(inner_html, tgt):
    """Wraps already-escaped HTML in a ptxgoto: link; returns it unchanged
    when tgt is None or links are not enabled. target="_top" makes the click
    also work inside All Reports' iframes."""
    if not tgt or not _enabled:
        return inner_html
    return (u'<a class="ptxgoto" href="ptxgoto:{0}" target="_top" '
            u'style="color:inherit">{1}</a>').format(tgt, inner_html)


def hint_html(spanish=False):
    # The second sentence says what was registered and how to remove it, since the
    # registration happens without asking.
    if spanish:
        text = (u'Haga clic en una referencia para ir a ella en Paratext (el grupo de '
                u'desplazamiento de la ventana debe seguir a otros programas). Para esto se '
                u'registra el tipo de enlace "ptxgoto:" en su cuenta de Windows; para quitarlo, '
                u'ejecute ParatextGoTo.exe --unregister desde la carpeta cms.')
    else:
        text = (u"Click a reference to go there in Paratext (its window's "
                u'scroll group must follow other programs). For this, the "ptxgoto:" link '
                u'type is registered for your Windows account; to remove it, run '
                u'ParatextGoTo.exe --unregister from the cms folder.')
    return u'<p class="ptxgoto-hint">' + text + u'</p>'
