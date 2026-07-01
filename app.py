import streamlit as st
import osmnx as ox
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium

# --- CONFIGURATION & INITIALISATION ---
if "commune_validee" not in st.session_state:
    st.session_state.commune_validee = "Turenne"

ox.settings.timeout = 180  
ox.settings.use_cache = True

st.set_page_config(page_title="Radar de Patrimoine Isolé", layout="wide")
st.title("🗺️ Détecteur de Vestiges & Patrimoine Isolé")

# --- FONCTIONS ---
@st.cache_data(show_spinner="Extraction des données (10km)...")
def charger_tous_vestiges_osm(commune):
    tags = {"historic": ["ruins", "castle", "fortress", "archaeological_site", "monument", "memorial"]}
    try:
        gdf = ox.features_from_address(commune, tags=tags, dist=10000)
        if gdf.empty: return None
        gdf['geometry'] = gdf.geometry.centroid
        return gdf[['geometry', 'historic', 'name', 'note', 'description']]
    except Exception as e:
        st.error(f"Erreur lors de l'extraction : {e}")
        return None

# --- SIDEBAR (SANS FORMULAIRE POUR PLUS DE RÉACTIVITÉ) ---
st.sidebar.header("1. Zone géographique")
nom_commune = st.sidebar.text_input("Nom de la commune :", value=st.session_state.commune_validee)

# Bouton simple : déclenche le recalcul immédiat
if st.sidebar.button("Lancer le scan 🚀"):
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
        
        # Organisation : Carte en haut, Tableau en bas
        zone_carte = st.empty()
        st.markdown("---")
        st.subheader("📋 Données détaillées")
        
        evenement_clic = st.dataframe(df_affichage, selection_mode="single-row", on_select="rerun", use_container_width=True)
        
        center = [gdf_final.geometry.y.mean(), gdf_final.geometry.x.mean()]
        zoom = 12
        id_sel = None
        
        if evenement_clic and evenement_clic.selection.rows:
            sel = gdf_final.iloc[evenement_clic.selection.rows[0]]
            center = [sel.geometry.y, sel.geometry.x]
            zoom = 16
            id_sel = sel.name
            
        with zone_carte.container():
            st.subheader(f"📍 {len(gdf_final)} élément(s) trouvé(s)")
            m = folium.Map(location=center, zoom_start=zoom)
            folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri').add_to(m)
            for idx, row in gdf_final.iterrows():
                is_sel = (idx == id_sel)
                folium.Marker([row.geometry.y, row.geometry.x], 
                             icon=folium.Icon(color="green" if is_sel else "red", icon="star" if is_sel else "landmark", prefix="fa")).add_to(m)
            st_folium(m, width=None, height=650)
    else:
        st.warning("Aucun résultat pour cette sélection.")
else:
    st.info("Entrez une commune et cliquez sur Scan.")
