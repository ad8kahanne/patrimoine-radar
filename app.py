import streamlit as st
import osmnx as ox
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- INITIALISATION SÉCURISÉE (C'est ce qui manquait) ---
if "commune_validee" not in st.session_state:
    st.session_state.commune_validee = "Turenne"

# Configuration des limites de l'API Overpass
ox.settings.timeout = 180  
ox.settings.use_cache = True

st.set_page_config(page_title="Radar de Patrimoine Isolé", layout="wide")
st.title("🗺️ Détecteur de Vestiges & Patrimoine Isolé")

# --- FONCTIONS ---
@st.cache_data(show_spinner="Extraction des données...")
def charger_tous_vestiges_osm(commune):
    tags = {"historic": ["ruins", "castle", "fortress", "archaeological_site", "monument", "memorial"]}
    try:
        gdf = ox.features_from_address(commune, tags=tags, dist=10000)
        if gdf.empty: return None
        gdf['geometry'] = gdf.geometry.centroid
        return gdf[['geometry', 'historic', 'name', 'note', 'description']]
    except: return None

@st.cache_data(show_spinner="Analyse des bâtiments...")
def charger_batiments_osm(commune):
    try:
        gdf = ox.features_from_address(commune, tags={"building": True}, dist=10000)
        return gdf[['geometry']] if not gdf.empty else None
    except: return None

# --- SIDEBAR ---
st.sidebar.header("1. Zone géographique")
with st.sidebar.form("form_commune"):
    nom_commune = st.text_input("Nom de la commune :", value=st.session_state.commune_validee)
    if st.form_submit_button("Lancer le scan 🚀"):
        st.session_state.commune_validee = nom_commune
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("2. Filtres")
rayon_isolement = st.sidebar.slider("Rayon d'isolement (m) :", 0, 2000, 300, 50)
choix_ruines = st.sidebar.checkbox("Ruines", True)
choix_chateaux = st.sidebar.checkbox("Châteaux", True)
choix_archeo = st.sidebar.checkbox("Archéo", True)
choix_monuments = st.sidebar.checkbox("Monuments", False)

# --- TRAITEMENT ---
gdf_brut = charger_tous_vestiges_osm(st.session_state.commune_validee)

if gdf_brut is not None:
    tags_actifs = []
    if choix_ruines: tags_actifs.append("ruins")
    if choix_chateaux: tags_actifs.extend(["castle", "fortress"])
    if choix_archeo: tags_actifs.append("archaeological_site")
    if choix_monuments: tags_actifs.extend(["monument", "memorial"])
    
    gdf_final = gdf_brut[gdf_brut['historic'].isin(tags_actifs)]
    
    if not gdf_final.empty:
        df_affichage = pd.DataFrame(gdf_final.drop(columns='geometry'))
        zone_carte = st.empty()
        st.markdown("---")
        st.subheader("📋 Résultats")
        
        evenement_clic = st.dataframe(df_affichage, selection_mode="single-row", on_select="rerun", use_container_width=True)
        
        # Logique de centrage carte
        center = [gdf_final.geometry.y.mean(), gdf_final.geometry.x.mean()]
        zoom = 12
        id_sel = None
        
        if evenement_clic and evenement_clic.selection.rows:
            sel = gdf_final.iloc[evenement_clic.selection.rows[0]]
            center = [sel.geometry.y, sel.geometry.x]
            zoom = 16
            id_sel = sel.name
            
        with zone_carte.container():
            m = folium.Map(location=center, zoom_start=zoom)
            folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri').add_to(m)
            for idx, row in gdf_final.iterrows():
                is_sel = (idx == id_sel)
                folium.Marker([row.geometry.y, row.geometry.x], 
                             icon=folium.Icon(color="green" if is_sel else "red", icon="star" if is_sel else "landmark", prefix="fa")).add_to(m)
            st_folium(m, width=None, height=650)
    else:
        st.warning("Aucun résultat.")
else:
    st.info("Entrez une commune et cliquez sur Scan.")
