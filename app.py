import streamlit as st
import osmnx as ox
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- CONFIGURATION INITIALE ---
if "commune_validee" not in st.session_state: st.session_state.commune_validee = "Turenne"
if "map_center" not in st.session_state: st.session_state.map_center = [45.0, 1.5]
if "map_zoom" not in st.session_state: st.session_state.map_zoom = 12
if "layer_type" not in st.session_state: st.session_state.layer_type = "Satellite"

ox.settings.timeout = 180  
ox.settings.use_cache = True

st.set_page_config(page_title="Radar de Patrimoine", layout="wide")
st.title("🗺️ Détecteur de Vestiges & Patrimoine Isolé")

st.session_state.layer_type = st.radio(
    "Choisir la vue :", ["Satellite", "Carte", "Cadastre"], 
    index=["Satellite", "Carte", "Cadastre"].index(st.session_state.layer_type),
    horizontal=True
)

@st.cache_data(show_spinner="Extraction...")
def charger_donnees(commune):
    tags = {"historic": ["ruins", "castle", "fortress", "archaeological_site", "monument", "memorial"]}
    try:
        gdf = ox.features_from_address(commune, tags=tags, dist=10000)
        if gdf.empty: return None
        gdf['geometry'] = gdf.geometry.centroid
        cols = [c for c in ['geometry', 'historic', 'name', 'note', 'description'] if c in gdf.columns]
        return gdf[cols]
    except: return None

nom_commune = st.sidebar.text_input("Commune :", value=st.session_state.commune_validee)
if st.sidebar.button("Lancer le scan 🚀"):
    st.session_state.commune_validee = nom_commune
    st.rerun()

gdf_brut = charger_donnees(st.session_state.commune_validee)

if gdf_brut is not None:
    # Création du conteneur fixe pour la carte
    carte_container = st.container()
    
    # Logique de tuiles
    if st.session_state.layer_type == "Satellite":
        tiles, attr = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', 'Esri'
    elif st.session_state.layer_type == "Cadastre":
        tiles, attr = 'https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=CADASTRALPARCELS.PARCELLAIRE_EXPRESS&STYLE=normal&FORMAT=image/png&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}', 'IGN'
    else:
        tiles, attr = 'openstreetmap', 'OpenStreetMap'
    
    m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom, tiles=tiles, attr=attr)
    
    for idx, row in gdf_brut.iterrows():
        folium.Marker([row.geometry.y, row.geometry.x], 
                      popup=folium.Popup(f"<b>{row.get('name', 'Vestige')}</b>", max_width=200),
                      icon=folium.Icon(color="red", icon="landmark", prefix="fa")).add_to(m)
    
    with carte_container:
        output = st_folium(m, width=None, height=500, returned_objects=["center", "zoom"])
        
    # Mise à jour silencieuse
    if output and output.get("center"):
        st.session_state.map_center = [output["center"]["lat"], output["center"]["lng"]]
        st.session_state.map_zoom = output["zoom"]
    
    st.markdown("---")
    st.subheader("📋 Résultats")
    evenement = st.dataframe(pd.DataFrame(gdf_brut.drop(columns='geometry')), selection_mode="single-row", on_select="rerun", use_container_width=True)
    
    if evenement and evenement.selection.rows:
        sel = gdf_brut.iloc[evenement.selection.rows[0]]
        st.session_state.map_center = [sel.geometry.y, sel.geometry.x]
        st.session_state.map_zoom = 16
        st.rerun()
else:
    st.info("Entrez une commune et cliquez sur Scan.")
