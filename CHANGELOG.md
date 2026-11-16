# Changelog

La version esta en `__version__` de `parsec_nodes.py`; la etiqueta de la shelf, el
instalador y el nombre del ZIP se generan a partir de ella.

## 2.2

Version de seguridad. Actualiza los dos equipos. El formato del portapapeles no cambia.

- Paste Nodes revisa la descripcion completa antes de crear nada y rechaza nodos que
  ejecutan codigo, expresiones Python, llamadas HScript que lanzan procesos o Python, y
  parametros personalizados con callbacks o menus con script. En la 2.1 un portapapeles
  manipulado podia ejecutar comandos al pegar.
- Aviso unico, con Cancelar por defecto, cuando hay VEX, OpenCL o parametros personalizados.
- El texto de canal (ACHN) debe contener un solo nodo y un solo canal: ya no puede
  escribir animacion sobre nodos que ya existian en la escena.
- Aviso de licencia tambien en el modo reconstruccion; la licencia declarada es solo un indicio.
- Las expresiones en menus y casillas ya se copian (antes Copy Nodes fallaba).
- El transporte nativo (.cpio) sale del modulo y de la shelf; queda solo como prueba.
- Nombres de enumeraciones y flags validados con listas cerradas.
- Instalador: escritura atomica, copias `.bak` con fecha, `uninstall()`, version visible.
- `SHA256SUMS`, ZIP reproducible, `LICENSE` (MIT) y `README.en.md`.
- Ya no se transportan expresiones Python (antes si, en claves de texto y numericas).

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
