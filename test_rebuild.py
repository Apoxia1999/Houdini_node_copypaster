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
    original_license_category = hou.licenseCategory()
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
    text = bridge.copy_rebuild()
    target = hou.node('/obj').createNode('geo', 'bridge_test_target')
    target.deleteItems(target.children())
    # Name collision must preserve the existing destination node.
    old = target.createNode('null', 'test_box')
    bridge._network = lambda kwargs: Pane(target)
    added = bridge.paste_rebuild()
    assert len(added) == 2, len(added)
    transform = next(n for n in added if isinstance(n, hou.OpNode) and n.type().name() == 'xform')
    assert transform.parm('tx').eval() == 3.25
    assert transform.input(0).type().name() == 'box'
    assert target.node('test_box') == old
    assert hou.licenseCategory() == original_license_category
    for item in hou.selectedItems(): item.setSelected(False)
    wrangle = src.createNode('attribwrangle', 'my_wrangle')
    wrangle.parm('snippet').set('@P.y += chf("amplitude");')
    group = wrangle.parmTemplateGroup()
    group.append(hou.FloatParmTemplate('amplitude', 'Amplitude', 1, default_value=(2.0,)))
    group.append(hou.RampParmTemplate('profile', 'Profile', hou.rampParmType.Float))
    wrangle.setParmTemplateGroup(group)
    wrangle.parm('amplitude').setExpression('$F * 0.1', language=hou.exprLanguage.Hscript)
    wrangle.parm('profile').set(hou.Ramp((hou.rampBasis.Linear, hou.rampBasis.Linear), (0.0, 1.0), (0.2, 0.8)))
    wrangle.setSelected(True)
    bridge.copy_rebuild()
    imported = bridge.paste_rebuild()
    assert len(imported) == 1
    clone = imported[0]
    assert clone.parm('snippet').unexpandedString() == wrangle.parm('snippet').unexpandedString()
    assert clone.parm('amplitude').expression() == '$F * 0.1'
    assert clone.parm('profile').evalAsRamp().values() == wrangle.parm('profile').evalAsRamp().values()
    # Animations: weighted split tangents, automatic slopes, discontinuities,
    # subframes and extrapolation must match at and between keys.
    for item in hou.selectedItems(): item.setSelected(False)
    for channel, interpolation, extrapolation in (
        ('tx', 'bezier()', hou.parmExtrapolate.CycleOffset),
        ('ty', 'linear()', hou.parmExtrapolate.Oscillate),
        ('tz', 'constant()', hou.parmExtrapolate.Cycle),
        ('rx', 'cubic()', hou.parmExtrapolate.Slope),
        ('ry', 'spline()', hou.parmExtrapolate.Hold),
        ('sx', 'bezier()', hou.parmExtrapolate.Hold)):
        parm = b.parm(channel)
        keys = []
        for i, (frame, value) in enumerate(((1.0, 0.2), (12.5, 4.0), (33.25, -2.0))):
            key = hou.Keyframe()
            key.setFrame(frame)
            key.setValue(value)
            key.setExpression(interpolation, hou.exprLanguage.Hscript)
            if channel == 'tx':
                key.interpretAccelAsRatio(False)
                key.setSlope(1.5 + i)
                key.setInSlope(-0.5 - i)
                key.setAccel(0.1 + i * 0.02)
                key.setInAccel(0.2 + i * 0.03)
                if i == 1: key.setInValue(3.0)
            elif channel in ('rx', 'sx'):
                key.setSlopeAuto(True)
                if channel != 'sx': key.setInSlopeAuto(True)
            keys.append(key)
        parm.setKeyframes(keys)
        parm.setKeyframeExtrapolation(True, extrapolation)
        parm.setKeyframeExtrapolation(False, extrapolation)
    # A single numeric key is also animation, not an expression-only shortcut.
    single = hou.Keyframe()
    single.setFrame(7.25)
    single.setValue(8.0)
    b.parm('rz').setKeyframe(single)
    b.setSelected(True)
    bridge.copy_rebuild()
    animation_text = ui.text
    imported = bridge.paste_rebuild()[0]
    samples = [(-0.5 + i * 0.017) for i in range(180)]
    for channel in ('tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx'):
        original = b.parm(channel)
        duplicate = imported.parm(channel)
        assert [bridge._describe_key(k) for k in original.keyframes()] == [bridge._describe_key(k) for k in duplicate.keyframes()], channel
        for t in samples:
            assert abs(original.evalAtTime(t) - duplicate.evalAtTime(t)) < 1e-8, (channel, t, original.evalAtTime(t), duplicate.evalAtTime(t))
        for before in (True, False):
            assert original.keyframeExtrapolation(before) == duplicate.keyframeExtrapolation(before)
    # Preserve key times and tangent units when the destination uses another FPS.
    original_fps = hou.fps()
    expected = {c: [b.parm(c).evalAtTime(t) for t in samples] for c in ('tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx')}
    hou.setFps(30)
    ui.text = animation_text
    at_30fps = bridge.paste_rebuild()[0]
    for channel, values in expected.items():
        for t, value in zip(samples, values):
            assert abs(at_30fps.parm(channel).evalAtTime(t) - value) < 1e-8, ('30fps', channel, t)
    hou.setFps(original_fps)
    # String animation / Python expressions preserve the keyframe subclass.
    for item in hou.selectedItems(): item.setSelected(False)
    textnode = src.createNode('font')
    stringkey = hou.StringKeyframe()
    stringkey.setFrame(1.5)
    stringkey.setExpression('"Frame " + str(hou.frame())', hou.exprLanguage.Python)
    stringkey2 = hou.StringKeyframe()
    stringkey2.setFrame(13.25)
    stringkey2.setExpression('"Later " + str(hou.frame())', hou.exprLanguage.Python)
    textnode.parm('text').setKeyframes((stringkey, stringkey2))
    textnode.setSelected(True)
    bridge.copy_rebuild()
    stringclone = bridge.paste_rebuild()[0]
    assert [bridge._describe_key(k) for k in stringclone.parm('text').keyframes()] == [bridge._describe_key(k) for k in textnode.parm('text').keyframes()]
    for t in (0, 0.125, 0.5):
        assert stringclone.parm('text').evalAtTime(t) == textnode.parm('text').evalAtTime(t)
    print('PASS: reconstruction plus numeric/string animation, interpolation, split/automatic tangents, subframes, extrapolation and differing FPS (1080+ evaluated curve samples)')
finally:
    hou.ui = original_ui
