#!/usr/bin/env python3
"""Descarga edificios y calles de OpenStreetMap y los deja listos para Godot.

Uso:
    python herramientas/descargar_osm.py              # todas las zonas
    python herramientas/descargar_osm.py centro       # solo una

Solo usa la biblioteca estándar de Python 3.9+.

Cada zona de zonas.json se guarda en godot/datos/<zona>.json con las
coordenadas ya proyectadas a metros respecto a un origen común, así las zonas
quedan en su posición real unas respecto a otras:
    x = este, z = sur (Godot mira hacia -Z, así el norte queda "arriba").

Datos © colaboradores de OpenStreetMap, licencia ODbL.
"""
from __future__ import annotations

import json
import math
import sys
import time
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ZONAS = Path(__file__).resolve().parent / "zonas.json"
CRUDO = Path(__file__).resolve().parent / "crudo"  # copia de la respuesta de OSM (no se sube a git)
SALIDA = RAIZ / "godot" / "datos"
# Servidores públicos de Overpass; se prueban en orden si alguno está caído.
SERVIDORES = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
ATRIBUCION = "© colaboradores de OpenStreetMap (ODbL) — openstreetmap.org/copyright"

ALTURA_PISO = 3.2       # metros por piso
PISOS_POR_DEFECTO = 2   # cuando OSM no dice nada
RADIO_TIERRA = 6378137.0

# Ancho en metros según el tipo de vía, cuando OSM no trae "width" ni "lanes".
ANCHOS = {
    "motorway": 14, "trunk": 12, "primary": 10, "secondary": 9, "tertiary": 8,
    "residential": 6, "unclassified": 6, "living_street": 5, "service": 4,
    "pedestrian": 5, "footway": 2, "path": 1.5, "steps": 2, "cycleway": 2,
}


def consulta(bbox: dict) -> str:
    caja = f'{bbox["sur"]},{bbox["oeste"]},{bbox["norte"]},{bbox["este"]}'
    return f"""[out:json][timeout:120];
(
  way["building"]({caja});
  relation["building"]["type"="multipolygon"]({caja});
  way["building:part"]({caja});
  way["highway"]({caja});
);
out body geom;"""


def descargar(bbox: dict) -> dict:
    datos = urllib.parse.urlencode({"data": consulta(bbox)}).encode()
    for intento in range(4):
        for servidor in SERVIDORES:
            pedido = urllib.request.Request(
                servidor, data=datos, headers={"User-Agent": "demo-edificios-osm/0.1"}
            )
            try:
                with urllib.request.urlopen(pedido, timeout=180) as r:
                    return json.load(r)
            except Exception as e:  # la API pública a veces está ocupada
                print(f"  {urllib.parse.urlparse(servidor).netloc} falló ({e})")
        espera = 5 * 2**intento
        print(f"  reintento en {espera}s")
        time.sleep(espera)
    raise SystemExit("No se pudo descargar de Overpass. Intenta más tarde.")


def proyector(origen: dict):
    """Proyección equirectangular local: de sobra para unos pocos km."""
    lat0, lon0 = math.radians(origen["lat"]), math.radians(origen["lon"])
    cos0 = math.cos(lat0)

    def a_metros(lat: float, lon: float) -> list[float]:
        x = (math.radians(lon) - lon0) * cos0 * RADIO_TIERRA
        z = -(math.radians(lat) - lat0) * RADIO_TIERRA
        return [round(x, 2), round(z, 2)]

    return a_metros


def numero(texto) -> float | None:
    """'12', '12.5 m', '12,5' -> float; cualquier otra cosa -> None."""
    if texto is None:
        return None
    limpio = str(texto).lower().replace(",", ".").replace("m", "").strip()
    try:
        return float(limpio)
    except ValueError:
        return None


def altura_de(tags: dict) -> tuple[float, int, str]:
    """Devuelve (altura en m, pisos, de dónde salió el dato)."""
    altura = numero(tags.get("height"))
    pisos = numero(tags.get("building:levels"))
    if altura and altura > 0:
        return altura, max(1, round(pisos or altura / ALTURA_PISO)), "height"
    if pisos and pisos > 0:
        return round(pisos * ALTURA_PISO, 1), int(round(pisos)), "levels"
    return PISOS_POR_DEFECTO * ALTURA_PISO, PISOS_POR_DEFECTO, "defecto"


def pisos_estimados(ident: str, area_m2: float, regla: dict | None) -> int | None:
    """Inventa un número de pisos creíble cuando OSM no lo trae.

    En barrios de torres (Bocagrande, Castillogrande, Manga) casi ningún
    edificio tiene altura en OSM y todo quedaría de 2 pisos. La regla de la zona
    (clave "altura_estimada" en zonas.json) dice desde qué área de huella un
    edificio se trata como torre, qué proporción de esos lo es y entre cuántos
    pisos. El resultado depende solo del id, así que no cambia entre corridas.
    """
    if not regla or area_m2 < regla["area_min"] or area_m2 > regla.get("area_max", 6000):
        return None
    azar = zlib.crc32(ident.encode()) / 0xFFFFFFFF
    if azar > regla.get("proporcion", 1.0):
        return None
    minimo, maximo = regla["pisos"]
    azar2 = zlib.crc32((ident + "/pisos").encode()) / 0xFFFFFFFF
    # Al cuadrado: muchas torres medianas y pocas muy altas.
    return int(round(minimo + (maximo - minimo) * azar2**2))


def anillo(geometria: list, a_metros) -> list | None:
    """Convierte un anillo de OSM a metros, sin el punto de cierre repetido."""
    pts = [a_metros(p["lat"], p["lon"]) for p in geometria]
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts.pop()
    limpio = [p for i, p in enumerate(pts) if p != pts[i - 1]]
    return limpio if len(limpio) >= 3 else None


def area(pts: list) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))) / 2


ETIQUETAS_UTILES = (
    "name", "building", "building:part", "building:material", "building:colour",
    "roof:shape", "roof:material", "roof:colour", "roof:levels", "amenity",
    "historic", "tourism", "start_date", "architect", "heritage", "min_height",
)


def edificio(ident: str, pts: list, tags: dict, regla: dict | None = None,
             externas: dict | None = None) -> dict:
    altura, pisos, fuente = altura_de(tags)
    # Orden de confianza: etiqueta de OSM > Overture > estimación > 2 pisos.
    externa = (externas or {}).get(ident.split("/")[0] + "/" + ident.split("/")[1])
    if fuente == "defecto" and externa:
        altura = externa.get("altura") or externa["pisos"] * ALTURA_PISO
        pisos = int(externa.get("pisos") or max(1, round(altura / ALTURA_PISO)))
        altura, fuente = round(altura, 1), "overture"
    if fuente == "defecto":
        estimados = pisos_estimados(ident, area(pts), regla)
        if estimados:
            altura, pisos, fuente = round(estimados * ALTURA_PISO, 1), estimados, "estimada"
    return {
        "id": ident,
        "huella": pts,
        "altura": altura,
        "pisos": pisos,
        "fuente_altura": fuente,
        "area": round(area(pts), 1),
        "tags": {k: tags[k] for k in ETIQUETAS_UTILES if k in tags},
    }


def unir_anillos(tramos: list) -> list:
    """Une los tramos 'outer' de un multipolígono en anillos cerrados."""
    tramos = [list(t) for t in tramos if t]
    anillos = []
    while tramos:
        actual = tramos.pop(0)
        while actual[0] != actual[-1]:
            for i, t in enumerate(tramos):
                if t[0] == actual[-1]:
                    actual += t[1:]
                elif t[-1] == actual[-1]:
                    actual += t[-2::-1]
                else:
                    continue
                tramos.pop(i)
                break
            else:
                break  # anillo abierto: datos incompletos, se descarta
        if actual[0] == actual[-1]:
            anillos.append(actual)
    return anillos


def alturas_externas(zona_id: str) -> dict:
    """Alturas de Overture guardadas por alturas_overture.py, si existen."""
    archivo = CRUDO / f"overture_alturas_{zona_id}.json"
    if archivo.exists():
        return json.loads(archivo.read_text(encoding="utf-8"))
    return {}


def procesar(crudo: dict, zona_id: str, zona: dict, origen: dict) -> dict:
    a_metros = proyector(origen)
    regla = zona.get("altura_estimada")
    externas = alturas_externas(zona_id)
    edificios, calles = [], []
    for e in crudo["elements"]:
        tags = e.get("tags", {})
        if e["type"] == "way" and "geometry" in e:
            if "highway" in tags:
                pts = [a_metros(p["lat"], p["lon"]) for p in e["geometry"]]
                tipo = tags["highway"]
                carriles = numero(tags.get("lanes"))
                ancho = numero(tags.get("width")) or (carriles and carriles * 3.2) or ANCHOS.get(tipo, 4)
                calles.append({
                    "id": f'way/{e["id"]}', "puntos": pts, "tipo": tipo,
                    "ancho": round(ancho, 1), "nombre": tags.get("name", ""),
                })
            elif "building" in tags or "building:part" in tags:
                pts = anillo(e["geometry"], a_metros)
                if pts:
                    edificios.append(edificio(f'way/{e["id"]}', pts, tags, regla, externas))
        elif e["type"] == "relation":
            # Por ahora solo los contornos exteriores; los patios (inner) se rellenan.
            tramos = [
                [(p["lat"], p["lon"]) for p in m["geometry"]]
                for m in e.get("members", [])
                if m.get("role") == "outer" and "geometry" in m
            ]
            for n, cerrado in enumerate(unir_anillos(tramos)):
                pts = anillo([{"lat": la, "lon": lo} for la, lo in cerrado], a_metros)
                if pts:
                    edificios.append(edificio(f'relation/{e["id"]}/{n}', pts, tags, regla, externas))
    b = zona["bbox"]
    return {
        "zona": zona_id,
        "nombre": zona["nombre"],
        "atribucion": ATRIBUCION,
        "origen": {"lat": origen["lat"], "lon": origen["lon"]},
        "limites": [a_metros(b["norte"], b["oeste"]), a_metros(b["sur"], b["este"])],
        "edificios": edificios,
        "calles": calles,
    }


def main() -> None:
    config = json.loads(ZONAS.read_text(encoding="utf-8"))
    args = sys.argv[1:]
    # --sin-descargar reutiliza la última respuesta guardada en herramientas/crudo/
    # (útil para ajustar alturas en zonas.json sin volver a pedirle nada a OSM).
    sin_descargar = "--sin-descargar" in args
    pedidas = [a for a in args if not a.startswith("--")] or list(config["zonas"])
    SALIDA.mkdir(parents=True, exist_ok=True)
    CRUDO.mkdir(exist_ok=True)
    for zona_id in pedidas:
        if zona_id not in config["zonas"]:
            raise SystemExit(f"Zona desconocida: {zona_id}. Opciones: {', '.join(config['zonas'])}")
        zona = config["zonas"][zona_id]
        cache = CRUDO / f"{zona_id}.json"
        if sin_descargar and cache.exists():
            print(f"{zona['nombre']}: usando copia local")
            crudo = json.loads(cache.read_text(encoding="utf-8"))
        else:
            print(f"{zona['nombre']}: descargando…")
            crudo = descargar(zona["bbox"])
            cache.write_text(json.dumps(crudo), encoding="utf-8")
            time.sleep(2)  # cortesía con la API pública
        datos = procesar(crudo, zona_id, zona, config["origen"])
        destino = SALIDA / f"{zona_id}.json"
        destino.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        cuenta = {"height": 0, "levels": 0, "overture": 0, "estimada": 0, "defecto": 0}
        for e in datos["edificios"]:
            cuenta[e["fuente_altura"]] += 1
        print(f"  {len(datos['edificios'])} edificios, {len(datos['calles'])} calles -> {destino.relative_to(RAIZ)}")
        print(f"  alturas: {cuenta['height'] + cuenta['levels']} de OSM, {cuenta['overture']} de Overture, "
              f"{cuenta['estimada']} estimadas, {cuenta['defecto']} con {PISOS_POR_DEFECTO} pisos por defecto")


if __name__ == "__main__":
    main()
