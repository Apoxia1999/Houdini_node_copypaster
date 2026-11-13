"""Houdini node transport over a plain-text clipboard. No executable text payloads."""
import base64
import hashlib
import json
import os
import tempfile
import zlib

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
            text = encode(handle.read(), parent.childTypeCategory().name(), hou.applicationVersionString(), hou.licenseCategory().name())
    hou.ui.copyTextToClipboard(text)
    hou.ui.setStatusMessage('Parsec Nodes: copiados %d elementos (%d caracteres). Abre Parsec y pulsa Paste Nodes.' % (len(items), len(text)))
    return text


def paste_nodes(kwargs=None):
    import hou
    raw, envelope = decode(hou.ui.getTextFromClipboard())
    pane = _network(kwargs)
    parent = pane.pwd()
    category = parent.childTypeCategory()
    if category is None or category.name() != envelope['category']:
        raise ValueError('Abre una red de tipo %s para pegar estos nodos.' % envelope['category'])
    source_license = envelope.get('license', 'Unknown')
    target_license = hou.licenseCategory().name()
    if source_license == 'Apprentice' and target_license != 'Apprentice':
        choice = hou.ui.displayMessage(
            'Estos nodos proceden de Houdini Apprentice. Importarlos puede convertir '
            'esta sesion a no comercial. El puente conserva las restricciones de licencia.\n\n'
            'Prueba solo en una sesion vacia, sin escenas de trabajo abiertas.',
            buttons=('Cancelar', 'Continuar prueba'), default_choice=0, close_choice=0,
            severity=hou.severityType.Warning)
        if choice != 1:
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


def run(action, kwargs=None):
    import hou
    try:
        return {'copy': copy_nodes, 'paste': paste_nodes}[action](kwargs)
    except Exception as exc:
        hou.ui.displayMessage('Parsec Nodes\n\n' + str(exc), severity=hou.severityType.Error)

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
        language = getattr(hou.exprLanguage, record['language']) if 'language' in record else None
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
        if all(isinstance(key, hou.Keyframe) for key in keys):
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
    hou.ui.setStatusMessage('Parsec Nodes: %d nodos copiados en modo reconstruccion (%d caracteres).' % (len(nodes), len(text)))
    return text


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
    for record in records:
        node_type = category.nodeTypes().get(record['type'])
        if node_type is None or not _standard_type(node_type):
            raise ValueError('El tipo %s no existe o depende de un HDA externo en este equipo.' % record['type'])
    created = []
    with hou.undos.group('Rebuild Parsec Nodes'):
        try:
            for record in records:
                node = parent.createNode(record['type'], node_name=record['name'],
                                         run_init_scripts=False, load_contents=True,
                                         exact_type_name=True)
                created.append(node)
                if record.get('templates'):
                    group = hou.ParmTemplateGroup()
                    group.setToDialogScript(record['templates'])
                    node.setParmTemplateGroup(group)
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
                            parm.setKeyframeExtrapolation(before, getattr(hou.parmExtrapolate, extrapolation))
                    elif 'expression' in p:
                        parm.setExpression(p['expression'], language=getattr(hou.exprLanguage, p['language']))
                    elif 'ramp' in p:
                        ramp = p['ramp']
                        parm.set(hou.Ramp([getattr(hou.rampBasis, b) for b in ramp['basis']], ramp['keys'], ramp['values']))
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
            setters = {'isBypassed': 'bypass', 'isDisplayFlagSet': 'setDisplayFlag',
                       'isRenderFlagSet': 'setRenderFlag', 'isTemplateFlagSet': 'setTemplateFlag'}
            for node, record in zip(created, records):
                for getter, value in record['flags'].items():
                    getattr(node, setters[getter])(value)
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
    message = 'Parsec Nodes: reconstruidos %d nodos con parametros, claves y conexiones.' % len(created)
    if data.get('fps', hou.fps()) != hou.fps():
        message += ' FPS distintos: se conservan los tiempos en segundos; no se cambia el FPS del destino.'
    hou.ui.setStatusMessage(message)
    return tuple(created)


# Main buttons now reconstruct node descriptions. Native functions remain for regression tests.
def run(action, kwargs=None):
    import hou
    try:
        return {'copy': copy_rebuild, 'paste': paste_rebuild}[action](kwargs)
    except Exception as exc:
        hou.ui.displayMessage('Parsec Nodes - Reconstruccion\n\n' + str(exc), severity=hou.severityType.Error)
