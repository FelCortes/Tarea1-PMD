import os
import csv
import subprocess
import psycopg2

DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "santiago_centro"
DB_USER = "postgres"
DB_PASS = "postgrespassword"

def main():
    print("🚀 Iniciando la carga completa (ETL) a PostGIS en EPSG:5361...")

    # Conexión a PostgreSQL
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )
    conn.autocommit = True
    cursor = conn.cursor()

    # 1. Cargar Comunas (Usa psql nativo de Docker)
    if os.path.exists("datos/comunas_cl.sql"):
        print("📂 [1/3] Cargando comunas...")
        cursor.execute("DROP TABLE IF EXISTS comunas_cl CASCADE;")
        subprocess.run(
            f"docker exec -i postgis_tarea1 psql -U {DB_USER} -d {DB_NAME} -f /workspace/datos/comunas_cl.sql", 
            shell=True
        )
        print("✅ Comunas cargadas correctamente.")

    # 2. Procesar Paraderos GTFS (Lectura eficiente por lotes con Python DictReader)
    print("🚌 [2/3] Procesando Paraderos GTFS...")
    gtfs_dir = "datos/gtfs"
    for root, dirs, files in os.walk("datos"):
        if "stops.txt" in files:
            gtfs_dir = root
            break

    stops_path = os.path.join(gtfs_dir, "stops.txt")
    if os.path.exists(stops_path):
        cursor.execute("""
            DROP TABLE IF EXISTS paraderos_gtfs CASCADE;
            CREATE TABLE paraderos_gtfs (
                stop_id VARCHAR PRIMARY KEY,
                stop_code VARCHAR,
                stop_name VARCHAR,
                geom GEOMETRY(Point, 5361)
            );
        """)
        
        insert_query = """
            INSERT INTO paraderos_gtfs (stop_id, stop_code, stop_name, geom)
            VALUES (%s, %s, %s, ST_Transform(ST_SetSRID(ST_MakePoint(%s::float, %s::float), 4326), 5361))
            ON CONFLICT (stop_id) DO NOTHING;
        """
        
        batch = []
        paraderos_cargados = 0
        with open(stops_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    s_id = row.get('stop_id')
                    s_code = row.get('stop_code', '')
                    s_name = row.get('stop_name', '')
                    lat = float(row['stop_lat'])
                    lon = float(row['stop_lon'])
                    batch.append((s_id, s_code, s_name, lon, lat))
                    paraderos_cargados += 1
                    
                    if len(batch) >= 1000:
                        cursor.executemany(insert_query, batch)
                        batch = []
                except (KeyError, ValueError):
                    continue
            if batch:
                cursor.executemany(insert_query, batch)

        cursor.execute("""
            CREATE INDEX idx_paraderos_gtfs_geom ON paraderos_gtfs USING GIST(geom);
            ANALYZE paraderos_gtfs;
        """)
        print(f"✅ Paraderos GTFS procesados ({paraderos_cargados} paraderos cargados).")

    # 3. Procesar Recorridos GTFS (Shapes y Rutas)
    print("🛤️ [3/3] Procesando Recorridos (Shapes y Rutas GTFS)...")
    shapes_path = os.path.join(gtfs_dir, "shapes.txt")
    trips_path = os.path.join(gtfs_dir, "trips.txt")
    routes_path = os.path.join(gtfs_dir, "routes.txt")

    if os.path.exists(shapes_path) and os.path.exists(trips_path) and os.path.exists(routes_path):
        cursor.execute("""
            DROP TABLE IF EXISTS shapes_temp CASCADE;
            CREATE TEMP TABLE shapes_temp (c1 TEXT, c2 TEXT, c3 TEXT, c4 TEXT);
            
            DROP TABLE IF EXISTS trips_temp CASCADE;
            CREATE TEMP TABLE trips_temp (c1 TEXT, c2 TEXT, c3 TEXT, c4 TEXT, c5 TEXT, c6 TEXT, c7 TEXT, c8 TEXT, c9 TEXT);
            
            DROP TABLE IF EXISTS routes_temp CASCADE;
            CREATE TEMP TABLE routes_temp (c1 TEXT, c2 TEXT, c3 TEXT, c4 TEXT, c5 TEXT, c6 TEXT, c7 TEXT, c8 TEXT, c9 TEXT);
        """)
        
        with open(shapes_path, 'r', encoding='utf-8', errors='ignore') as f:
            cursor.copy_expert("COPY shapes_temp FROM STDIN WITH CSV HEADER", f)
        with open(trips_path, 'r', encoding='utf-8', errors='ignore') as f:
            cursor.copy_expert("COPY trips_temp FROM STDIN WITH CSV HEADER", f)
        with open(routes_path, 'r', encoding='utf-8', errors='ignore') as f:
            cursor.copy_expert("COPY routes_temp FROM STDIN WITH CSV HEADER", f)

        cursor.execute("""
            DROP TABLE IF EXISTS recorridos CASCADE;
            CREATE TABLE recorridos AS
            WITH shapes_clean AS (
                SELECT c1 AS shape_id, c2::float AS shape_pt_lat, c3::float AS shape_pt_lon, c4::int AS shape_pt_sequence
                FROM shapes_temp WHERE c2 ~ '^[0-9.-]+$' AND c3 ~ '^[0-9.-]+$'
            ),
            trips_clean AS (
                SELECT c1 AS route_id, c3 AS trip_id, c6 AS shape_id FROM trips_temp
            ),
            routes_clean AS (
                SELECT c1 AS route_id, c3 AS route_short_name FROM routes_temp
            )
            SELECT 
                t.shape_id,
                r.route_short_name,
                ST_Transform(
                    ST_MakeLine(
                        ST_SetSRID(ST_MakePoint(s.shape_pt_lon, s.shape_pt_lat), 4326)
                        ORDER BY s.shape_pt_sequence
                    ), 5361
                ) AS geom
            FROM shapes_clean s
            JOIN trips_clean t ON s.shape_id = t.shape_id
            JOIN routes_clean r ON t.route_id = r.route_id
            GROUP BY t.shape_id, r.route_short_name;

            CREATE INDEX idx_recorridos_geom ON recorridos USING GIST(geom);
            ANALYZE recorridos;
            
            DROP TABLE IF EXISTS shapes_temp;
            DROP TABLE IF EXISTS trips_temp;
            DROP TABLE IF EXISTS routes_temp;
        """)
        print("✅ Recorridos (LineString) construidos e indexados correctamente.")

    cursor.close()
    conn.close()
    print("🎉 ¡ETL completado con éxito!")

if __name__ == "__main__":
    main()