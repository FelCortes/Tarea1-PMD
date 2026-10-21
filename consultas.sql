-- ==========================================
-- CONSULTA 1: Paraderos por comuna y su densidad (Santiago Centro)
-- ==========================================
SELECT 
    c.cut_com AS codigo_comuna,
    COUNT(p.stop_id) AS total_paraderos,
    ROUND(ST_Area(ST_MakeValid(c.geom))::numeric / 1000000, 2) AS area_km2,
    ROUND(COUNT(p.stop_id)::numeric / NULLIF(ST_Area(ST_MakeValid(c.geom))::numeric / 1000000, 0), 2) AS densidad_por_km2
FROM comunas_cl c
LEFT JOIN paraderos_gtfs p ON c.geom && p.geom AND ST_Intersects(ST_MakeValid(c.geom), p.geom)
WHERE c.cut_com = '13101'
GROUP BY c.cut_com, c.geom
ORDER BY total_paraderos DESC;


-- ==========================================
-- CONSULTA 2: Cobertura de edificios respecto a paraderos (CON EXPLAIN ANALYZE)
-- ==========================================
/*
   ANÁLISIS DE RENDIMIENTO (EXPLAIN ANALYZE):
   - Índice utilizado: Índice espacial GIST de la tabla paraderos (`idx_paraderos_gtfs_geom`) y de la tabla `multipolygons`.
   - De qué lado se aplica: Se aplica del lado de la función geoespacial (`ST_DWithin` / `ST_Intersects`), 
     transformando la búsqueda relacional en un Bitmap Index Scan sobre los árboles R-Tree.
   - Qué pasaría sin él: PostgreSQL realizaría un Seq Scan (barrido secuencial) absoluto, comparando 
     cada uno de los edificios contra los paraderos uno por uno, elevando drásticamente el tiempo de CPU.
*/
EXPLAIN ANALYZE
WITH edificios_distancia AS (
    SELECT 
        e.osm_id AS edificio_id,
        c.cut_com AS comuna,
        NOT EXISTS (
            SELECT 1 FROM paraderos_gtfs p 
            WHERE p.geom && ST_MakeValid(e.geom) AND ST_DWithin(ST_MakeValid(e.geom), p.geom, 500)
        ) AS sin_cobertura
    FROM multipolygons e
    JOIN comunas_cl c ON c.geom && e.geom AND ST_Intersects(ST_MakeValid(c.geom), ST_MakeValid(e.geom))
    WHERE c.cut_com = '13101' AND e.building IS NOT NULL
)
SELECT 
    comuna,
    COUNT(*) AS total_edificios,
    SUM(CASE WHEN sin_cobertura THEN 1 ELSE 0 END) AS edificios_lejos,
    ROUND(100.0 * SUM(CASE WHEN sin_cobertura THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS porcentaje_sin_cobertura
FROM edificios_distancia
GROUP BY comuna
ORDER BY porcentaje_sin_cobertura DESC;


-- ==========================================
-- CONSULTA 3: Dos fuentes, un objeto (Anti-joins)
-- ==========================================
SELECT COUNT(*) AS gtfs_sin_osm_cerca
FROM paraderos_gtfs p
WHERE NOT EXISTS (
    SELECT 1 FROM points o 
    WHERE p.geom && o.geom AND ST_DWithin(p.geom, ST_MakeValid(o.geom), 50)
);


-- ==========================================
-- CONSULTA 4: Kilómetros de recorrido por comuna (CON EXPLAIN ANALYZE)
-- ==========================================
/*
   ANÁLISIS DE RENDIMIENTO (EXPLAIN ANALYZE):
   - Índice utilizado: Índice GIST sobre la columna geométrica de la tabla `recorridos` (`idx_recorridos_geom`) y comunas.
   - De qué lado se aplica: Se aplica en la fase de filtrado previo de `ST_Intersects` (operador rápido `&&`), 
     filtrando cajas contenedoras (bounding boxes) antes de calcular la intersección geométrica exacta.
   - Qué pasaría sin él: La base de datos tendría que evaluar la intersección matemática de cada línea de transporte 
     con el polígono comunal de forma completamente secuencial (Seq Scan), disparando el costo de cómputo.
*/
EXPLAIN ANALYZE
SELECT 
    c.cut_com AS comuna,
    ROUND(SUM(ST_Length(ST_Intersection(r.geom, ST_MakeValid(c.geom))))::numeric / 1000.0, 2) AS total_kilometros
FROM comunas_cl c
JOIN recorridos r ON c.geom && r.geom AND ST_Intersects(ST_MakeValid(c.geom), r.geom)
WHERE c.cut_com = '13101'
GROUP BY c.cut_com
ORDER BY total_kilometros DESC;


-- ==========================================
-- CONSULTA 5: Vecino más cercano (CROSS JOIN LATERAL)
-- ==========================================
SELECT 
    p.stop_name,
    a.other_tags,
    ROUND((p.geom <-> ST_MakeValid(a.geom))::numeric, 2) AS distancia_metros
FROM paraderos_gtfs p
CROSS JOIN LATERAL (
    SELECT other_tags, geom 
    FROM points 
    WHERE (other_tags ILIKE '%pharmacy%' 
       OR other_tags ILIKE '%hospital%'
       OR other_tags ILIKE '%doctors%')
    ORDER BY p.geom <-> ST_MakeValid(geom) 
    LIMIT 1
) a
LIMIT 20;


-- ==========================================
-- CONSULTA 6: Grilla hexagonal (500m) (CON EXPLAIN ANALYZE)
-- ==========================================
/*
   ANÁLISIS DE RENDIMIENTO (EXPLAIN ANALYZE):
   - Índice utilizado: Índices GIST en `multipolygons` y `recorridos`.
   - De qué lado se aplica: Se aplica en el `LEFT JOIN` espacial sobre las celdas generadas por `ST_HexagonGrid`, 
     permitiendo ubicar rápidamente qué entidades caen dentro de cada hexágono mediante el índice espacial.
   - Qué pasaría sin él: Provocaría un colapso en el rendimiento (Nested Loop masivo), evaluando millones 
     de combinaciones espaciales posibles sin soporte de índices, volviendo la consulta inviable.
*/
DROP MATERIALIZED VIEW IF EXISTS grilla_transporte_edificios CASCADE;

CREATE MATERIALIZED VIEW grilla_transporte_edificios AS
SELECT 
    h.geom AS cell_geom,
    COUNT(DISTINCT e.osm_id) AS total_edificios,
    COUNT(DISTINCT r.route_short_name) AS total_recorridos
FROM ST_HexagonGrid(500, (SELECT ST_Union(ST_MakeValid(geom)) FROM comunas_cl WHERE cut_com = '13101')) h
LEFT JOIN multipolygons e ON h.geom && e.geom AND ST_Intersects(h.geom, ST_MakeValid(e.geom)) AND e.building IS NOT NULL
LEFT JOIN recorridos r ON h.geom && r.geom AND ST_Intersects(h.geom, r.geom)
GROUP BY h.geom;

EXPLAIN ANALYZE
SELECT * FROM grilla_transporte_edificios
ORDER BY total_edificios DESC, total_recorridos ASC
LIMIT 10;


-- ==========================================
-- CONSULTA 7: Pregunta propia (Cruce OSM + GTFS)
-- ==========================================
SELECT 
    c.cut_com AS comuna,
    COUNT(e.osm_id) AS edificios_educacionales_cerca_paraderos
FROM comunas_cl c
JOIN multipolygons e ON c.geom && e.geom AND ST_Intersects(ST_MakeValid(c.geom), ST_MakeValid(e.geom))
WHERE c.cut_com = '13101'
  AND (e.other_tags ILIKE '%school%' OR e.other_tags ILIKE '%university%')
  AND EXISTS (
      SELECT 1 FROM paraderos_gtfs p 
      WHERE p.geom && ST_MakeValid(e.geom) AND ST_DWithin(ST_MakeValid(e.geom), p.geom, 200)
  )
GROUP BY c.cut_com
ORDER BY edificios_educacionales_cerca_paraderos DESC;