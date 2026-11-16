"""Installer checks. Run ONLY with a throwaway preferences folder:

    HOUDINI_USER_PREF_DIR=/tmp/parsec_prefs/houdini__HVER__ hython test_install.py
"""
import os
import tempfile
from pathlib import Path
import hou

prefs = Path(hou.text.expandString('$HOUDINI_USER_PREF_DIR')).resolve()
assert str(prefs).startswith(str(Path(tempfile.gettempdir()).resolve())), 'Refusing to run against real preferences: %s' % prefs
source = (Path(__file__).parent / 'install_parsec_nodes.py').read_text(encoding='utf-8')
toolbar = prefs / 'toolbar'
target = toolbar / 'parsec_nodes.shelf'
listing = lambda: sorted(p.name for p in toolbar.iterdir())

# Fresh install writes exactly one file.
space = {}
exec(compile(source, 'install_parsec_nodes.py', 'exec'), space)
assert listing() == ['parsec_nodes.shelf'], listing()
assert target.read_bytes() == space['SHELF']

# Second run in a row: nothing rewritten, no backup.
exec(compile(source, 'install_parsec_nodes.py', 'exec'), {})
assert listing() == ['parsec_nodes.shelf'], listing()

# Upgrade from older content: one timestamped backup holding the old bytes.
old = b'<shelfDocument><toolshelf name="parsec_nodes_shelf" label="Parsec Nodes v0.9"></toolshelf></shelfDocument>'
target.write_bytes(old)
exec(compile(source, 'install_parsec_nodes.py', 'exec'), {})
backups = [n for n in listing() if n.endswith('.bak')]
assert len(backups) == 1 and (toolbar / backups[0]).read_bytes() == old, listing()
assert target.read_bytes() == space['SHELF']
exec(compile(source, 'install_parsec_nodes.py', 'exec'), {})
assert [n for n in listing() if n.endswith('.bak')] == backups, listing()

# Failure after the temporary file exists: original untouched, no .tmp survives.
target.write_bytes(old)
real_replace = os.replace
def broken(*args): raise OSError('simulated full disk')
os.replace = broken
try:
    try: exec(compile(source, 'install_parsec_nodes.py', 'exec'), {})
    except OSError: pass
    else: raise AssertionError('Simulated failure did not surface')
finally:
    os.replace = real_replace
assert target.read_bytes() == old
assert not [n for n in listing() if n.endswith('.tmp')], listing()
# uninstall() removes only the shelf file.
exec(compile(source, 'install_parsec_nodes.py', 'exec'), space)
others = [n for n in listing() if n != 'parsec_nodes.shelf']
assert space['uninstall']() is True and not target.exists()
assert listing() == others, listing()
assert space['uninstall']() is False
print('PASS: installer is atomic, backs up once per change with a timestamp, and reports the version transition')
