import base64
import hashlib
import json
import os
import sys
import tempfile
import zlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import parsec_nodes as bridge
import hou

class UI:
    text = ''
    answer = None  # None: any dialog fails the test. Otherwise the button index to press.
    def __init__(self): self.shown = []
    def copyTextToClipboard(self, text): self.text = text
    def getTextFromClipboard(self): return self.text
    def setStatusMessage(self, text): print(text)
    def displayMessage(self, text, **kwargs):
        self.shown.append((text, kwargs.get('buttons')))
        if self.answer is None: raise AssertionError(text)
        return self.answer

MARKER = os.path.join(tempfile.gettempdir(), 'parsec_nodes_PWNED')

def craft(nodes, category='Sop', license_name='Apprentice', drop_license=False):
    # Hand-made payload: prefix + JSON envelope with zlib + base64 of a JSON body.
    raw = json.dumps({'format': 'rebuild-json-v1', 'fps': 24, 'nodes': nodes}).encode('utf-8')
    envelope = {'category': category, 'version': 'crafted', 'license': license_name, 'size': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(),
                'data': base64.b64encode(zlib.compress(raw, 9)).decode('ascii')}
    if drop_license: del envelope['license']
    return 'HOUDINI_PARSEC_REBUILD_V1:' + json.dumps(envelope)

def record(node_type, parms=(), **extra):
    data = {'name': 'crafted', 'type': node_type, 'position': [0, 0], 'color': [1, 1, 1], 'comment': '',
            'parms': list(parms), 'flags': {'isDisplayFlagSet': True}, 'inputs': []}
    data.update(extra)
    return data

def crafted_key(expression, language='Hscript', kind='numeric'):
    data = {'kind': kind, 'time': 0.0, 'expression': expression, 'language': language}
    if kind == 'numeric':
        data.update({'isValueSet': False, 'isSlopeSet': False, 'isAccelSet': False, 'isValueTied': True,
                     'isSlopeTied': True, 'isAccelTied': True, 'isValueUsed': False, 'isSlopeUsed': False,
                     'isAccelUsed': False, 'isSlopeAuto': False, 'isInSlopeAuto': False,
                     'isAccelInterpretedAsRatio': True})
    return data

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
    # VEX and spare parameters are announced once; Cancel creates nothing, Pegar pastes.
    before = set(target.allItems())
    ui.shown, ui.answer = [], 0
    assert bridge.paste_rebuild() == () and set(target.allItems()) == before
    assert len(ui.shown) == 1 and ui.shown[0][1] == ('Cancelar', 'Pegar'), ui.shown
    ui.answer = 1
    imported = bridge.paste_rebuild()
    ui.answer = None
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
    copied = json.loads(bridge.decode(bridge.PREFIX + animation_text[len(bridge.REBUILD_PREFIX):])[0])
    exact = {p['name'] for p in copied['nodes'][0]['parms'] if 'channel_text' in p}
    assert exact == {'tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx'}, exact
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
    # String animation preserves the keyframe subclass (HScript; Python is refused, see below).
    for item in hou.selectedItems(): item.setSelected(False)
    textnode = src.createNode('font')
    stringkey = hou.StringKeyframe()
    stringkey.setFrame(1.5)
    stringkey.setExpression('strcat("Frame ", ftoa($F))', hou.exprLanguage.Hscript)
    stringkey2 = hou.StringKeyframe()
    stringkey2.setFrame(13.25)
    stringkey2.setExpression('strcat("Later ", ftoa($F))', hou.exprLanguage.Hscript)
    textnode.parm('text').setKeyframes((stringkey, stringkey2))
    textnode.setSelected(True)
    bridge.copy_rebuild()
    stringclone = bridge.paste_rebuild()[0]
    assert [bridge._describe_key(k) for k in stringclone.parm('text').keyframes()] == [bridge._describe_key(k) for k in textnode.parm('text').keyframes()]
    for t in (0, 0.125, 0.5):
        assert stringclone.parm('text').evalAtTime(t) == textnode.parm('text').evalAtTime(t)
    # TASK 3 - static expressions arrive as expressions on every numeric parameter kind.
    for item in hou.selectedItems(): item.setSelected(False)
    expressive = src.createNode('xform', 'expressive')
    expressive.parm('tx').setExpression('$F*0.1', language=hou.exprLanguage.Hscript)
    expressive.parm('ty').setExpression('ch("tx") * 2', language=hou.exprLanguage.Hscript)
    expressive.parm('xOrd').setExpression('$F % 6', language=hou.exprLanguage.Hscript)        # menu
    expressive.parm('invertxform').setExpression('$F > 10', language=hou.exprLanguage.Hscript)  # toggle
    copies = src.createNode('copyxform', 'expressive_copy')
    copies.parm('ncy').setExpression('$F + 1', language=hou.exprLanguage.Hscript)                # integer
    expressive.setSelected(True); copies.setSelected(True)
    bridge.copy_rebuild()
    fresh = hou.node('/obj').createNode('geo', 'bridge_test_fresh')
    fresh.deleteItems(fresh.children())
    bridge._network = lambda kwargs: Pane(fresh)
    pasted = {n.type().name(): n for n in bridge.paste_rebuild()}
    bridge._network = lambda kwargs: Pane(target)
    for node, names in ((expressive, ('tx', 'ty', 'xOrd', 'invertxform')), (copies, ('ncy',))):
        twin = pasted[node.type().name()]
        for name in names:
            assert twin.parm(name).expression() == node.parm(name).expression(), name
            for frame in (1, 7, 24, 48):
                assert twin.parm(name).evalAtFrame(frame) == node.parm(name).evalAtFrame(frame), (name, frame)
    assert pasted['xform'].parm('tx').evalAtFrame(10) != pasted['xform'].parm('tx').evalAtFrame(20)
    print('PASS: static expressions round-trip on float, integer, menu and toggle parameters')
    # TASK 1 - payload review. Nothing below may create a node, cook, or leave a marker file.
    if os.path.exists(MARKER): os.remove(MARKER)
    shell = "touch '%s'" % MARKER
    pycode = "__import__('os').system(%r)" % shell
    callback = wrangle.parmTemplateGroup()
    callback.append(hou.FloatParmTemplate('evil', 'Evil', 1, script_callback=pycode,
                                          script_callback_language=hou.scriptLanguage.Python))
    menu = wrangle.parmTemplateGroup()
    menu.append(hou.MenuParmTemplate('evilmenu', 'Evil', (), item_generator_script=pycode,
                                     item_generator_script_language=hou.scriptLanguage.Python))
    default = wrangle.parmTemplateGroup()
    default.append(hou.FloatParmTemplate('evildefault', 'Evil', 1, default_expression=('system("%s")' % shell,),
                                         default_expression_language=(hou.scriptLanguage.Hscript,)))
    achn = ('ACHN 2\nstart = 0\nend = 0\n/obj/x/y {\n    channel tx {\n      lefttype = extend\n'
            '      righttype = extend\n      flags = 0\n      segment { options = {\t untie  iv ov is os ia oa }\n\n'
            '\t length = 0 expr = %s }\n    }\n  }\n')
    attacks = {
        'python sop': record('python', [{'name': 'python', 'locked': False, 'value': pycode}]),
        'python snippet sop': record('pythonsnippet', []),
        'python keyframe': record('xform', [{'name': 'tx', 'locked': False, 'keyframes': [crafted_key(pycode, 'Python')],
                                             'extrapolation': ['Hold', 'Hold']}]),
        'hscript system keyframe': record('xform', [{'name': 'tx', 'locked': False, 'extrapolation': ['Hold', 'Hold'],
                                                     'keyframes': [crafted_key('strlen(system("%s"))' % shell)]}]),
        'hscript pythonexprs keyframe': record('xform', [{'name': 'tx', 'locked': False, 'extrapolation': ['Hold', 'Hold'],
                                                          'keyframes': [crafted_key('pythonexprf("1")')]}]),
        'static python expression': record('xform', [{'name': 'tx', 'locked': False, 'expression': pycode, 'language': 'Python'}]),
        'backtick string': record('xform', [{'name': 'group', 'locked': False, 'value': '`system("%s")`' % shell}]),
        'achn python channel': record('xform', [{'name': 'tx', 'locked': False, 'extrapolation': ['Hold', 'Hold'],
                                                 'keyframes': [crafted_key('bezier()')],
                                                 'channel_text': achn % (pycode + ' language = python')}]),
        'achn system channel': record('xform', [{'name': 'tx', 'locked': False, 'extrapolation': ['Hold', 'Hold'],
                                                 'keyframes': [crafted_key('bezier()')],
                                                 'channel_text': achn % ('strlen(system("%s"))' % shell)}]),
        'spare callback': record('attribwrangle', [], templates=callback.asDialogScript()),
        'spare menu script': record('attribwrangle', [], templates=menu.asDialogScript()),
        'spare default expression': record('attribwrangle', [], templates=default.asDialogScript()),
    }
    for name, attack in attacks.items():
        for answer in (0, 1):  # even a user who clicks through cannot paste denied content
            before = set(target.allItems())
            ui.text, ui.shown, ui.answer = craft([record('box'), attack]), [], answer
            assert bridge.paste_rebuild() == (), name
            assert set(target.allItems()) == before, name
            assert len(ui.shown) == 1 and ui.shown[0][1] == ('Cancelar',), (name, ui.shown)
    # A built-in parameter redefined by the payload is replaced by the destination's own definition.
    redefined = wrangle.type().parmTemplateGroup()
    redefined.replace('class', hou.StringParmTemplate('class', 'Evil', 1, script_callback=pycode,
                                                      script_callback_language=hou.scriptLanguage.Python))
    redefined.append(hou.FloatParmTemplate('harmless', 'Harmless', 1))
    ui.text, ui.shown, ui.answer = craft([record('attribwrangle', [], templates=redefined.asDialogScript())]), [], 1
    safe = bridge.paste_rebuild()[0]
    assert safe.parm('harmless') is not None and safe.parmTemplateGroup().find('class').scriptCallback() == ''
    assert isinstance(safe.parmTemplateGroup().find('class'), hou.MenuParmTemplate)
    # Malformed records are rejected as a format error, never half-applied.
    for bad in ([42], [{'type': 'box'}], [record('box', ['x'])], [record('box', [{'name': 'sizex', 'locked': False, 'keyframes': 5}])]):
        before = set(target.allItems())
        ui.text, ui.shown, ui.answer = craft(bad), [], 1
        try: bridge.paste_rebuild()
        except ValueError: pass
        else: raise AssertionError('Malformed payload accepted: %r' % (bad,))
        assert set(target.allItems()) == before
    # Channel text may hold exactly one node block with one channel. Blocks the old
    # line-based check missed must never animate a node that already exists.
    victim = target.createNode('xform', 'victim')
    good = next(p for p in copied['nodes'][0]['parms'] if p['name'] == 'tx')
    tail = ('\n      lefttype = extend\n      righttype = extend\n      flags = 0\n'
            '      segment { length = 0 expr = 7 }\n    }\n  }\n')
    for name, extra in (('two spaces', victim.path() + '  {\n    channel  tx {' + tail),
                        ('tabs', victim.path() + '\t{\n    channel\ttx {' + tail),
                        ('brace on next line', victim.path() + '\n{\n    channel  tx\n{' + tail),
                        ('second channel', None)):
        text = good['channel_text'] + extra if extra else good['channel_text'].replace(
            '    channel tx {', '    channel  ty {' + tail[:-6] + '    channel tx {')
        before = set(target.allItems())
        ui.text, ui.shown, ui.answer = craft([record('xform', [dict(good, channel_text=text)])]), [], 1
        assert bridge.paste_rebuild() == () and set(target.allItems()) == before, name
        assert victim.parm('tx').keyframes() == (), name
    try: bridge._restore_channel(victim.parm('ty'), good['channel_text'])
    except ValueError: pass
    else: raise AssertionError('Channel text applied to a different parameter')
    print('PASS: channel text with extra node or channel blocks is refused; existing nodes keep their animation')
    # TASK 10 - enum and flag names from the payload are allowlisted, never passed to getattr.
    numeric = {'name': 'tx', 'locked': False, 'keyframes': [crafted_key('bezier()')], 'extrapolation': ['Hold', 'Hold']}
    bogus = {
        'exprLanguage': record('xform', [dict(numeric, keyframes=[crafted_key('bezier()', '__class__')])]),
        'parmExtrapolate': record('xform', [dict(numeric, extrapolation=['__class__', 'Hold'])]),
        'rampBasis': record('xform', [{'name': 'tx', 'locked': False, 'ramp': {'basis': ['__doc__'], 'keys': [0.0], 'values': [0.0]}}]),
        'flags': record('xform', flags={'__class__': True}),
    }
    bogus['flags value'] = record('xform', flags={'isBypassed': 'yes'})
    for kind, crafted in bogus.items():
        before = set(target.allItems())
        ui.text, ui.shown, ui.answer = craft([record('box'), crafted]), [], 1
        try: bridge.paste_rebuild()
        except ValueError as error: assert str(error) == 'Valor no valido para %s.' % kind.split()[0], (kind, error)
        else: raise AssertionError('Bogus %s accepted' % kind)
        assert set(target.allItems()) == before and ui.shown == [], kind
    print('PASS: bogus enum and flag names are rejected with a validation message and create nothing')
    # Standard SOPs with numeric keyframes paste without any dialog.
    ui.text, ui.shown, ui.answer = animation_text, [], None
    assert len(bridge.paste_rebuild()) == 1 and ui.shown == []
    # TASK 2 - licence warning matrix. The field is a hint written by the sender.
    real_license = hou.licenseCategory
    try:
        for target_license in ('Commercial', 'Indie'):
            hou.licenseCategory = lambda: getattr(hou.licenseCategoryType, target_license)
            for declared, warns in (('Apprentice', True), ('ApprenticeHD', True), ('Education', True),
                                    ('Unknown', True), ('', True), (None, True), ('commercial', True),
                                    (['Commercial'], True), ('Commercial', False), ('Indie', False)):
                payload = craft([record('box')], license_name=declared, drop_license=declared is None)
                before = set(target.allItems())
                ui.text, ui.shown, ui.answer = payload, [], 0
                pasted = bridge.paste_rebuild()
                assert (len(ui.shown) == 1) == warns, (target_license, declared, ui.shown)
                if warns:
                    assert pasted == () and set(target.allItems()) == before, declared
                    assert 'verificar la procedencia' in ui.shown[0][0]
                    ui.shown, ui.answer = [], 1
                    assert len(bridge.paste_rebuild()) == 1 and len(ui.shown) == 1, declared
                else:
                    assert len(pasted) == 1, declared
    finally:
        hou.licenseCategory = real_license
    print('PASS: licence warning shown for Apprentice, ApprenticeHD, Education, unknown, malformed and missing values')
    hou.setFrame(3)
    for node in target.children():
        try: node.cook(force=True)
        except hou.OperationFailed: pass  # nodes without input; expressions are still evaluated
    assert not os.path.exists(MARKER), 'A payload executed code'
    print('PASS: payload review blocks %d code-execution payloads; benign pastes need no dialog' % len(attacks))
    print('PASS: reconstruction plus numeric/string animation, interpolation, split/automatic tangents, subframes, extrapolation and differing FPS (1080+ evaluated curve samples)')
finally:
    hou.ui = original_ui
