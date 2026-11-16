# Changelog

La version esta en `__version__` de `parsec_nodes.py`; la etiqueta de la shelf, el
instalador y el nombre del ZIP se generan a partir de ella.

## 2.1

- Las curvas numericas se guardan con sus segmentos exactos de canal (ACHN), en vez de
  reconstruir unicamente los campos publicos de las claves. Conserva las aceleraciones
  implicitas de las tangentes automaticas Bezier.
- Las claves de texto se transportan mediante sus tiempos, expresiones y lenguajes.
- Hay que actualizar los dos equipos antes de copiar animaciones: la 2.0 no lee los
  nuevos campos de claves.

## 2.0

- Modo reconstruccion: los botones transportan una descripcion JSON de nodos, parametros
  y conexiones, y el destino crea los nodos con la API de Houdini. Ya no se importan
  redes nativas, HDAs ni bloques CPIO del origen.
- Prefijo de formato nuevo (`HOUDINI_PARSEC_REBUILD_V1:`): hay que volver a copiar tras actualizar.
