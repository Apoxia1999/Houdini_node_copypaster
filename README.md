# Houdini_node_copypaster

**Version 2.1 · Shelf: Parsec Nodes v2.1**

Los botones principales ahora transportan una descripcion JSON de nodos, parametros y
conexiones. El destino crea nodos con la API de Houdini: no importa redes nativas,
HDAs ni bloques CPIO del origen. Para las curvas numericas usa segmentos ACHN de texto
(solo animacion) y los remapea exclusivamente a los nodos nuevos. El texto comprimido viaja por el portapapeles de Parsec.
Esta tecnica no convierte derechos de licencia de contenido creado en Apprentice.

Probado en Linux con Houdini Apprentice 22.0.466. Verificaciones: conexiones, parametros,
colisiones de nombres, Attribute Wrangle y VEX, parametros personalizados, expresiones y
rampas, claves numericas y de texto, tangentes separadas y automaticas, subframes,
interpolacion y extrapolacion ciclica. Las curvas se comparan en mas de mil muestras
y tambien entre escenas con FPS diferentes. Tambien probado cargando y ejecutando los scripts reales de la shelf con el
portapapeles Qt. La comprobacion de la licencia de una sesion FX comercial en Windows
queda pendiente de la prueba del usuario; no hay una licencia FX disponible aqui.

## Instalar o actualizar en Linux

Descarga el repositorio o el ZIP y extraelo. En Windows > Python Shell de Houdini,
ejecuta esta linea sustituyendo la ruta por la ubicacion del instalador:

```python
exec(open('/ruta/Houdini_node_copypaster/install_parsec_nodes.py', encoding='utf-8').read())
```

## Instalar o actualizar en Windows mediante Parsec

1. En Linux, abre `INSTALAR_EN_WINDOWS.txt` en un editor de texto.
2. Copia la unica linea completa.
3. En Windows remoto, abre Windows > Python Shell de Houdini.
4. Pega la linea y pulsa Enter.

El instalador escribe `toolbar/parsec_nodes.shelf` en `$HOUDINI_USER_PREF_DIR`.
No necesita permisos de administrador ni reiniciar Houdini. Si el conjunto de shelves
activo esta protegido, la instalacion termina y explica como mostrar la pestana manualmente:
menu + a la derecha de las shelves > Shelves > Parsec Nodes v2.1.

Alternativa: extrae el ZIP y ejecuta desde Python Shell, usando la ruta real:

```python
exec(open(r'C:\ruta\install_parsec_nodes.py', encoding='utf-8').read())
```

## Prueba entre equipos

1. Actualiza ambos equipos y comprueba que aparece Parsec Nodes v2.1.
2. Selecciona Box > Transform, o una cadena de nodos estandar de una sola red.
3. Pulsa Copy Nodes. El mensaje inferior indicara modo reconstruccion.
4. En Parsec, espera un segundo y entra en una red vacia del mismo tipo (SOP en SOP).
5. Pulsa Paste Nodes. Comprueba los nodos y la edicion de licencia que muestra Houdini.
6. Prueba primero en una sesion de FX nueva, sin escenas de trabajo abiertas.

El formato v2 tiene un prefijo distinto al antiguo. Hay que volver a copiar tras actualizar.
Si falla la transferencia remota, comprueba que texto normal llegue a Bloc de notas.

## Alcance actual

- Cadenas de nodos estandar incluidos con Houdini, sin subredes editadas dentro.
- Parametros estaticos, expresiones HScript (tambien en menus, casillas y enteros), VEX, rampas,
  parametros personalizados y conexiones internas.
- No se transportan expresiones Python ni llamadas HScript que ejecutan procesos o Python
  (`system`, `execute`, `run`, `pythonexpr*`): un pegado que las contenga se rechaza entero.
- Animacion: claves numericas y de texto, interpolacion, tangentes y aceleraciones,
  pendientes automaticas, valores de entrada/salida separados y extrapolacion.
- Los tiempos se conservan en segundos. Si cambia el FPS del destino, cambian los numeros
  de frame correspondientes, pero no se modifica el FPS global de la escena.
- Los HDAs estandar incluidos en la instalacion se crean desde la definicion del destino.
- Los HDAs externos y los nodos con geometria bloqueada se rechazan.
- Notas y cajas no se copian con el modo reconstruccion: selecciona los nodos que quieres pasar.
- No se transportan texturas, caches ni archivos externos. Las referencias a otros nodos
  se conservan como texto y pueden requerir ajustes, especialmente si hay nombres repetidos.
- La copia de descripciones no elimina las restricciones de archivos o HDAs no comerciales
  que se carguen despues mediante esas referencias.
- Los tipos y parametros deben existir en el destino. Una reconstruccion que falla revierte
  los nodos nuevos y conserva los nodos preexistentes.
- Limite interno de transporte: 32 MiB de descripcion sin comprimir. Limite real de Parsec no medido.

## Atajos

Ctrl+Alt+Shift y clic en Copy Nodes abre el editor de atajos. Puedes asignar Ctrl+Shift+C.
Haz lo mismo para Paste Nodes con Ctrl+Shift+V; revisa los conflictos que indique Houdini.
Los atajos no se asignan automaticamente.

## Desinstalar

Quita la pestana de la shelf y, con Houdini cerrado, elimina
`toolbar/parsec_nodes.shelf` de la carpeta de preferencias del usuario.

## Actualizacion v2.1

Actualiza los dos equipos antes de copiar animaciones. La v2 inicial no sabia leer
los nuevos campos de claves. Vuelve a ejecutar el instalador en cada Houdini y copia de nuevo.

Las curvas numericas se guardan con sus segmentos exactos de canal, en vez de
reconstruir unicamente los campos publicos de las claves. Esto conserva tambien
las aceleraciones implicitas de las tangentes automaticas Bezier. Las claves de
texto se transportan mediante sus tiempos, expresiones y lenguajes.

## Desarrollo y verificacion

`parsec_nodes.py` contiene la herramienta. `build.py` genera la shelf, el instalador
autonomo, la linea de instalacion por portapapeles y el ZIP distribuible.

```sh
python build.py
/path/to/houdini/bin/hython test_rebuild.py
/path/to/houdini/bin/hython test_bridge.py
```

Las pruebas usan escenas aisladas; no deben ejecutarse en la consola de una escena
de trabajo. Requieren una instalacion de Houdini y acceso a su servidor de licencias.
`test_rebuild.py` verifica el modo actual, incluidas las curvas animadas.
`test_bridge.py` conserva las pruebas del transporte nativo inicial, que no se usa
en los botones principales de reconstruccion.

El transporte admite texto sincronizado por Parsec; la herramienta no depende de su SDK.
