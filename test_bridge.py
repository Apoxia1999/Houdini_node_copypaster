import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import os
import tempfile
import parsec_nodes as bridge
import hou

# Native .cpio transport (v1). Test-only: it is NOT part of the shipped module or the shelf,
# because loadItemsFromFile can restore embedded HDA definitions and their callbacks.
def copy_nodes(kwargs=None):
    import hou
    items = tuple(hou.selectedItems())
    if not items:
        raise ValueError('Selecciona los nodos que quieres copiar.')
    parent = items[0].parent()
    if any(item.parent() != parent for item in items):
        raise ValueError('Selecciona elementos de una sola red.')
    # A selected network box does not implicitly serialize its contents.
    expanded = set(items)
    for item in items:
        if isinstance(item, hou.NetworkBox):
            expanded.update(item.items(recurse=True))
    items = tuple(expanded)
    with tempfile.TemporaryDirectory(prefix='houdini_parsec_') as folder:
        path = os.path.join(folder, 'nodes.cpio')
        parent.saveItemsToFile(items, path)
        with open(path, 'rb') as handle:
            text = bridge.encode(handle.read(), parent.childTypeCategory().name(), hou.applicationVersionString(), hou.licenseCategory().name())
    hou.ui.copyTextToClipboard(text)
    hou.ui.setStatusMessage('Parsec Nodes: copiados %d elementos (%d caracteres). Abre Parsec y pulsa Paste Nodes.' % (len(items), len(text)))
    return text


def paste_nodes(kwargs=None):
    import hou
    raw, envelope = bridge.decode(hou.ui.getTextFromClipboard())
    pane = bridge._network(kwargs)
    parent = pane.pwd()
    category = parent.childTypeCategory()
    if category is None or category.name() != envelope['category']:
        raise ValueError('Abre una red de tipo %s para pegar estos nodos.' % envelope['category'])
    if not bridge._license_gate(envelope):
        return ()
    before = set(parent.allItems())
    warning = None
    with tempfile.TemporaryDirectory(prefix='houdini_parsec_') as folder:
        path = os.path.join(folder, 'nodes.cpio')
        with open(path, 'wb') as handle:
            handle.write(raw)
        with hou.undos.group('Paste Parsec Nodes'):
            try:
                parent.loadItemsFromFile(path)
            except hou.LoadWarning as exc:
                warning = str(exc)
            except Exception:
                # Remove partial imports without touching pre-existing items.
                added = set(parent.allItems()) - before
                if added:
                    parent.deleteItems(tuple(added))
                raise
            added = set(parent.allItems()) - before
            # Move top-level items together. Box contents move with their box.
            roots = [item for item in added if item.parentNetworkBox() not in added]
            if roots:
                center = sum((item.position() for item in roots), hou.Vector2(0, 0)) / len(roots)
                offset = pane.visibleBounds().center() - center
                for item in roots:
                    item.move(offset)
            for item in parent.selectedItems():
                item.setSelected(False)
            for item in added:
                item.setSelected(True)
    hou.ui.setStatusMessage('Parsec Nodes: pegados %d elementos desde Houdini %s. Ctrl+Z deshace.' % (len(added), envelope.get('version', '?')))
    if warning:
        hou.ui.displayMessage('Los nodos se han cargado con avisos:\n' + warning, severity=hou.severityType.Warning)
    return tuple(added)


class UI:
    text = ''
    def copyTextToClipboard(self, text): self.text = text
    def getTextFromClipboard(self): return self.text
    def setStatusMessage(self, text): print(text)
    def displayMessage(self, text, **kwargs): raise AssertionError(text)

class Pane:
    def __init__(self, parent): self.parent = parent
    def pwd(self): return self.parent
    def visibleBounds(self): return hou.BoundingRect(-5, -5, 5, 5)

ui = UI()
original_ui = getattr(hou, 'ui', None)
hou.ui = ui
try:
    src = hou.node('/obj').createNode('geo', 'bridge_test_source')
    src.deleteItems(src.children())
    a = src.createNode('box', 'test_box')
    b = src.createNode('xform', 'test_transform')
    b.setInput(0, a)
    b.parm('tx').set(3.25)
    a.setPosition(hou.Vector2(1, 3))
    b.setPosition(hou.Vector2(1, 1))
    note = src.createStickyNote()
    note.setText('Hola desde Linux')
    for item in (a, b, note): item.setSelected(True)
    text = copy_nodes()
    raw, metadata = bridge.decode(text)
    assert metadata['category'] == 'Sop'
    target = hou.node('/obj').createNode('geo', 'bridge_test_target')
    target.deleteItems(target.children())
    # Name collision must preserve the existing destination node.
    old = target.createNode('null', 'test_box')
    bridge._network = lambda kwargs: Pane(target)
    added = paste_nodes()
    assert len(added) == 3, len(added)
    transform = next(n for n in added if isinstance(n, hou.OpNode) and n.type().name() == 'xform')
    assert transform.parm('tx').eval() == 3.25
    assert transform.input(0).type().name() == 'box'
    assert target.node('test_box') == old
    assert any(isinstance(n, hou.StickyNote) and n.text() == 'Hola desde Linux' for n in added)
    # Copy the box including its contained nodes.
    for item in hou.selectedItems(): item.setSelected(False)
    box = src.createNetworkBox()
    box.addItem(a)
    box.addItem(b)
    box.fitAroundContents()
    box.setSelected(True)
    copy_nodes()
    imported = paste_nodes()
    assert len(imported) == 3
    assert any(isinstance(n, hou.NetworkBox) for n in imported)
    # Detect truncated or changed transport before importing anything.
    for bad in ('plain text', text[:-5], text.replace('"sha256":"', '"sha256":"0', 1)):
        try: bridge.decode(bad)
        except ValueError: pass
        else: raise AssertionError('Corruption was not detected')
    for length in (0, 1, 10000):
        data = bytes(range(256)) * length
        assert bridge.decode(bridge.encode(data, 'Sop', 'test'))[0] == data
    original_license = hou.licenseCategory
    original_display = ui.displayMessage
    hou.licenseCategory = lambda: hou.licenseCategoryType.Commercial
    ui.displayMessage = lambda *args, **kwargs: 0
    before_cancel = set(target.allItems())
    assert paste_nodes() == ()
    assert set(target.allItems()) == before_cancel
    hou.licenseCategory = original_license
    ui.displayMessage = original_display
    print('PASS: connections, parameter values, sticky notes, network boxes, name collisions and corruption checks')
finally:
    hou.ui = original_ui
