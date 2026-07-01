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

# --- FONCTIONS ---
@st.cache_data(show_spinner="Extraction en cours...")
def charger_donnees(commune):
    tags = {"historic": ["ruins", "castle", "fortress", "archaeological_site", "monument", "memorial"]}
    try:
        gdf = ox.features_from_address(commune, tags=tags, dist=10000)
        if gdf.empty: return None
        gdf['geometry'] = gdf.geometry.centroid
        cols = [c for c in ['geometry', 'historic', 'name', 'note', 'description'] if c in gdf.columns]
        return gdf[cols]
    except: return None

# --- SIDEBAR ---
nom_commune = st.sidebar.text_input("Commune :", value=st.session_state.commune_validee)
if st.sidebar.button("Lancer le scan 🚀"):
    st.session_state.commune_validee = nom_commune
    st.rerun()

rayon = st.sidebar.slider("Rayon d'isolement (m) :", 0, 2000, 300, 50)
c_ruines = st.sidebar.checkbox("Ruines", True)
c_chateaux = st.sidebar.checkbox("Châteaux", True)
c_archeo = st.sidebar.checkbox("Archéo", True)
c_monu = st.sidebar.checkbox("Monuments", False)

# --- TRAITEMENT ---
gdf_brut = charger_donnees(st.session_state.commune_validee)

if gdf_brut is not None:
    tags_sel = []
    if c_ruines: tags_sel.append("ruins")
    if c_chateaux: tags_sel.extend(["castle", "fortress"])
    if c_archeo: tags_sel.append("archaeological_site")
    if c_monu: tags_sel.extend(["monument", "memorial"])
    
    gdf_final = gdf_brut[gdf_brut['historic'].isin(tags_sel)]
    
    if not gdf_final.empty:
        # Contrôle permanent du type de vue
        st.session_state.layer_type = st.radio("Type de vue :", ["Satellite", "Carte"], horizontal=True)
        
        if st.session_state.map_center == [45.0, 1.5]:
            st.session_state.map_center = [gdf_final.geometry.y.mean(), gdf_final.geometry.x.mean()]
            
        # Définition des tuiles basées sur le choix radio
        tiles = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}' if st.session_state.layer_type == "Satellite" else 'openstreetmap'
        attr = 'Esri World Imagery' if st.session_state.layer_type == "Satellite" else 'OpenStreetMap'
        
        m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom, tiles=tiles, attr=attr)
        
        for idx, row in gdf_final.iterrows():
            folium.Marker([row.geometry.y, row.geometry.x], icon=folium.Icon(color="red", icon="landmark", prefix="fa")).add_to(m)
        
        st_folium(m, width=None, height=500)
        
        st.markdown("---")
        st.subheader("📋 Résultats")
        df_display = pd.DataFrame(gdf_final.drop(columns='geometry'))
        
        evenement = st.dataframe(df_display, selection_mode="single-row", on_select="rerun", use_container_width=True)
        
        if evenement and evenement.selection.rows:
            sel = gdf_final.iloc[evenement.selection.rows[0]]
            st.session_state.map_center = [sel.geometry.y, sel.geometry.x]
            st.session_state.map_zoom = 16
            st.rerun()
            
    else:
        st.warning("Aucun résultat.")
else:
    st.info("Entrez une commune et cliquez sur Scan.")
