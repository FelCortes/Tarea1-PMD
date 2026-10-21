#!/usr/bin/env python3
"""
Orquestador general para la Tarea 1.
Ejecuta todo el pipeline de forma automatizada:
    python ejecutar_todo.py
"""
import os
import subprocess
import sys
import time

def ejecutar_comando(cmd, descripcion):
    print(f"\n==================================================")
    print(f"📌 {descripcion}")
    print(f"Comando: {' '.join(cmd)}")
    print(f"==================================================")
    
    resultado = subprocess.run(cmd)
    if resultado.returncode != 0:
        print(f"\n⛔ Error durante la ejecución de: {descripcion}", file=sys.stderr)
        sys.exit(resultado.returncode)
    print(f"✅ ¡{descripcion} completado con éxito!\n")

def main():
    print("🚀 Iniciando el pipeline completo de la Tarea 1 (Santiago Centro)...")

    # Paso 1: Preparar datos de OSM (usa el GeoPackage existente o lo genera)
    gpkg_path = os.path.join("datos", "osm_santiago-centro.gpkg")
    if os.path.exists(gpkg_path):
        print(f"\nℹ️ El archivo '{gpkg_path}' ya existe. Saltando el recorte...")
    else:
        ejecutar_comando(
            [sys.executable, "preparar_datos.py", "--zona", "santiago-centro"],
            "Paso 1: Preparar datos de OpenStreetMap (preparar_datos.py)"
        )

    # Paso 2: Levantar el contenedor de Docker con PostGIS
    ejecutar_comando(
        ["docker", "compose", "up", "-d"],
        "Paso 2: Levantar contenedor Docker con PostGIS (docker compose up -d)"
    )

    # Pausa prudencial para asegurar que la base de datos termine de iniciar
    print("\n⏳ Esperando 8 segundos a que PostGIS esté completamente listo...")
    time.sleep(8)

    # Paso 3: Ejecutar el script ETL de carga completa
    ejecutar_comando(
        [sys.executable, "carga_todo.py"],
        "Paso 3: Cargar tablas e índices espaciales en PostGIS (carga_todo.py)"
    )

    # Paso 4: Ejecutar las consultas SQL (crea la grilla y las vistas necesarias para el mapa)
    ejecutar_comando(
        ["docker", "exec", "-i", "postgis_tarea1", "psql", "-U", "postgres", "-d", "santiago_centro", "-f", "/workspace/consultas.sql"],
        "Paso 4: Ejecutar consultas SQL y crear la grilla (consultas.sql)"
    )

    # Paso 5: Generar el mapa obligatorio de la grilla hexagonal
    ejecutar_comando(
        [sys.executable, "generar_mapa.py"],
        "Paso 5: Generar mapa de la grilla hexagonal (generar_mapa.py)"
    )

    print("\n🎉 ¡PROCESO COMPLETO FINALIZADO CON ÉXITO!")
    print("👉 Tu base de datos está lista, las consultas ejecutadas y el mapa 'mapa_grilla_hexagonal.png' generado.")

if __name__ == "__main__":
    main()