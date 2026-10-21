Carpetas a crear:\
En la carpeta raiz, crear "datos" y "datos_fuente", luego dentro de "datos" se debe crear la carpeta "gtfs".\
Debe quedar:\
../datos/\
../datos/gtfs/\
../datos_fuente/\
\
Archivos necesarios:\
"chile-latest.osm.pbf" - del 19 de octubre de 2026. Este archivo debe ir en ../datos_fuente/\
"comunas_cl.sql" - del laboratorio 03. Este archivo va en ../datos/\
"GRFS-20261003.zip" - del 3 de octuvre de 2026. Este archivo va en ../datos/gtfs/ y se DEBE descomprimir ahi (los archivos .txt deben quedar en esa misma carpeta)\
\
El archivo ejecutar_todo.py es el archivo que inicia el proceso de la tarea\
Para ejecutar el archivo, en consola escribir "python3 ejecutar_todo.py". El docker compose se inicia en este mismo script (debe esta Docker corriendo).
