import streamlit as st
import osmnx as ox
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium

# 1. Configuration des limites de l'API Overpass (Évite les coupures de serveur)
ox.settings.timeout = 180  
ox.settings.use_cache = True

st.set_page_config(page_title="Radar de Patrimoine Isolé", layout="wide")

st.title("🗺️ Détecteur de Vestiges & Patrimoine Isolé")
st.markdown("""
Cet outil extrait l'intégralité des données historiques d'**OpenStreetMap** et isole les résultats selon leur distance par rapport aux habitations modernes.
""")

# 2. Panneau de configuration (Sidebar)
st.sidebar.header("Paramètres de recherche")

nom_commune = st.sidebar.text_input(
    "Nom de la commune (avec pays) :", 
    value="Turenne, Corrèze, France",
    help="Soyez précis pour aider le géocodage (ex: Turenne, Corrèze, France)"
)

rayon_isolement = st.sidebar.slider(
    "Rayon d'isolement minimum (mètres) :",
    min_value=0,
    max_value=2000,
    value=300,
    step=50,
    help="Distance minimale par rapport à un bâtiment. Si mis à 0, le filtre est désactivé et 100% des vestiges s'affichent."
)

# 3. Fonctions d'extraction optimisées avec cache Streamlit
@st.cache_data(show_spinner="Extraction de la totalité du patrimoine historique (Points & Formes)...")
def charger_tous_vestiges(commune):
    # Capture absolue pour maximiser les découvertes : "True" prend TOUTES les sous-catégories
    tags = {
        "historic": True, 
        "ruins": True,
        "abandoned": True
    }
    try:
        gdf = ox.features_from_place(commune, tags=tags)
        if gdf.empty:
            return None
        
        # CORRECTION "Il ne trouve pas tout" : Conversion systématique en Centroïde.
        # Cela permet de traiter au même niveau les simples repères (Points) et les tracés de vieux murs (Polygones)
        gdf_points = gdf.copy()
        gdf_points['geometry'] = gdf_points.geometry.centroid
        
        # Tri et nettoyage des colonnes pour la base de données finale
        colonnes_cibles = ['geometry', 'historic', 'name', 'description', 'ruins', 'abandoned']
        colonnes_existantes = [col for col in colonnes_cibles if col in gdf_points.columns]
        
        return gdf_points[colonnes_existantes]
    except Exception as e:
        st.sidebar.error(f"Erreur d'extraction OSM : {e}")
        return None

@st.cache_data(show_spinner="Cartographie des zones urbaines et bâtiments...")
def charger_batiments_modernes(commune):
    tags = {"building": True}
    try:
        gdf = ox.features_from_place(commune, tags=tags)
        if gdf.empty:
            return None
        return gdf[['geometry']]
    except Exception as e:
        return None

# 4. Traitement et filtrage spatial
if nom_commune:
    gdf_vestiges = charger_tous_vestiges(nom_commune)
    
    if gdf_vestiges is not None and not gdf_vestiges.empty:
        # Projection automatique dans le système métrique local (UTM) pour des calculs en mètres réels
        utm_crs = gdf_vestiges.estimate_utm_crs()
        gdf_vestiges_proj = gdf_vestiges.to_crs(utm_crs)
        
        # CORRECTION "Rayon à zéro" 
        if rayon_isolement > 0:
            gdf_batiments = charger_batiments_modernes(nom_commune)
            
            if gdf_batiments is not None and not gdf_batiments.empty:
                gdf_batiments_proj = gdf_batiments.to_crs(utm_crs)
                
                # Indexation spatiale (R-Tree) pour un calcul de distance ultra-rapide
                sindex_bats = gdf_batiments_proj.sindex
                
                def verifier_isolement(point, index, gdf_bats, rayon):
                    bbox = point.buffer(rayon)
                    match_idx = index.query(bbox, predicate="intersects")
                    if len(match_idx) == 0:
                        return True # Aucun bâtiment dans la zone limitrophe bounding box
                    
                    # Si intersection potentielle détectée, calcul de la distance exacte au plus proche
                    candidats = gdf_bats.iloc[match_idx]
                    return candidats.distance(point).min() >= rayon

                mask_isole = gdf_vestiges_proj.geometry.apply(
                    lambda pt: verifier_isolement(pt, sindex_bats, gdf_batiments_proj, rayon_isolement)
                )
                gdf_filtre_proj = gdf_vestiges_proj[mask_isole]
            else:
                st.info("Aucun bâtiment moderne détecté sur la zone pour appliquer le filtre d'isolement.")
                gdf_filtre_proj = gdf_vestiges_proj
        else:
            # Si le rayon == 0 : court-circuit complet. On ignore l'extraction des bâtiments (Gain de temps et de RAM)
            gdf_filtre_proj = gdf_vestiges_proj
        
        # Re-projection au standard GPS (WGS84) pour l'affichage de la carte Folium
        gdf_final = gdf_filtre_proj.to_crs(epsg=4326)
        
        # 5. Rendu de l'interface et affichages des résultats
        st.subheader(f"📍 {len(gdf_final)} élément(s) archéologique(s) ou historique(s) identifié(s)")
        
        if not gdf_final.empty:
            # Recentrage automatique de la carte
            center_y = gdf_final.geometry.y.mean()
            center_x = gdf_final.geometry.x.mean()
            
            m = folium.Map(location=[center_y, center_x], zoom_start=13, tiles="OpenStreetMap")
            
            # Ajout du fond de carte Satellite (Essentiel pour voir les structures cachées dans les bois)
            folium.TileLayer(
                tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                attr='Esri World Imagery',
                name='Vue Satellite (Esri)',
                overlay=False
            ).add_to(m)
            folium.LayerControl().add_to(m)
            
            # Génération des marqueurs
            for idx, row in gdf_final.iterrows():
                nom = row['name'] if ('name' in row and pd.notna(row['name'])) else "Patrimoine / Ruine non nommée"
                type_h = row['historic'] if ('historic' in row and pd.notna(row['historic'])) else "Indéterminé"
                
                popup_html = f"""
                <div style='font-family: Arial, sans-serif; min-width: 200px;'>
                    <h4 style='margin:0 0 5px 0; color:#8B0000;'>{nom}</h4>
                    <b>Classification OSM :</b> {type_h}<br>
                </div>
                """
                
                folium.Marker(
                    location=[row.geometry.y, row.geometry.x],
                    popup=folium.Popup(popup_html, max_width=300),
                    icon=folium.Icon(color="red", icon="landmark", prefix="fa")
                ).add_to(m)
                
                # Tracé du cercle d'isolation visuel uniquement si le rayon est actif
                if rayon_isolement > 0:
                    folium.Circle(
                        location=[row.geometry.y, row.geometry.x],
                        radius=rayon_isolement,
                        color="#2A75D3",
                        fill=True,
                        fill_opacity=0.05,
                        weight=1
                    ).add_to(m)
            
            # Rendu de la carte
            st_folium(m, width=None, height=600, returned_objects=[])
            
            # Tableau brut des données en bas de page
            st.subheader("📋 Base de données des résultats")
            df_affichage = pd.DataFrame(gdf_final.drop(columns='geometry'))
            st.dataframe(df_affichage, use_container_width=True)
            
        else:
            st.warning("Aucun vestige n'est assez isolé pour correspondre à vos critères. Abaissez le curseur en mètres.")
    else:
        st.error("Aucune entité historique n'a pu être extraite pour cette localisation. Précisez le nom de la commune.")
