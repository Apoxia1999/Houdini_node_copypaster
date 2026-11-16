# Houdini_node_copypaster

**Version 2.1 · Shelf: Parsec Nodes v2.1** · history in [CHANGELOG.md](CHANGELOG.md)

The published version and its hashes travel together: `__version__` in `parsec_nodes.py`
and in the installer, and `SHA256SUMS` for that same version.

Licence: MIT, see [LICENSE](LICENSE). It includes a notice about Houdini licensing:
the tool does not convert SideFX licence rights.

The two buttons transport a JSON description of nodes, parameters and connections.
The destination creates the nodes through the Houdini API: it does not import native
networks, HDAs or CPIO blocks from the source. Numeric curves use ACHN text segments
(animation only), remapped exclusively onto the new nodes. The compressed text travels over the Parsec clipboard.
This technique does not convert licence rights of content created in Apprentice.

Tested on Linux with Houdini Apprentice 22.0.466. Checks: connections, parameters,
name collisions, Attribute Wrangle and VEX, spare parameters, expressions and
ramps, numeric and string keys, split and automatic tangents, subframes,
interpolation and cyclic extrapolation. Curves are compared at more than a thousand samples
and also between scenes with different FPS. Also tested by loading and running the real shelf scripts with the
Qt clipboard. The licence check of a commercial FX session on Windows
is still pending the user's own test; no FX licence is available here.

## Instalar o actualizar en Linux
*(Install or update on Linux)*

Download the repository or the ZIP and extract it. In Houdini's Windows > Python Shell,
run this line, replacing the path with the installer's location:

```python
exec(open('/path/Houdini_node_copypaster/install_parsec_nodes.py', encoding='utf-8').read())
```

## Instalar o actualizar en Windows
*(Install or update on Windows)*

Primary path: copy the ZIP to the Windows machine, extract it and check its hash (see
Integridad). Then, in Houdini's Windows > Python Shell, using the real path:

```python
exec(open(r'C:\path\install_parsec_nodes.py', encoding='utf-8').read())
```

The installer writes `toolbar/parsec_nodes.shelf` under `$HOUDINI_USER_PREF_DIR`.
It needs no administrator rights and no Houdini restart. If the active shelf set is
protected, installation still completes and explains how to show the tab by hand:
+ menu at the right of the shelves > Shelves > Parsec Nodes.

### Alternativa: una linea por el portapapeles de Parsec
*(Fallback: one line over the Parsec clipboard)*

Only if you cannot copy files to the remote machine. `INSTALAR_EN_WINDOWS.txt` holds the
same installer compressed into one line; it is not readable as is, so
decode and review it before pasting. From the extracted folder:

```sh
python -c "import base64,zlib,re;print(zlib.decompress(base64.b64decode(re.search(r\"b64decode\('([^']+)'\",open('INSTALAR_EN_WINDOWS.txt').read()).group(1))).decode())"
```

The output must match `install_parsec_nodes.py` (plus one trailing blank line). Then:

1. On Linux, open `INSTALAR_EN_WINDOWS.txt` in a text editor and copy the single full line.
2. On the remote Windows machine, open Houdini's Windows > Python Shell.
3. Paste the line and press Enter.

## Integridad
*(Integrity)*

`SHA256SUMS` lists the SHA-256 hash of the ZIP and of every file inside it. It is published
next to the download and in the repository. To check it:

```sh
sha256sum -c SHA256SUMS                                  # Linux
Get-FileHash Houdini_node_copypaster-v2.1.zip -Algorithm SHA256   # Windows PowerShell
```

The ZIP is built with fixed timestamps: the same sources always give the same hash.
The hashes detect an altered or incomplete download; they are not signed, so
compare them with the ones in the repository, not only with the downloads page.

## Prueba entre equipos
*(Test between machines)*

1. Update both machines and check that Parsec Nodes v2.1 appears.
2. Select Box > Transform, or a chain of standard nodes in a single network.
3. Press Copy Nodes. The status line reports reconstruction mode.
4. In Parsec, wait a second and enter an empty network of the same type (SOP into SOP).
5. Press Paste Nodes. Check the nodes and the licence edition Houdini shows.
6. Try it first in a new FX session, with no work scenes open.

The v2 format has a different prefix from the old one. Copy again after updating.
If the remote transfer fails, check that plain text reaches Notepad.

## Alcance actual
*(Current scope)*

- Chains of standard nodes shipped with Houdini, without edited subnetworks inside.
- Static parameters, HScript expressions (also on menus, toggles and integers), VEX, ramps,
  spare parameters and internal connections.
- Python expressions and HScript calls that run processes or Python
  (`system`, `execute`, `run`, `pythonexpr*`) are not transported: a paste containing them is refused whole.
- Animation: numeric and string keys, interpolation, tangents and accelerations,
  automatic slopes, split in/out values and extrapolation.
- Times are kept in seconds. If the destination FPS differs, the matching frame numbers
  change, but the scene's global FPS is not modified.
- Standard HDAs shipped with the installation are created from the destination's definition.
- External HDAs and nodes with locked geometry are refused.
- Sticky notes and network boxes are not copied in reconstruction mode: select the nodes you want.
- Textures, caches and external files are not transported. References to other nodes
  are kept as text and may need adjusting, especially with repeated names.
- Copying descriptions does not remove the restrictions of non-commercial files or HDAs
  loaded later through those references.
- Types and parameters must exist at the destination. A failed reconstruction rolls back
  the new nodes and keeps pre-existing ones.
- Internal transport limit: 32 MiB of uncompressed description. Parsec's real limit is not measured.

## Seguridad
*(Security)*

Clipboard text is treated as untrusted. Before creating any node,
Paste Nodes reviews the whole description.

- The whole paste is refused if it contains nodes that run code (Python SOP and
  any type with a Python editor parameter, shell command nodes),
  Python expressions, HScript calls to `system`, `execute`, `run` or `pythonexpr*`
  (in keys, channels, backtick strings or default values), or
  spare parameters with callbacks, scripted menus or `script_*` tags.
- Each node's own parameters always come from the destination machine's
  definition; only spare parameters are accepted from the clipboard.
- If there is VEX, OpenCL, script parameters or spare parameters, a single
  warning lists them before anything is created. The default button is Cancel.
- Licence warning: the source licence is declared by whoever copies and cannot be verified.
  If it is Apprentice, ApprenticeHD, Education, unknown or missing, the warning always shows. There is
  no option to turn the warning off.

Known limits:

- There is no signature: the tool cannot know who produced the clipboard text.
- VEX is not analysed, only announced. Review code you did not write yourself.
- The content travels unencrypted and may remain in clipboard histories.
- Use of Parsec's shared clipboard depends on each company's policy.

## Atajos
*(Shortcuts)*

Ctrl+Alt+Shift and click on Copy Nodes opens the hotkey editor. You can assign Ctrl+Shift+C.
Do the same for Paste Nodes with Ctrl+Shift+V; review any conflicts Houdini reports.
Shortcuts are not assigned automatically.

## Desinstalar
*(Uninstall)*

In the same Python Shell where you ran the installer, type `uninstall()`: it asks for
confirmation and deletes `toolbar/parsec_nodes.shelf`. Then remove the shelf tab.
The `parsec_nodes.shelf.<date>.bak` backups are left alone.

By hand: remove the shelf tab and, with Houdini closed, delete
`toolbar/parsec_nodes.shelf` from the user preferences folder.

## Actualizacion v2.1
*(Update v2.1)*

Update both machines before copying animation. The initial v2 could not read
the new key fields. Run the installer again in each Houdini and copy again.

Numeric curves are stored with their exact channel segments, instead of
rebuilding only the public key fields. This also keeps
the implicit accelerations of automatic Bezier tangents. String keys
are transported through their times, expressions and languages.

## Desarrollo y verificacion
*(Development and verification)*

`parsec_nodes.py` holds the tool. `build.py` generates the shelf, the standalone
installer, the one-line clipboard installer, the distributable ZIP and `SHA256SUMS`,
and ends by checking that every artifact carries exactly the source (it exits with an error otherwise).
These scripts are included in the ZIP.

```sh
python build.py
/path/to/houdini/bin/hython test_rebuild.py
/path/to/houdini/bin/hython test_bridge.py
HOUDINI_USER_PREF_DIR=/tmp/parsec_prefs/houdini__HVER__ /path/to/houdini/bin/hython test_install.py
```

`test_rebuild.py` also covers the paste security review (code-bearing nodes and
expressions, spare parameters with scripts), the licence warning and expressions.
`test_install.py` checks the installer and only runs against a temporary
preferences folder.

The tests use isolated scenes; do not run them in the console of a work
scene. They need a Houdini installation and access to its licence server.
`test_rebuild.py` verifies the current mode, including animated curves.
`test_bridge.py` keeps, as a test only, the initial native transport (.cpio):
that code is no longer part of `parsec_nodes.py` or of the installed shelf.

The transport accepts text synchronised by Parsec; the tool does not depend on its SDK.
