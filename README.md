# Game

Demo técnica del city builder sobre la Tierra real: edificios y calles de
Cartagena de Indias importados de OpenStreetMap y levantados en Godot.

Estado actual: **paso 1**, volúmenes simples sobre las huellas reales. El
generador de edificios por estilo se construye después sobre esta base.

## Cómo correrla

Necesitas Python 3.9+ (sin dependencias) y Godot 4.3 o más nuevo.

```
python herramientas/descargar_osm.py
```

Eso descarga las zonas definidas en `herramientas/zonas.json` y deja un JSON
por zona en `godot/datos/`. Luego abre `godot/project.godot` en Godot y dale a
Ejecutar (F5).

Controles: WASD mover, clic derecho + ratón mirar, Q/E bajar y subir, Shift
rápido, rueda del ratón cambia la velocidad.

## Zonas

| Zona | Qué cubre |
| --- | --- |
| `centro` | Centro Histórico amurallado: Centro, San Diego y Getsemaní |
| `bocagrande` | Bocagrande, El Laguito y Castillogrande |

Todas comparten el mismo origen (la Torre del Reloj), así que quedan en su
posición real unas respecto a otras. Para agregar o recortar una zona basta
editar su recuadro en `zonas.json` y volver a correr el script.

## Cómo funciona

- `herramientas/descargar_osm.py` consulta Overpass, proyecta las coordenadas a
  metros (x = este, z = sur) y calcula la altura de cada edificio: usa `height`
  si existe, si no `building:levels` × 3,2 m, y si no 2 pisos por defecto.
  Guarda también las etiquetas útiles para el futuro generador (material,
  techo, uso, nombre).
- `godot/scripts/mundo.gd` lee esos JSON y construye una sola malla por zona
  con un prisma por edificio, más las calles como cintas planas.
- `godot/scripts/camara_libre.gd` es la cámara para recorrer y grabar clips.

Limitaciones conocidas: los patios interiores de los multipolígonos se
rellenan, no hay relieve todavía y los techos son planos.

## Datos

Datos del mapa © colaboradores de OpenStreetMap, bajo licencia
[ODbL](https://www.openstreetmap.org/copyright). La atribución se muestra
también dentro de la demo.
