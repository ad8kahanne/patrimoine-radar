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

# Initialisation de la commune par défaut dans l'état de la session
if "commune_validee" not in st.session_state:
    st.session_state.commune_validee = "Turenne"

# --- BARRE LATÉRALE ---

st.sidebar.header("1. Zone géographique")
# Le formulaire ne contient PLUS QUE la commune pour éviter les requêtes API intempestives
with st.sidebar.form("formulaire_commune"):
    nom_commune = st.text_input(
        "Nom de la commune :", 
        value=st.session_state.commune_validee
    )
    bouton_scan = st.form_submit_button("Lancer le scan 🚀")
    if bouton_scan:
        st.session_state.commune_validee = nom_commune

st.sidebar.markdown("---")
st.sidebar.header("2. Filtres d'affichage en temps réel")

# Placer ces éléments HORS du formulaire permet une réactivité instantanée sur la carte
rayon_isolement = st.sidebar.slider(
    "Rayon d'isolement minimum (mètres) :",
    min_value=0,
    max_value=2000,
    value=300,
    step=50,
    help="Distance minimale par rapport à un bâtiment moderne. À 0, le filtre est désactivé."
)

st.sidebar.write("**Types de vestiges à afficher :**")
choix_ruines = st.sidebar.checkbox("Ruines (ruins)", value=True)
choix_chateaux = st.sidebar.checkbox("Châteaux & Forteresses (castle, fortress)", value=True)
choix_archeo = st.sidebar.checkbox("Sites archéologiques (archaeological_site)", value=True)
choix_monuments = st.sidebar.checkbox("Monuments & Mémoriaux (monument, memorial)", value=False)


# --- FONCTIONS D'EXTRACTION (TÉLÉCHARGEMENT GLOBAL CACHÉ) ---

@st.cache_data(show_spinner="Extraction de l'ensemble des données historiques (10km)...")
def charger_tous_vestiges_osm(commune):
    # On télécharge toutes les catégories d'un coup pour pouvoir basculer de l'une à l'autre instantanément
    toutes_categories = ["ruins", "castle", "fortress", "archaeological_site", "monument", "memorial"]
    tags = {"historic": toutes_categories}
    try:
        gdf = ox.features_from_address(commune, tags=tags, dist=10000)
        if gdf.empty:
            return None
        
        # Transformation des polygones en points centraux
        gdf_points = gdf.copy()
        gdf_points['geometry'] = gdf_points.geometry.centroid
        
        colonnes_cibles = ['geometry', 'historic', 'name', 'note', 'description']
        colonnes_existantes = [col for col in colonnes_cibles if col in gdf_points.columns]
        return gdf_points[colonnes_existantes]
    except Exception:
        return None

@st.cache_data(show_spinner="Analyse des structures modernes environnantes...")
def charger_batiments_osm(commune):
    tags = {"building": True}
    try:
        gdf = ox.features_from_address(commune, tags=tags, dist=10000)
        if gdf.empty:
            return None
        return gdf[['geometry']]
    except Exception:
        return None


# --- TRAITEMENT ET FILTRAGE LOCAL ---

if st.session_state.commune_validee:
    # 1. Récupération brute de la base de données OSM indexée pour cette commune
    gdf_brut = charger_tous_vestiges_osm(st.session_state.commune_validee)
    
    if gdf_brut is not None and not gdf_brut.empty:
        
        # 2. Filtrage par type (Calcul local instantané basé sur les cases à cocher)
        tags_actifs = []
        if choix_ruines: tags_actifs.append("ruins")
        if choix_chateaux: tags_actifs.extend(["castle", "fortress"])
        if choix_archeo: tags_actifs.append("archaeological_site")
        if choix_monuments: tags_actifs.extend(["monument", "memorial"])
        
        gdf_filtre_type = gdf_brut[gdf_brut['historic'].isin(tags_actifs)]
        
        if not gdf_filtre_type.empty:
            utm_crs = gdf_filtre_type.estimate_utm_crs()
            gdf_proj = gdf_filtre_type.to_crs(utm_crs)
            
            # 3. Filtrage par isolement spatial (si supérieur à 0)
            if rayon_isolement > 0:
                gdf_batiments = charger_batiments_osm(st.session_state.commune_validee)
                
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

                    mask_isole = gdf_proj.geometry.apply(
                        lambda pt: verifier_isolement(pt, sindex_bats, gdf_batiments_proj, rayon_isolement)
                    )
                    gdf_filtre_spatial_proj = gdf_proj[mask_isole]
                else:
                    gdf_filtre_spatial_proj = gdf_proj
            else:
                gdf_filtre_spatial_proj = gdf_proj
            
            # Reprojection finale en coordonnées géographiques standards
            gdf_final = gdf_filtre_spatial_proj.to_crs(epsg=4326)
            
            # --- GESTION DE LA SÉLECTION DANS LE TABLEAU ---
            df_affichage = pd.DataFrame(gdf_final.drop(columns='geometry'))
            
            # Coordonnées d'affichage par défaut (centre moyen des points trouvés)
            if not gdf_final.empty:
                center_y = gdf_final.geometry.y.mean()
                center_x = gdf_final.geometry.x.mean()
                zoom_carte = 12
            else:
                center_y, center_x, zoom_carte = 46.0, 2.0, 6
                
            id_selectionne = None
            
            # Pour conserver la carte en haut et le tableau en bas dans l'ordre visuel tout en capturant 
            # la sélection du tableau avant le rendu de la carte, on utilise des placeholders st.empty()
            zone_carte = st.empty()
            st.markdown("---")
            st.subheader("📋 Données détaillées des résultats")
            
            # Affichage du tableau interactif avec écoute du clic de ligne
            evenement_clic = st.dataframe(
                df_affichage, 
                selection_mode="single_row", 
                on_select="rerun", 
                use_container_width=True
            )
            
            # Analyse de la ligne sélectionnée pour modifier la carte en conséquence
            if evenement_clic and evenement_clic.selection.rows:
                index_ligne_selectionnee = evenement_clic.selection.rows[0]
                entite_cible = gdf_final.iloc[index_ligne_selectionnee]
                center_y = entite_cible.geometry.y
                center_x = entite_cible.geometry.x
                zoom_carte = 16  # Zoom ciblé puissant sur l'élément sélectionné
                id_selectionne = entite_cible.name  # Stockage de l'ID OSM de la ligne

            # --- RENDU DE LA CARTE (DANS LA ZONE DU HAUT) ---
            with zone_carte.container():
                st.subheader(f"📍 {len(gdf_final)} élément(s) historique(s) repéré(s)")
                
                if not gdf_final.empty:
                    m = folium.Map(location=[center_y, center_x], zoom_start=zoom_carte)
                    
                    # Fond satellite Esri
                    folium.TileLayer(
                        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                        attr='Esri World Imagery',
                        name='Vue Satellite',
                        overlay=False
                    ).add_to(m)
                    folium.LayerControl().add_to(m)
                    
                    # Génération dynamique des marqueurs
                    for idx, row in gdf_final.iterrows():
                        nom = row['name'] if ('name' in row and pd.notna(row['name'])) else "Patrimoine non nommé"
                        type_h = row['historic'] if ('historic' in row and pd.notna(row['historic'])) else "Indéterminé"
                        popup_html = f"<b>{nom}</b><br>Type : {type_h}"
                        
                        # Changement d'aspect visuel si la ligne du tableau correspond à ce point precise
                        ligne_cliquee = (idx == id_selectionne)
                        couleur_marqueur = "green" if ligne_cliquee else "red"
                        icone_style = "star" if ligne_cliquee else "landmark"
                        
                        folium.Marker(
                            location=[row.geometry.y, row.geometry.x],
                            popup=folium.Popup(popup_html, max_width=250),
                            icon=folium.Icon(color=couleur_marqueur, icon=icone_style, prefix="fa")
                        ).add_to(m)
                        
                        if rayon_isolement > 0:
                            folium.Circle(
                                location=[row.geometry.y, row.geometry.x],
                                radius=rayon_isolement,
                                color="#28a745" if ligne_cliquee else "#1f77b4",
                                fill=True,
                                fill_opacity=0.08 if ligne_cliquee else 0.04,
                                weight=2 if ligne_cliquee else 1
                            ).add_to(m)
                    
                    st_folium(m, width=None, height=650, returned_objects=[])
                else:
                    st.warning("Aucun élément ne correspond aux filtres ou à la distance d'isolement.")
        else:
            st.warning("Aucun résultat ne correspond aux catégories cochées.")
    else:
        st.error("Aucune donnée disponible. Lancez le scan initial via le bouton dédié.")
