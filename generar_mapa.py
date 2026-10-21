import geopandas as gpd
import matplotlib.pyplot as plt
from sqlalchemy import create_engine

# Conexión a PostGIS
engine = create_engine("postgresql://postgres:postgrespassword@localhost:5432/santiago_centro")

print("Leyendo la grilla hexagonal desde PostGIS...")
query = """
    SELECT cell_geom AS geometry, total_edificios, total_recorridos
    FROM grilla_transporte_edificios
"""
gdf = gpd.read_postgis(query, con=engine, geom_col="geometry")

# --- MAPA 1: Edificios ---
print("Generando mapa de edificios...")
fig, ax = plt.subplots(1, 1, figsize=(10, 10))
gdf.plot(
    column="total_edificios",
    cmap="YlOrRd",
    legend=True,
    edgecolor="black",
    linewidth=0.1,
    ax=ax,
    legend_kwds={"label": "Total de Edificios por Hexágono", "orientation": "horizontal"}
)
ax.set_title("Distribución de Edificios - Santiago Centro (Grilla 500m)", fontsize=14)
ax.axis("off")
plt.savefig("mapa_grilla_edificios.png", dpi=300, bbox_inches="tight")
plt.close()
print("   → Guardado: mapa_grilla_edificios.png")

# --- MAPA 2: Recorridos de Transporte ---
print("Generando mapa de recorridos de transporte...")
fig, ax = plt.subplots(1, 1, figsize=(10, 10))
gdf.plot(
    column="total_recorridos",
    cmap="Blues",
    legend=True,
    edgecolor="black",
    linewidth=0.1,
    ax=ax,
    legend_kwds={"label": "Total de Recorridos por Hexágono", "orientation": "horizontal"}
)
ax.set_title("Cobertura de Transporte Público - Santiago Centro (Grilla 500m)", fontsize=14)
ax.axis("off")
plt.savefig("mapa_grilla_transporte.png", dpi=300, bbox_inches="tight")
plt.close()
print("   → Guardado: mapa_grilla_transporte.png")

print("🎉 ¡Mapas generados con éxito!")