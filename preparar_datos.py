#!/usr/bin/env python3
"""
Prepara el extracto de OpenStreetMap usando la imagen oficial pública de GDAL (osgeo/gdal:ubuntu-full-latest)
para garantizar exactamente las mismas columnas, tipos de datos y estructura originales.

    python3 preparar_datos.py --zona santiago-centro
    python3 preparar_datos.py --forzar
    python3 preparar_datos.py --sql
"""
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTE = os.path.join(AQUI, "datos_fuente")
DESTINO = os.path.join(AQUI, "datos")

URL_FICHA = "https://download.geofabrik.de/south-america/chile.html"
URL_PBF = "https://download.geofabrik.de/south-america/chile-latest.osm.pbf"

SRID_CARGA = 5361
IMAGEN_GDAL = "osgeo/gdal:ubuntu-full-latest"
CAPAS = ("points", "lines", "multipolygons")

ZONAS = {
    "gran-valparaiso": (-71.75, -33.16, -71.33, -32.88),
    "santiago-centro": (-70.75, -33.52, -70.52, -33.36),
    "gran-concepcion": (-73.22, -37.06, -72.92, -36.66),
    "gran-santiago":   (-70.90, -33.68, -70.42, -33.28),
}


def salir(mensaje):
    print(f"\n⛔ {mensaje}", file=sys.stderr)
    sys.exit(1)


def argumentos():
    args = sys.argv[1:]
    zona, bbox, nombre = "gran-valparaiso", None, None
    forzar, sql = "--forzar" in args, "--sql" in args
    if "--zona" in args:
        zona = args[args.index("--zona") + 1]
        if zona not in ZONAS:
            salir(f"Zona desconocida: {zona}. Disponibles: {', '.join(ZONAS)}")
    if "--bbox" in args:
        i = args.index("--bbox")
        try:
            bbox = tuple(float(v) for v in args[i + 1:i + 5])
            assert len(bbox) == 4 and bbox[0] < bbox[2] and bbox[1] < bbox[3]
        except (ValueError, AssertionError):
            salir("--bbox espera cuatro números: xmin ymin xmax ymax")
        if "--nombre" not in args:
            salir("--bbox necesita --nombre <nombre-de-la-zona>")
        nombre = args[args.index("--nombre") + 1]
    if bbox is None:
        bbox, nombre = ZONAS[zona], zona
    return nombre, bbox, forzar, sql


def elegir_pbf():
    os.makedirs(FUENTE, exist_ok=True)
    pbfs = sorted(f for f in os.listdir(FUENTE) if f.lower().endswith(".osm.pbf"))
    if not pbfs:
        salir(
            "No hay ningún .osm.pbf en datos_fuente/.\n"
            f"   1. Descarga «chile-latest.osm.pbf» desde: {URL_FICHA}\n"
            f"   2. Déjalo en: {FUENTE}"
        )
    ruta = os.path.join(FUENTE, pbfs[0])
    mb = os.path.getsize(ruta) / 1e6
    print(f"Fuente: {pbfs[0]} ({mb:.0f} MB)")
    return ruta


class OgrDockerPublico:
    """Ejecuta ogr2ogr usando la imagen oficial pública y estable de OSGeo en Docker."""
    def __init__(self):
        print(f"Usando herramienta ogr2ogr mediante la imagen Docker pública '{IMAGEN_GDAL}'...")

    def run(self, herramienta, args):
        # Monta la carpeta raíz del proyecto entero en /workspace dentro del contenedor
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{AQUI}:/workspace",
            IMAGEN_GDAL,
            herramienta
        ] + args
        return subprocess.run(cmd, capture_output=True, text=True)


def recortar(ogr, pbf, nombre, bbox, forzar):
    os.makedirs(DESTINO, exist_ok=True)
    salida = os.path.join(DESTINO, f"osm_{nombre}.gpkg")
    
    if os.path.exists(salida) and not forzar:
        print(f"\n{os.path.basename(salida)} ya existe ({os.path.getsize(salida) / 1e6:.0f} MB), se conserva")
        return salida
    if os.path.exists(salida):
        os.remove(salida)

    xmin, ymin, xmax, ymax = bbox
    print(f"\nRecortando la caja lon [{xmin}, {xmax}] · lat [{ymin}, {ymax}] y reproyectando a {SRID_CARGA}...")
    print("   (lee el archivo completo una vez dentro del contenedor — por favor espere unos momentos)...")

    pbf_nombre = os.path.basename(pbf)

    args = [
        "-f", "GPKG", f"/workspace/datos/osm_{nombre}.gpkg",
        f"/workspace/datos_fuente/{pbf_nombre}",
        *CAPAS,
        "-spat", str(xmin), str(ymin), str(xmax), str(ymax),
        "-t_srs", f"EPSG:{SRID_CARGA}",
        "-progress",
        "--config", "OSM_MAX_TMPFILE_SIZE", "4000",
    ]

    t0 = time.perf_counter()
    r = ogr.run("ogr2ogr", args)
    
    if r.returncode != 0 or not os.path.exists(salida):
        salir("ogr2ogr falló en el contenedor.\n   stderr: " + r.stderr.strip()[-600:])
        
    avisos = len([l for l in r.stderr.splitlines() if "Warning" in l])
    print(f"   → {os.path.basename(salida)} ({os.path.getsize(salida) / 1e6:.0f} MB) en {time.perf_counter() - t0:.0f} s"
          + (f" · {avisos} advertencias de geometría" if avisos else ""))
    return salida


def verificar(gpkg, nombre):
    con = sqlite3.connect(gpkg)
    capas = dict(con.execute("SELECT table_name, srs_id FROM gpkg_contents WHERE data_type = 'features'").fetchall())
    faltan = [c for c in CAPAS if c not in capas]
    if faltan:
        salir(f"Al GeoPackage le faltan capas: {faltan}")
    conteos = {c: con.execute(f'SELECT count(*) FROM "{c}"').fetchone()[0] for c in CAPAS}
    con.close()
    print(f"\nVerificación OK: {conteos['points']:,} puntos · {conteos['lines']:,} líneas · "
          f"{conteos['multipolygons']:,} polígonos · SRID {SRID_CARGA} → osm_{nombre}.gpkg")
    return conteos


NOMBRES_TABLAS = {"points": "osm_puntos", "lines": "osm_lineas", "multipolygons": "osm_poligonos"}

def generar_sql(ogr, gpkg, nombre, forzar):
    salida = os.path.join(DESTINO, f"osm_{nombre}.sql")
    if os.path.exists(salida) and not forzar:
        return
    print(f"\nGenerando {os.path.basename(salida)} (PGDump)...")
    partes = []
    for capa, tabla in NOMBRES_TABLAS.items():
        parcial = os.path.join(DESTINO, f"_{tabla}.sql")
        args = [
            "-f", "PGDump", f"/workspace/datos/_{tabla}.sql", f"/workspace/datos/osm_{nombre}.gpkg", capa,
            "-nln", tabla, "-lco", "GEOMETRY_NAME=geom", "-lco", "SPATIAL_INDEX=GIST",
            "-lco", "COLUMN_TYPES=other_tags=hstore", "-lco", "FID=id"
        ]
        r = ogr.run("ogr2ogr", args)
        if r.returncode != 0 or not os.path.exists(parcial):
            salir(f"ogr2ogr (PGDump, {capa}) falló.")
        partes.append(parcial)
    with open(salida, "w", encoding="utf-8") as f:
        f.write("CREATE EXTENSION IF NOT EXISTS postgis;\nCREATE EXTENSION IF NOT EXISTS hstore;\n")
        for p in partes:
            with open(p, encoding="utf-8") as src:
                shutil.copyfileobj(src, f)
            os.remove(p)
    print(f"   → {os.path.basename(salida)} generado con éxito.")


if __name__ == "__main__":
    nombre, bbox, forzar, sql = argumentos()
    print(f"Preparando los datos de la Tarea 1 — zona «{nombre}»...")
    pbf = elegir_pbf()
    ogr = OgrDockerPublico()
    gpkg = recortar(ogr, pbf, nombre, bbox, forzar)
    verificar(gpkg, nombre)
    if sql:
        generar_sql(ogr, gpkg, nombre, forzar)