#!/usr/bin/env python3
"""Prueba Overture Maps como fuente de alturas y las aplica a la demo.

Antes:  pip install overturemaps
        python herramientas/descargar_osm.py     (si aún no lo corriste)
Uso:    python herramientas/alturas_overture.py

Por cada zona de zonas.json:
  1. Descarga los edificios de Overture del recuadro.
  2. Imprime un informe: cuántos traen altura, de qué fuente vienen las
     huellas y cuántas alturas son nuevas respecto a lo que ya daba OSM.
  3. Guarda las alturas en herramientas/crudo/ y regenera godot/datos/ para
     que la demo las use (solo donde OSM no traía altura).

Overture Maps: edificios bajo licencia ODbL (incluye datos de OpenStreetMap,
Microsoft y Google Open Buildings, entre otros).
"""
from __future__ import annotations

import collections
import json
import re
import subprocess
import sys
from pathlib import Path

import descargar_osm as osm

ID_OSM = re.compile(r"^([wr])(\d+)")


def descargar(zona_id: str, bbox: dict) -> Path:
    destino = osm.CRUDO / f"overture_{zona_id}.geojsonl"
    caja = f'{bbox["oeste"]},{bbox["sur"]},{bbox["este"]},{bbox["norte"]}'
    orden = [sys.executable, "-m", "overturemaps", "download", f"--bbox={caja}",
             "-f", "geojsonseq", "--type=building", "-o", str(destino)]
    try:
        subprocess.run(orden, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise SystemExit(f"Falló la descarga de Overture ({e}). ¿Corriste 'pip install overturemaps'?")
    return destino


def leer(archivo: Path):
    with archivo.open(encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip("\x1e \n\r")
            if linea:
                yield json.loads(linea)["properties"]


def fuentes_de(props: dict) -> list:
    fuentes = props.get("sources") or []
    if isinstance(fuentes, str):  # algunas versiones lo escriben como texto JSON
        fuentes = json.loads(fuentes)
    return fuentes


def id_osm(fuentes: list) -> str | None:
    """'w123@4' -> 'way/123', con el mismo formato de ids que usa la demo."""
    for f in fuentes:
        m = ID_OSM.match(str(f.get("record_id") or ""))
        if m and "openstreetmap" in str(f.get("dataset", "")).lower():
            return ("way/" if m.group(1) == "w" else "relation/") + m.group(2)
    return None


def analizar(zona_id: str, archivo: Path) -> dict:
    total = con_altura = con_pisos = sin_osm = sin_osm_con_altura = altos = 0
    por_fuente = collections.Counter()
    alturas = {}
    for p in leer(archivo):
        total += 1
        fuentes = fuentes_de(p)
        por_fuente[str(fuentes[0].get("dataset", "?")) if fuentes else "?"] += 1
        altura, pisos = p.get("height"), p.get("num_floors")
        con_altura += bool(altura)
        con_pisos += bool(pisos)
        altos += bool(altura and altura >= 30)
        ident = id_osm(fuentes)
        if ident is None:
            sin_osm += 1
            sin_osm_con_altura += bool(altura or pisos)
        elif altura or pisos:
            alturas[ident] = {"altura": altura, "pisos": pisos}

    (osm.CRUDO / f"overture_alturas_{zona_id}.json").write_text(json.dumps(alturas), encoding="utf-8")

    # ¿Cuántas de esas alturas no las teníamos ya por las etiquetas de OSM?
    nuevas = None
    demo = osm.SALIDA / f"{zona_id}.json"
    if demo.exists():
        actuales = json.loads(demo.read_text(encoding="utf-8"))["edificios"]
        sin_dato = {"/".join(e["id"].split("/")[:2]) for e in actuales
                    if e["fuente_altura"] not in ("height", "levels")}
        nuevas = len(sin_dato & alturas.keys())
        print(f"  la demo tiene {len(actuales)} edificios de OSM, {len(sin_dato)} sin altura real")

    print(f"  Overture: {total} edificios; {con_altura} con altura, {con_pisos} con pisos, {altos} de 30 m o más")
    print("  huellas por fuente: " + ", ".join(f"{k} {v}" for k, v in por_fuente.most_common()))
    print(f"  huellas que NO están en OSM: {sin_osm} ({sin_osm_con_altura} con altura)")
    if nuevas is not None:
        print(f"  >>> alturas NUEVAS que aporta Overture a la demo: {nuevas}")
    return {"total": total, "con_altura": con_altura, "nuevas": nuevas}


def main() -> None:
    config = json.loads(osm.ZONAS.read_text(encoding="utf-8"))
    osm.CRUDO.mkdir(exist_ok=True)
    for zona_id, zona in config["zonas"].items():
        print(f"{zona['nombre']}:")
        analizar(zona_id, descargar(zona_id, zona["bbox"]))
    print("\nRegenerando godot/datos con las alturas de Overture…")
    sys.argv = [sys.argv[0], "--sin-descargar"]
    osm.main()


if __name__ == "__main__":
    main()
