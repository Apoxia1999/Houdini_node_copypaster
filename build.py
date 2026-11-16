from pathlib import Path
import base64
import zipfile
root = Path(__file__).resolve().parent
module = (root / 'parsec_nodes.py').read_text(encoding='utf-8')
shelf = '''<?xml version="1.0" encoding="UTF-8"?>
<shelfDocument>
  <toolshelf name="parsec_nodes_shelf" label="Parsec Nodes v2.1">
    <memberTool name="parsec_nodes_copy"/>
    <memberTool name="parsec_nodes_paste"/>
  </toolshelf>
'''
for action, label, icon in [('copy', 'Copy Nodes', 'BUTTONS_copy'), ('paste', 'Paste Nodes', 'BUTTONS_paste')]:
    # Inline module keeps this independent of the host's Python minor version.
    script = 'namespace = {}\nexec(compile(%r, "parsec_nodes.py", "exec"), namespace)\nnamespace["run"](%r, kwargs)\n' % (module, action)
    assert ']]>' not in script
    shelf += '  <tool name="parsec_nodes_%s" label="%s" icon="%s">\n    <script scriptType="python"><![CDATA[%s]]></script>\n  </tool>\n' % (action, label, icon, script)
shelf += '</shelfDocument>\n'
(root / 'parsec_nodes.shelf').write_text(shelf, encoding='utf-8')
installer = '''# Run this file from Houdini's Python Shell. Works on Linux and Windows.
import base64
import datetime
import os
import re
from pathlib import Path
import hou

SHELF = base64.b64decode(%r)

def _label(data):
    match = re.search(rb'<toolshelf name="parsec_nodes_shelf" label="([^"]*)"', data or b'')
    return match.group(1).decode('utf-8', 'replace') if match else 'ninguna'


def install():
    prefs = Path(hou.text.expandString('$HOUDINI_USER_PREF_DIR'))
    toolbar = prefs / 'toolbar'
    toolbar.mkdir(parents=True, exist_ok=True)
    target = toolbar / 'parsec_nodes.shelf'
    previous = target.read_bytes() if target.exists() else None
    print('Parsec Nodes: version instalada: %%s. Version nueva: %%s.' %% (_label(previous), _label(SHELF)))
    if previous != SHELF:
        if previous is not None:
            stamp = datetime.datetime.now().strftime('%%Y-%%m-%%dT%%H%%M%%S')
            target.with_name('parsec_nodes.shelf.%%s.bak' %% stamp).write_bytes(previous)
        # Atomic: a failed or interrupted write never leaves a half-written shelf.
        temporary = target.with_suffix('.shelf.tmp')
        try:
            temporary.write_bytes(SHELF)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
    if hou.isUIAvailable():
        hou.shelves.loadFile(str(target))
        shelf_note = ''
        try:
            sets = hou.ui.curDesktop().shelfDock().shelfSets()
            if sets:
                shelf = hou.shelves.shelves()['parsec_nodes_shelf']
                if shelf not in sets[0].shelves():
                    sets[0].setShelves(sets[0].shelves() + (shelf,))
            else:
                shelf_note = 'Para mostrar la pestana: menu + de la shelf > Shelves > Parsec Nodes.'
        except Exception:
            shelf_note = 'El conjunto de shelves activo no permite cambios automaticos.\\nPara mostrar la pestana: menu + de la shelf > Shelves > Parsec Nodes.'
        hou.ui.displayMessage('Parsec Nodes v2.1 - Reconstruccion instalado.\\n\\n' + shelf_note + '\\n\\nUsa Copy Nodes en el equipo de origen y Paste Nodes en el destino.\\n\\nPara asignar un atajo: Ctrl+Alt+Shift y clic en el boton de la shelf.\\n\\n' + str(target))
    print('Parsec Nodes instalado: ' + str(target))
    return str(target)

install()
''' % base64.b64encode(shelf.encode()).decode()
(root / 'install_parsec_nodes.py').write_text(installer, encoding='utf-8')
import zlib
bootstrap = "import base64,zlib; exec(compile(zlib.decompress(base64.b64decode(%r)), '<Parsec Nodes installer>', 'exec'))" % base64.b64encode(zlib.compress(installer.encode(), 9)).decode()
(root / 'INSTALAR_EN_WINDOWS.txt').write_text(bootstrap + '\n', encoding='utf-8')
with zipfile.ZipFile(root / 'Houdini_node_copypaster-v2.1.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in ['install_parsec_nodes.py', 'parsec_nodes.py', 'parsec_nodes.shelf', 'README.md', 'INSTALAR_EN_WINDOWS.txt']:
        if (root / name).exists():
            archive.write(root / name, 'Houdini_node_copypaster/' + name)
print('Built shelf and standalone installer')
