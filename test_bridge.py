import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import parsec_nodes as bridge
import hou

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
    text = bridge.copy_nodes()
    raw, metadata = bridge.decode(text)
    assert metadata['category'] == 'Sop'
    target = hou.node('/obj').createNode('geo', 'bridge_test_target')
    target.deleteItems(target.children())
    # Name collision must preserve the existing destination node.
    old = target.createNode('null', 'test_box')
    bridge._network = lambda kwargs: Pane(target)
    added = bridge.paste_nodes()
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
    bridge.copy_nodes()
    imported = bridge.paste_nodes()
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
    assert bridge.paste_nodes() == ()
    assert set(target.allItems()) == before_cancel
    hou.licenseCategory = original_license
    ui.displayMessage = original_display
    print('PASS: connections, parameter values, sticky notes, network boxes, name collisions and corruption checks')
finally:
    hou.ui = original_ui
