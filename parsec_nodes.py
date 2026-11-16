"""Houdini node transport over a plain-text clipboard. No executable text payloads."""
import base64
import hashlib
import json
import os
import tempfile
import zlib

__version__ = "2.1"

PREFIX = 'HOUDINI_PARSEC_NODES_V1:'
MAX_RAW = 32 * 1024 * 1024
MAX_TEXT = 48 * 1024 * 1024


def encode(raw, category, version, license_name="Unknown"):
    if len(raw) > MAX_RAW:
        raise ValueError('La seleccion supera 32 MB. Prueba con menos nodos.')
    envelope = {'category': category, 'version': version,
                'license': license_name, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'data': base64.b64encode(zlib.compress(raw, 9)).decode('ascii')}
    return PREFIX + json.dumps(envelope, separators=(',', ':'))


def decode(text):
    text = text.strip()
    if not text.startswith(PREFIX):
        raise ValueError('El portapapeles no contiene nodos de Parsec Nodes. Copia con Copy Nodes en el otro equipo y espera un segundo.')
    if len(text) > MAX_TEXT:
        raise ValueError('El contenido del portapapeles es demasiado grande.')
    try:
        envelope = json.loads(text[len(PREFIX):])
        size = envelope['size']
        if type(size) is not int or not 0 <= size <= MAX_RAW:
            raise ValueError('Tamano no valido.')
        compressed = base64.b64decode(envelope['data'], validate=True)
        stream = zlib.decompressobj()
        raw = stream.decompress(compressed, size + 1)
        if (len(raw) != size or not stream.eof or stream.unused_data
                or hashlib.sha256(raw).hexdigest() != envelope['sha256']):
            raise ValueError('Checksum o longitud incorrectos.')
        if not isinstance(envelope['category'], str):
            raise ValueError('Categoria no valida.')
        return raw, envelope
    except (KeyError, TypeError, ValueError, zlib.error) as exc:
        raise ValueError('Los nodos llegaron incompletos o el formato no es valido. Vuelve a copiar y espera a que Parsec sincronice.') from exc


LICENSES = ('Commercial', 'Indie', 'Education', 'ApprenticeHD', 'Apprentice')
NONCOMMERCIAL = ('Education', 'ApprenticeHD', 'Apprentice')


def _license_gate(envelope):
    """The licence field is written by the sender: a hint, never an authorisation."""
    import hou
    source = envelope.get('license')
    if hou.licenseCategory().name() == 'Apprentice':
        return True
    if isinstance(source, str) and source in LICENSES and source not in NONCOMMERCIAL:
        return True
    declared = source if isinstance(source, str) and source in LICENSES else 'desconocida'
    choice = hou.ui.displayMessage(
        'Licencia de origen declarada: %s. El portapapeles no permite verificar la procedencia.\n\n'
        'El contenido creado en Houdini Apprentice o Education sigue sujeto al EULA de SideFX: '
        'esta herramienta no convierte derechos de licencia.\n\n'
        'Continua solo si conoces el origen de estos nodos.' % declared,
        buttons=('Cancelar', 'Continuar'), default_choice=0, close_choice=0,
        severity=hou.severityType.Warning)
    return choice == 1


def _network(kwargs):
    import hou
    pane = (kwargs or {}).get('pane')
    if isinstance(pane, hou.NetworkEditor):
        return pane
    pane = hou.ui.paneTabUnderCursor()
    if isinstance(pane, hou.NetworkEditor):
        return pane
    panes = [p for p in hou.ui.curDesktop().paneTabs()
             if isinstance(p, hou.NetworkEditor) and p.isCurrentTab()]
    if len(panes) == 1:
        return panes[0]
    raise ValueError('Pon el raton sobre la red de destino y ejecuta la herramienta con su atajo. Hay varias redes abiertas.')


# Reconstruction mode: only node descriptions, never native Houdini archives.
REBUILD_PREFIX = 'HOUDINI_PARSEC_REBUILD_V1:'


def _standard_type(node_type):
    import hou
    definition = node_type.definition()
    if definition is None:
        return True
    library = os.path.realpath(definition.libraryFilePath())
    installation = os.path.realpath(hou.getenv('HFS'))
    try:
        return os.path.commonpath([library, installation]) == installation
    except ValueError:
        return False


def _hscript_path(path):
    # Temporary Windows paths are converted to forward slashes for HScript.
    return '"' + str(path).replace('\\', '/').replace('"', '\\"').replace('$', '\\$') + '"'


def _describe_channel(parm):
    """ACHN stores exact channel segments, including automatic tangent defaults."""
    import hou
    with tempfile.TemporaryDirectory(prefix='houdini_parsec_channels_') as folder:
        path = os.path.join(folder, 'curve.chn')
        output, error = hou.hscript('chwrite %s %s' % (_hscript_path(parm.path()), _hscript_path(path)))
        if error.strip() or not os.path.exists(path):
            raise ValueError('No se pudo exportar la animacion de %s: %s' % (parm.path(), error))
        with open(path, encoding='utf-8') as handle:
            return handle.read()


def _restore_channel(parm, text):
    import hou
    import re
    # Accept exactly one channel and one node; rewrite the only destination.
    # This prevents an archive from writing animation onto pre-existing nodes.
    headers = list(re.finditer(r'^(/[^\s{}]+) \{$', text, re.MULTILINE))
    channels = re.findall(r'^\s*channel ([^\s{}]+) \{$', text, re.MULTILINE)
    if not text.startswith('ACHN ') or len(headers) != 1 or channels != [parm.name()]:
        raise ValueError('Formato de canal no valido para %s.' % parm.name())
    match = headers[0]
    text = text[:match.start(1)] + parm.node().path() + text[match.end(1):]
    with tempfile.TemporaryDirectory(prefix='houdini_parsec_channels_') as folder:
        path = os.path.join(folder, 'curve.chn')
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
        output, error = hou.hscript('chread -n %s' % _hscript_path(path))
        if error.strip():
            raise ValueError('No se pudo restaurar la animacion de %s: %s' % (parm.path(), error))


def _describe_key(key):
    """Store the key's data, including unset/tied and automatic tangent states."""
    import hou
    record = {'kind': 'string' if isinstance(key, hou.StringKeyframe) else 'numeric',
              'time': key.time()}
    if key.isExpressionSet():
        record['expression'] = key.expression()
        if key.isExpressionLanguageSet():
            record['language'] = key.expressionLanguage().name()
    if record['kind'] == 'numeric':
        for field in ('value', 'slope', 'accel'):
            title = field[0].upper() + field[1:]
            record['is' + title + 'Set'] = getattr(key, 'is' + title + 'Set')()
            if not record['is' + title + 'Set']:
                continue
            for getter in (field, 'in' + title):
                try:
                    record[getter] = getattr(key, getter)()
                except hou.KeyframeValueNotSet:
                    pass
        for field in ('isValueTied', 'isSlopeTied', 'isAccelTied',
                      'isValueUsed', 'isSlopeUsed', 'isAccelUsed',
                      'isSlopeAuto', 'isInSlopeAuto', 'isAccelInterpretedAsRatio'):
            record[field] = getattr(key, field)()
    return record


def _restore_key(record):
    import hou
    if record['kind'] not in ('numeric', 'string'):
        raise ValueError('Tipo de clave no compatible.')
    key = hou.StringKeyframe() if record['kind'] == 'string' else hou.Keyframe()
    key.setTime(record['time'])
    if record['kind'] == 'numeric':
        for field in ('value', 'inValue', 'slope', 'inSlope', 'accel', 'inAccel'):
            if field in record:
                getattr(key, 'set' + field[0].upper() + field[1:])(record[field])
        if not record['isAccelInterpretedAsRatio']:
            key.interpretAccelAsRatio(False)
        if record['isSlopeAuto']:
            key.setSlopeAuto(True)
        if record['isInSlopeAuto']:
            key.setInSlopeAuto(True)
    if 'expression' in record:
        if _unsafe_expression(record['expression'], record.get('language', 'Hscript')):
            raise ValueError('Expresion Python o de sistema no permitida.')
        language = _enum('exprLanguage', record['language']) if 'language' in record else None
        key.setExpression(record['expression'], language=language)
    if record['kind'] == 'numeric':
        for field in ('Value', 'Slope', 'Accel'):
            if not record['is' + field + 'Used']:
                getattr(key, 'use' + field)(False)
    return key


def _describe_parm(parm):
    import hou
    kind = parm.parmTemplate().type()
    if kind in (hou.parmTemplateType.Button, hou.parmTemplateType.Label,
                hou.parmTemplateType.Separator):
        return None
    record = {'name': parm.name(), 'locked': parm.isLocked()}
    keys = parm.keyframes()
    if keys:
        record['keyframes'] = [_describe_key(key) for key in keys]
        # chwrite only exports float and integer channels; menus and toggles travel as keys.
        if (kind in (hou.parmTemplateType.Float, hou.parmTemplateType.Int)
                and all(isinstance(key, hou.Keyframe) for key in keys)):
            record['channel_text'] = _describe_channel(parm)
        record['extrapolation'] = [parm.keyframeExtrapolation(before).name()
                                   for before in (True, False)]
        return record
    if kind == hou.parmTemplateType.Ramp:
        ramp = parm.evalAsRamp()
        record['ramp'] = {'basis': [b.name() for b in ramp.basis()],
                          'keys': ramp.keys(), 'values': ramp.values()}
    elif kind == hou.parmTemplateType.String:
        record['value'] = parm.unexpandedString()
    elif kind in (hou.parmTemplateType.Int, hou.parmTemplateType.Float,
                  hou.parmTemplateType.Toggle, hou.parmTemplateType.Menu,
                  hou.parmTemplateType.Folder):
        record['value'] = parm.eval()
    elif parm.isAtDefault():
        return None
    else:
        raise ValueError('%s contiene datos especiales incrustados que no admite la reconstruccion.' % parm.path())
    return record


def copy_rebuild(kwargs=None):
    import hou
    nodes = tuple(hou.selectedNodes())
    if not nodes:
        raise ValueError('Selecciona una cadena de nodos estandar.')
    parent = nodes[0].parent()
    if any(n.parent() != parent for n in nodes):
        raise ValueError('Selecciona nodos de una sola red.')
    index = {n: i for i, n in enumerate(nodes)}
    records = []
    for node in nodes:
        if not _standard_type(node.type()):
            raise ValueError('%s es un HDA externo. Este modo admite nodos incluidos con Houdini; no convierte HDAs de licencia.' % node.name())
        if (node.children() and (node.type().definition() is None or not node.matchesCurrentDefinition())) or (hasattr(node, 'isHardLocked') and node.isHardLocked()):
            raise ValueError('%s contiene una subred o geometria bloqueada. Entra en la subred y selecciona su cadena; los datos incrustados no se transportan.' % node.name())
        record = {'name': node.name(), 'type': node.type().name(),
                  'position': list(node.position()), 'color': list(node.color().rgb()),
                  'comment': node.comment(), 'parms': [], 'flags': {}}
        if node.spareParms():
            record['templates'] = node.parmTemplateGroup().asDialogScript()
        for parm in node.parms():
            data = _describe_parm(parm)
            if data is not None:
                record['parms'].append(data)
        for getter in ('isBypassed', 'isDisplayFlagSet', 'isRenderFlagSet', 'isTemplateFlagSet'):
            if hasattr(node, getter):
                record['flags'][getter] = getattr(node, getter)()
        record['inputs'] = [[c.inputIndex(), index[c.inputNode()], c.outputIndex()]
                            for c in node.inputConnections() if c.inputNode() in index]
        records.append(record)
    raw = json.dumps({'format': 'rebuild-json-v1', 'fps': hou.fps(), 'nodes': records}, ensure_ascii=False).encode('utf-8')
    text = encode(raw, parent.childTypeCategory().name(), hou.applicationVersionString(), hou.licenseCategory().name())
    text = REBUILD_PREFIX + text[len(PREFIX):]
    hou.ui.copyTextToClipboard(text)
    hou.ui.setStatusMessage('Parsec Nodes v%s: %d nodos copiados en modo reconstruccion (%d caracteres).' % (__version__, len(nodes), len(text)))
    return text


# Payload review: pasted text is untrusted. Code-bearing content is refused or confirmed.
DENIED_TYPES = ('python', 'pythonsnippet', 'pythonscript', 'shell', 'genericgenerator', 'sendcommand')
UNSAFE_CALL = r'\b(system|execute|run|pythonexpr[fsu]?)\s*\('
CODE_PARM = r'(script|command|callback|snippet|kernel|code$|(pre|post)(render|frame|write))'


# Names from the payload are only ever looked up through these allowlists.
ENUMS = {'exprLanguage': ('Hscript', 'Python'),
         'parmExtrapolate': ('Default', 'Hold', 'Cycle', 'Extend', 'Slope', 'CycleOffset', 'Oscillate'),
         'rampBasis': ('Linear', 'Constant', 'CatmullRom', 'MonotoneCubic', 'Bezier', 'BSpline', 'Hermite')}
FLAG_SETTERS = {'isBypassed': 'bypass', 'isDisplayFlagSet': 'setDisplayFlag',
                'isRenderFlagSet': 'setRenderFlag', 'isTemplateFlagSet': 'setTemplateFlag'}


def _enum(kind, name):
    import hou
    if not isinstance(name, str) or name not in ENUMS[kind]:
        raise ValueError('Valor no valido para %s.' % kind)
    return getattr(getattr(hou, kind), name)


def _templates(entries):
    import hou
    for template in entries:
        yield template
        if isinstance(template, hou.FolderParmTemplate):
            for child in _templates(template.parmTemplates()):
                yield child


def _unsafe_expression(text, language='Hscript'):
    """Only HScript expressions that cannot start a process or run Python are accepted."""
    import re
    return language != 'Hscript' or not isinstance(text, str) or re.search(UNSAFE_CALL, text) is not None


def _unsafe_string(text):
    import re
    return isinstance(text, str) and '`' in text and re.search(UNSAFE_CALL, text) is not None


def _review_templates(node_type, text, label, denied):
    """Spare parameters only: built-in templates always come from the destination type."""
    import hou
    if not isinstance(text, str):
        raise TypeError('templates')
    original = node_type.parmTemplateGroup()
    group = hou.ParmTemplateGroup()
    group.setToDialogScript(text)
    for template in tuple(_templates(group.entries())):
        known = original.find(template.name())
        folder = isinstance(template, hou.FolderParmTemplate)
        if known is not None and not folder:
            group.replace(template.name(), known)
            continue
        allowed = known.tags() if known is not None else {}
        unsafe = template.scriptCallback() != (known.scriptCallback() if known is not None else '')
        unsafe = unsafe or any(key.startswith('script_') and allowed.get(key) != value
                               for key, value in template.tags().items())
        if hasattr(template, 'itemGeneratorScript') and template.itemGeneratorScript():
            unsafe = True
        if hasattr(template, 'defaultExpression'):
            expressions, languages = template.defaultExpression(), template.defaultExpressionLanguage()
            if isinstance(expressions, str):
                expressions, languages = (expressions,), (languages,)
            for expression, language in zip(expressions, languages):
                if expression and _unsafe_expression(expression, language.name()):
                    unsafe = True
        if isinstance(template, hou.StringParmTemplate) and any(_unsafe_string(v) for v in template.defaultValue()):
            unsafe = True
        if unsafe:
            denied.append('%s: parametro personalizado %s con script' % (label, template.name()))
    return group


def _review(records, category):
    """Validate every record before the scene is touched. Returns (denied, flagged, groups)."""
    import re
    denied, flagged, groups = [], [], {}
    for number, record in enumerate(records):
        node_type = category.nodeTypes().get(record['type'])
        if node_type is None or not _standard_type(node_type):
            raise ValueError('El tipo %s no existe o depende de un HDA externo en este equipo.' % record['type'])
        label = '%s (%s)' % (record['name'], record['type'])
        original = node_type.parmTemplateGroup()
        if (node_type.nameComponents()[2] in DENIED_TYPES or
                any(t.tags().get('editorlang', '').lower() == 'python' for t in _templates(original.entries()))):
            denied.append(label + ': tipo de nodo que ejecuta codigo')
            continue
        spare = None
        if record.get('templates'):
            spare = groups[number] = _review_templates(node_type, record['templates'], label, denied)
            flagged.append(label + ': parametros personalizados')
        for getter, value in record['flags'].items():
            if getter not in FLAG_SETTERS or type(value) is not bool:
                raise ValueError('Valor no valido para flags.')
        for p in record['parms']:
            where = '%s.%s' % (label, p['name'])
            for key in p.get('keyframes', ()):
                if 'language' in key:
                    _enum('exprLanguage', key['language'])
            for name in p.get('extrapolation', ()):
                _enum('parmExtrapolate', name)
            for name in p['ramp']['basis'] if 'ramp' in p else ():
                _enum('rampBasis', name)
            if 'expression' in p:
                _enum('exprLanguage', p.get('language'))
            unsafe = any('expression' in key and _unsafe_expression(key['expression'], key.get('language', 'Hscript'))
                         for key in p.get('keyframes', ()))
            if 'expression' in p and _unsafe_expression(p['expression'], p.get('language')):
                unsafe = True
            channel = p.get('channel_text')
            if channel is not None and (not isinstance(channel, str) or re.search(UNSAFE_CALL, channel) or
                                        re.search(r'language\s*=\s*(?!\s|hscript\b)', channel, re.IGNORECASE)):
                unsafe = True
            value = p.get('value')
            if _unsafe_string(value):
                unsafe = True
            if unsafe:
                denied.append(where + ': expresion Python o de sistema')
            elif isinstance(value, str) and value:
                template = original.find(p['name'])
                if template is None and spare is not None:
                    template = spare.find(p['name'])
                tags = template.tags() if template is not None else {}
                if 'editor' in tags or 'editorlang' in tags or re.search(CODE_PARM, p['name']):
                    flagged.append(where + ': codigo')
    return denied, flagged, groups


def _confirm_review(denied, flagged):
    """One dialog before anything is created. Cancel is the default."""
    import hou
    if denied:
        hou.ui.displayMessage(
            'Pegado bloqueado: %d elementos ejecutan codigo y no se admiten.\n\n%s\n\nNo se ha creado nada.'
            % (len(denied), '\n'.join(denied[:20])),
            buttons=('Cancelar',), severity=hou.severityType.Warning)
        return False
    if not flagged:
        return True
    choice = hou.ui.displayMessage(
        'El portapapeles trae %d elementos con codigo o parametros personalizados.\n'
        'Pega solo si conoces su origen.\n\n%s' % (len(flagged), '\n'.join(flagged[:20])),
        buttons=('Cancelar', 'Pegar'), default_choice=0, close_choice=0,
        severity=hou.severityType.Warning)
    return choice == 1


def paste_rebuild(kwargs=None):
    import hou
    text = hou.ui.getTextFromClipboard().strip()
    if not text.startswith(REBUILD_PREFIX):
        raise ValueError('Copia de nuevo con Copy Nodes de la version de reconstruccion. Este boton no importa archivos nativos ni el portapapeles anterior.')
    raw, envelope = decode(PREFIX + text[len(REBUILD_PREFIX):])
    data = json.loads(raw.decode('utf-8'))
    if data.get('format') != 'rebuild-json-v1' or not isinstance(data.get('nodes'), list):
        raise ValueError('Formato de reconstruccion no valido.')
    records = data['nodes']
    pane = _network(kwargs)
    parent = pane.pwd()
    category = parent.childTypeCategory()
    if category is None or category.name() != envelope['category']:
        raise ValueError('Abre una red de tipo %s.' % envelope['category'])
    if not _license_gate(envelope):
        return ()
    try:
        denied, flagged, groups = _review(records, category)
    except (AttributeError, KeyError, TypeError) as exc:
        raise ValueError('Formato de reconstruccion no valido.') from exc
    if not _confirm_review(denied, flagged):
        return ()
    created = []
    with hou.undos.group('Rebuild Parsec Nodes'):
        try:
            for number, record in enumerate(records):
                node = parent.createNode(record['type'], node_name=record['name'],
                                         run_init_scripts=False, load_contents=True,
                                         exact_type_name=True)
                created.append(node)
                if number in groups:
                    node.setParmTemplateGroup(groups[number])
                # Multiparm counts are applied before the generated parameters.
                for p in record['parms']:
                    parm = node.parm(p['name'])
                    if parm is not None and parm.isMultiParmParent():
                        parm.set(p.get('value', 0))
                for p in record['parms']:
                    parm = node.parm(p['name'])
                    if parm is None:
                        raise ValueError('Falta el parametro %s en %s. Comprueba las versiones.' % (p['name'], node.name()))
                    parm.lock(False)
                    parm.deleteAllKeyframes()
                    if 'channel_text' in p:
                        _restore_channel(parm, p['channel_text'])
                    elif 'keyframes' in p:
                        parm.setKeyframes([_restore_key(key) for key in p['keyframes']])
                        for before, extrapolation in zip((True, False), p['extrapolation']):
                            parm.setKeyframeExtrapolation(before, _enum('parmExtrapolate', extrapolation))
                    elif 'expression' in p:
                        if _unsafe_expression(p['expression'], p.get('language')):
                            raise ValueError('Expresion Python o de sistema no permitida.')
                        parm.setExpression(p['expression'], language=_enum('exprLanguage', p.get('language')))
                    elif 'ramp' in p:
                        ramp = p['ramp']
                        parm.set(hou.Ramp([_enum('rampBasis', b) for b in ramp['basis']], ramp['keys'], ramp['values']))
                    else:
                        parm.set(p['value'], follow_parm_reference=False)
                    parm.lock(p['locked'])
                node.setPosition(record['position'])
                node.setColor(hou.Color(record['color']))
                node.setComment(record['comment'])
            # Resolve wires only after all nodes exist (handles name collisions).
            for node, record in zip(created, records):
                for input_index, source_index, output_index in record['inputs']:
                    node.setInput(input_index, created[source_index], output_index)
            for node, record in zip(created, records):
                for getter, value in record['flags'].items():
                    if getter not in FLAG_SETTERS or type(value) is not bool:
                        raise ValueError('Valor no valido para flags.')
                    getattr(node, FLAG_SETTERS[getter])(value)
            if created:
                center = sum((n.position() for n in created), hou.Vector2(0, 0)) / len(created)
                offset = pane.visibleBounds().center() - center
                for node in created:
                    node.move(offset)
                for selected in parent.selectedItems():
                    selected.setSelected(False)
                for node in created:
                    node.setSelected(True)
        except Exception:
            if created:
                parent.deleteItems(tuple(created))
            raise
    message = 'Parsec Nodes v%s: reconstruidos %d nodos con parametros, claves y conexiones.' % (__version__, len(created))
    if data.get('fps', hou.fps()) != hou.fps():
        message += ' FPS distintos: se conservan los tiempos en segundos; no se cambia el FPS del destino.'
    hou.ui.setStatusMessage(message)
    return tuple(created)


# Shelf entry point. Only the reconstruction mode ships.
def run(action, kwargs=None):
    import hou
    try:
        return {'copy': copy_rebuild, 'paste': paste_rebuild}[action](kwargs)
    except Exception as exc:
        hou.ui.displayMessage('Parsec Nodes v%s - Reconstruccion\n\n' % __version__ + str(exc), severity=hou.severityType.Error)
