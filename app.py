import streamlit as pd
import streamlit as st
import osmnx as ox
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium

# Configuration des limites de l'API Overpass
ox.settings.timeout = 180  
ox.settings.use_cache = True

st.set_page_config(page_title="Radar de Patrimoine Isolé", layout="wide")

st.title("🗺️ Détecteur de Vestiges & Patrimoine Isolé")

# Initialisation des variables d'état pour éviter que la carte disparaisse lors des interactions
if "scan_lance" not in st.session_state:
    st.session_state.scan_lance = False

# --- BARRE LATÉRALE : FORMULAIRE DE RECHERCHE ---
with st.sidebar.form("formulaire_recherche"):
    st.header("Paramètres")
    
    nom_commune = st.text_input(
        "Nom de la commune (avec pays) :", 
        value="Turenne, Corrèze, France"
    )
    
    rayon_isolement = st.slider(
        "Rayon d'isolement minimum (mètres) :",
        min_value=0,
        max_value=2000,
        value=300,
        step=50
    )
    
    st.markdown("---")
    st.write("**Types de recherche (historic=*) :**")
    
    # Restauration des cases à cocher d'origine
    choix_ruines = st.checkbox("Ruines (ruins)", value=True)
    choix_chateaux = st.checkbox("Châteaux & Forteresses (castle, fortress)", value=True)
    choix_archeo = st.checkbox("Sites archéologiques (archaeological_site)", value=True)
    choix_monuments = st.checkbox("Monuments & Mémoriaux (monument, memorial)", value=False)
    
    # Bouton de lancement manuel
    bouton_scan = st.form_submit_button("Lancer le scan 🚀")

# Enregistrement des paramètres lors du clic sur le bouton
if bouton_scan:
    st.session_state.nom_commune = nom_commune
    st.session_state.rayon_isolement = rayon_isolement
    st.session_state.choix_ruines = choix_ruines
    st.session_state.choix_chateaux = choix_chateaux
    st.session_state.choix_archeo = choix_archeo
    st.session_state.choix_monuments = choix_monuments
    st.session_state.scan_lance = True

# --- FONCTIONS D'EXTRACTION ---
@st.cache_data(show_spinner="Extraction des données historiques...")
def charger_vestiges(commune, tags_selectionnes):
    if not tags_selectionnes:
        return None
    tags = {"historic": tags_selectionnes}
    try:
        gdf = ox.features_from_place(commune, tags=tags)
        if gdf.empty:
            return None
        
        # Maintien de la correction géométrique (Point + Polygones via Centroïde)
        gdf_points = gdf.copy()
        gdf_points['geometry'] = gdf_points.geometry.centroid
        
        colonnes_cibles = ['geometry', 'historic', 'name', 'note', 'description']
        colonnes_existantes = [col for col in colonnes_cibles if col in gdf_points.columns]
        return gdf_points[colonnes_existantes]
    except Exception as e:
        return None

@st.cache_data(show_spinner="Analyse des structures modernes de proximité...")
def charger_batiments_modernes(commune):
    tags = {"building": True}
    try:
        gdf = ox.features_from_place(commune, tags=tags)
        if gdf.empty:
            return None
        return gdf[['geometry']]
    except Exception as e:
        return None

# --- EXÉCUTION DU TRAITEMENT ---
if st.session_state.scan_lance:
    
    # Construction de la liste des filtres OSM selon les cases cochées
    tags_osm = []
    if st.session_state.choix_ruines: tags_osm.append("ruins")
    if st.session_state.choix_chateaux: tags_osm.extend(["castle", "fortress"])
    if st.session_state.choix_archeo: tags_osm.append("archaeological_site")
    if st.session_state.choix_monuments: tags_osm.extend(["monument", "memorial"])
    
    if not tags_osm:
        st.error("Désolé, tu dois cocher au moins un type de recherche dans la barre de gauche pour lancer le scan.")
    else:
        gdf_vestiges = charger_vestiges(st.session_state.nom_commune, tags_osm)
        
        if gdf_vestiges is not None and not gdf_vestiges.empty:
            utm_crs = gdf_vestiges.estimate_utm_crs()
            gdf_vestiges_proj = gdf_vestiges.to_crs(utm_crs)
            
            # Application du filtre d'isolement (uniquement si le rayon est supérieur à 0)
            if st.session_state.rayon_isolement > 0:
                gdf_batiments = charger_batiments_modernes(st.session_state.nom_commune)
                
                if gdf_batiments is not None and not gdf_batiments.empty:
                    gdf_batiments_proj = gdf_batiments.to_crs(utm_crs)
                    sindex_bats = gdf_batiments_proj.sindex
                    
                    def verifier_isolement(point, index, gdf_bats, rayon):
                        bbox = point.buffer(rayon)
                        match_idx = index.query(bbox, predicate="intersects")
                        if len(match_idx) == 0:
                            return True
                        candidats = gdf_bats.iloc[match_idx]
                        return candidats.distance(point).min() >= rayon

                    mask_isole = gdf_vestiges_proj.geometry.apply(
                        lambda pt: verifier_isolement(pt, sindex_bats, gdf_batiments_proj, st.session_state.rayon_isolement)
                    )
                    gdf_filtre_proj = gdf_vestiges_proj[mask_isole]
                else:
                    gdf_filtre_proj = gdf_vestiges_proj
            else:
                # Si le rayon est à 0, on bypass le chargement des bâtiments modernes (vitesse maximale)
                gdf_filtre_proj = gdf_vestiges_proj
            
            gdf_final = gdf_filtre_proj.to_crs(epsg=4326)
            
            # --- AFFICHAGE DES RÉSULTATS ---
            st.subheader(f"📍 {len(gdf_final)} élément(s) correspondant à tes critères")
            
            if not gdf_final.empty:
                center_y = gdf_final.geometry.y.mean()
                center_x = gdf_final.geometry.x.mean()
                
                m = folium.Map(location=[center_y, center_x], zoom_start=13)
                
                # Couche satellite Esri
                folium.TileLayer(
                    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                    attr='Esri World Imagery',
                    name='Vue Satellite',
                    overlay=False
                ).add_to(m)
                folium.LayerControl().add_to(m)
                
                # Placement des marqueurs de vestiges
                for idx, row in gdf_final.iterrows():
                    nom = row['name'] if ('name' in row and pd.notna(row['name'])) else "Patrimoine non nommé"
                    type_h = row['historic'] if ('historic' in row and pd.notna(row['historic'])) else "Indéterminé"
                    
                    popup_html = f"<b>{nom}</b><br>Type : {type_h}"
                    
                    folium.Marker(
                        location=[row.geometry.y, row.geometry.x],
                        popup=folium.Popup(popup_html, max_width=250),
                        icon=folium.Icon(color="red", icon="landmark", prefix="fa")
                    ).add_to(m)
                    
                    # Dessin du cercle de tolérance (Masqué si rayon à 0)
                    if st.session_state.rayon_isolement > 0:
                        folium.Circle(
                            location=[row.geometry.y, row.geometry.x],
                            radius=st.session_state.rayon_isolement,
                            color="#1f77b4",
                            fill=True,
                            fill_opacity=0.05,
                            weight=1
                        ).add_to(m)
                
                st_folium(m, width=None, height=600, returned_objects=[])
                
                # Conservation de la liste tabulaire en bas que tu as validée
                st.markdown("---")
                st.subheader("📋 Liste détaillée des vestiges détectés")
                df_affichage = pd.DataFrame(gdf_final.drop(columns='geometry'))
                st.dataframe(df_affichage, use_container_width=True)
            else:
                st.warning("Aucun élément ne correspond à ce niveau d'isolement. Diminue le rayon en mètres.")
        else:
            st.error("Aucune donnée trouvée pour cette recherche ou cette commune. Vérifie l'orthographe ou les cases cochées.")
