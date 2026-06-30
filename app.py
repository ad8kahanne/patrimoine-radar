
import streamlit as st
import osmnx as ox
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import pandas as pd
from sklearn.neighbors import NearestNeighbors
import warnings
import streamlit.components.v1 as components
import time

# --- CONFIGURATION & CACHE ---
warnings.filterwarnings("ignore")
st.set_page_config(page_title="PATRIMOINE RADAR", layout="wide")

ox.settings.use_cache = True
ox.settings.cache_folder = './cache'
ox.settings.log_console = False

# --- INITIALISATION ÉTATS ---
if 'favs' not in st.session_state:
    st.session_state.favs = {} 
if 'map_center' not in st.session_state:
    st.session_state.map_center = None
if 'last_res' not in st.session_state:
    st.session_state.last_res = None
if 'zoom_level' not in st.session_state:
    st.session_state.zoom_level = 13
if 'sync_idx' not in st.session_state:
    st.session_state.sync_idx = 0
if 'last_city' not in st.session_state:
    st.session_state.last_city = ""

# --- STYLE CSS ---
st.markdown("""
    <style>
    div.stButton > button:first-child { background-color: #8B4513; color: white; border-radius: 5px; font-weight: bold; }
    .stProgress > div > div > div > div { background-color: #8B4513; }
    </style>
""", unsafe_allow_html=True)

js_close_sidebar = "<script>parent.document.querySelector('button[kind=\"headerNoPadding\"]').click();</script>"

st.title("🏛️ Patrimoine & Ruines Radar")

# --- BARRE LATÉRALE ---
with st.sidebar:
    st.header("Paramètres du Détecteur")
    commune_in = st.text_input("Secteur de recherche :", placeholder="Commune...", key="city_input")
    
    st.subheader("Filtres de ciblage")
    inclure_ruines = st.checkbox("Ruines & Bâtiments écroulés", value=True)
    inclure_abandonne = st.checkbox("Bâtiments abandonnés / Vieux bâti", value=True)
    inclure_fontaines = st.checkbox("Fontaines, Sources & Puits", value=True)
    inclure_historic = st.checkbox("Monuments & Vestiges historiques", value=False)
    
    rayon_iso_val = st.slider("Rayon d'isolement du vestige (m) :", 10, 500, 100)
    
    lancer_scan = st.button("Lancer la recherche", use_container_width=True)
    
    st.markdown("---")
    st.subheader("⭐ Vestiges Sauvegardés")
    if st.session_state.last_res is not None:
        res_count = len(st.session_state.last_res)
        col_sel, col_add = st.columns([2, 1])
        with col_sel:
            st.session_state.sync_idx = st.selectbox(
                "Choisir #", 
                range(res_count), 
                index=min(st.session_state.sync_idx, res_count-1),
                format_func=lambda x: f"Site #{x+1}", 
                label_visibility="collapsed"
            )
        with col_add:
            if st.button("Ajouter"):
                row = st.session_state.last_res.iloc[st.session_state.sync_idx]
                st.session_state.favs[st.session_state.sync_idx+1] = (row.geometry.centroid.y, row.geometry.centroid.x)
    
    if st.session_state.favs:
        st.write("📍 Accès rapide :")
        cols_fav = st.columns(4)
        for i, (num, coords) in enumerate(sorted(st.session_state.favs.items())):
            if cols_fav[i % 4].button(f"#{num}", key=f"fbtn_{num}"):
                st.session_state.map_center = [coords[0], coords[1]]
                st.session_state.zoom_level = 18
                st.session_state.sync_idx = num - 1
                st.rerun()
        if st.button("Vider la sélection", use_container_width=True):
            st.session_state.favs = {}
            st.rerun()

# --- LOGIQUE DE SCAN ---
if lancer_scan:
    if not commune_in:
        st.error("⚠️ Entrez une commune pour démarrer.")
    elif not (inclure_ruines or inclure_abandonne or inclure_fontaines or inclure_historic):
        st.error("⚠️ Sélectionnez au moins un filtre de ciblage.")
    else:
        if commune_in.strip().lower() != st.session_state.last_city.strip().lower():
            st.session_state.favs = {}
            st.session_state.sync_idx = 0
            st.session_state.last_res = None
            
        components.html(js_close_sidebar, height=0, width=0)
        try:
            st.session_state.last_city = commune_in
            
            with st.status("Scan du patrimoine en cours...", expanded=True) as status:
                p_bar = st.progress(0, text="Interrogation du cadastre et des bases historiques...")
                
                # Étape 1 : Géocodage
                base = ox.geocode_to_gdf(commune_in)
                for percent in range(1, 26):
                    time.sleep(0.01)
                    p_bar.progress(percent, text=f"Définition des limites administratives : {percent}%")
                
                # Étape 2 : Zone d'étude
                geom_c = base.geometry.iloc[0]
                voisines = ox.features_from_polygon(geom_c.buffer(0.015), tags={'admin_level': '8'})
                secteur = pd.concat([base, voisines[voisines.geometry.intersects(geom_c)]]).to_crs(epsg=2154)
                union_zone = secteur.geometry.union_all()
                
                for percent in range(26, 51):
                    time.sleep(0.01)
                    p_bar.progress(percent, text=f"Calcul de la zone d'analyse topographique : {percent}%")
                
                # Étape 3 : Construction dynamique de la requête de filtres (OSM Tags)
                osm_tags = {}
                if inclure_ruines:
                    osm_tags.update({'historic': 'ruins', 'building': 'ruins', 'ruins': True})
                if inclure_abandonne:
                    osm_tags.update({'abandoned': True, 'historic': 'abandoned', 'building': 'collapsed'})
                if inclure_fontaines:
                    osm_tags.update({'amenity': ['fountain', 'watering_place'], 'natural': 'spring', 'man_made': 'well'})
                if inclure_historic:
                    # Évite d'écraser 'ruins' si déjà sélectionné
                    hist_tags = ['monument', 'castle', 'archaeological_site', 'wayside_cross', 'chapel']
                    if 'historic' in osm_tags:
                        if isinstance(osm_tags['historic'], list):
                            osm_tags['historic'].extend(hist_tags)
                        else:
                            osm_tags['historic'] = [osm_tags['historic']] + hist_tags
                    else:
                        osm_tags['historic'] = hist_tags

                bbox_m = secteur.geometry.union_all().buffer(500)
                bbox = gpd.GeoSeries([bbox_m], crs=2154).to_crs(epsg=4326).iloc[0]
                
                p_bar.progress(51, text="Téléchargement des données d'inventaire (Patientez)...")
                
                # Extraction globale (Points, Lignes, Polygones)
                elements = ox.features_from_polygon(bbox, tags=osm_tags)
                
                for percent in range(52, 86):
                    time.sleep(0.01)
                    p_bar.progress(percent, text=f"Analyse des structures et filtrage géométrique : {percent}%")
                
                # Étape 4 : Traitement et calcul géospatial
                if not elements.empty:
                    # On convertit tout en métrique
                    elements = elements.to_crs(epsg=2154)
                    
                    # On s'assure de ne garder que ce qui est dans notre zone
                    elements = elements[elements.geometry.centroid.within(union_zone)].copy()
                    
                    if not elements.empty:
                        # Identification du type précis pour l'affichage final
                        def determiner_label(row):
                            if row.get('historic') == 'ruins' or row.get('building') == 'ruins' or row.get('ruins') == True:
                                return "Ruine / Vestige"
                            elif row.get('abandoned') == True or row.get('historic') == 'abandoned' or row.get('building') == 'collapsed':
                                return "Bâtiment Abandonné / Dégradé"
                            elif row.get('amenity') in ['fountain', 'watering_place'] or row.get('natural') == 'spring' or row.get('man_made') == 'well':
                                return "Point d'eau / Fontaine / Puits"
                            return "Élément d'intérêt Historique"

                        elements['type_patrimoine'] = elements.apply(determiner_label, axis=1)
                        elements['nom_site'] = elements.get('name', 'Ancien bâti / Vestige non répertorié')
                        
                        # Calcul d'isolation : Compter le nombre d'autres structures modernes à proximité
                        # On télécharge rapidement le bâti global pour mesurer l'isolement si demandé
                        try:
                            bat_global = ox.features_from_polygon(bbox, tags={'building': True}).to_crs(epsg=2154)
                            if not bat_global.empty:
                                coords_global = list(zip(bat_global.geometry.centroid.x, bat_global.geometry.centroid.y))
                                coords_elements = list(zip(elements.geometry.centroid.x, elements.geometry.centroid.y))
                                
                                nn = NearestNeighbors(radius=rayon_iso_val).fit(coords_global)
                                adj = nn.radius_neighbors_graph(coords_elements).toarray()
                                # On soustrait 1 pour ne pas se compter soi-même si la ruine est classée comme 'building'
                                elements['voisins_modernes'] = [max(0, int(somme - 1)) for somme in adj.sum(axis=1)]
                            else:
                                elements['voisins_modernes'] = 0
                        except:
                            elements['voisins_modernes'] = 0

                        st.session_state.last_res = elements.to_crs(epsg=4326)
                        st.session_state.map_center = [st.session_state.last_res.geometry.centroid.y.mean(), st.session_state.last_res.geometry.centroid.x.mean()]
                
                for percent in range(86, 101):
                    time.sleep(0.01)
                    p_bar.progress(percent, text=f"Superposition sur les matrices IGN : {percent}%")
                
                p_bar.empty()
                status.update(label="Recherche terminée !", state="complete", expanded=False)
                
        except Exception as e:
            st.error(f"❌ Erreur lors de l'extraction : {str(e)}")

# --- AFFICHAGE MAP ET RÉSULTATS ---
if st.session_state.last_res is not None:
    res = st.session_state.last_res
    if not res.empty:
        st.success(f"✅ {len(res)} éléments patrimoniaux ou vestiges détectés !")
        
        # Initialisation sans fond pour charger l'IGN en premier
        m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.zoom_level, tiles=None)
        
        # --- FLUX OFFICIELS GÉOPLATEFORME IGN 2026 ---
        folium.TileLayer(
            tiles='https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&FORMAT=image/png&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}',
            attr='IGN France - Plan Général',
            name='Carte d\'État IGN (Très précise)',
            max_zoom=19,
            overlay=False
        ).add_to(m)
        
        folium.TileLayer(
            tiles='https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&FORMAT=image/jpeg&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}',
            attr='IGN France - Agence Spatiale',
            name='IGN Satellite Orthophoto',
            max_zoom=20,
            overlay=False
        ).add_to(m)

        folium.TileLayer('OpenStreetMap', name='Carte OpenStreetMap standard', overlay=False).add_to(m)

        # Dessin des repères
        for i, (idx, row) in enumerate(res.iterrows()):
            lat, lon = row.geometry.centroid.y, row.geometry.centroid.x
            nom = row['nom_site']
            cat = row['type_patrimoine']
            vois = row.get('voisins_modernes', 0)
            
            pop_html = f"""<div style='font-family:Arial; width:190px;'>
            <b>SITE #{i+1}</b><br>
            <span style='color:#8B4513;'><b>{cat}</b></span><br>
            <small><i>{nom}</i></small><br>
            <small>Bât. modernes à proximité : {vois}</small><hr>
            <a href='https://www.google.com/maps/search/?api=1&query={lat},{lon}' target='_blank'>🗺️ Google Maps</a><br>
            <a href='https://waze.com/ul?ll={lat},{lon}&navigate=yes' target='_blank'>🚙 Waze</a></div>"""
            
            # Code couleur des pastilles selon le type détecté
            couleur = "brown" if "Ruine" in cat else ("orange" if "Abandonné" in cat else "blue")
            
            icon_c = f'<div style="background-color:{couleur}; border:2px solid white; border-radius:50%; width:24px; height:24px; color:white; font-weight:bold; font-size:11px; display:flex; justify-content:center; align-items:center;">{i+1}</div>'
            folium.Marker([lat, lon], popup=folium.Popup(pop_html, max_width=220), icon=folium.DivIcon(html=icon_c)).add_to(m)
        
        folium.LayerControl(position='topright', collapsed=False).add_to(m)
        
        map_data = st_folium(m, width="100%", height=700, key="main_map", returned_objects=["last_object_clicked"])
        
        if map_data and map_data.get("last_object_clicked"):
            c_lat, c_lon = map_data["last_object_clicked"]["lat"], map_data["last_object_clicked"]["lng"]
            dists = res.geometry.centroid.apply(lambda p: ((p.y - c_lat)**2 + (p.x - c_lon)**2)**0.5)
            new_idx = res.index.get_loc(dists.idxmin())
            if st.session_state.sync_idx != new_idx:
                st.session_state.sync_idx = new_idx
                st.rerun()

        # Export CSV adapté au patrimoine
        csv = res[['nom_site', 'type_patrimoine']].assign(lat=res.geometry.centroid.y, lon=res.geometry.centroid.x).to_csv(index=False)
        st.download_button("📥 Télécharger les coordonnées (CSV)", csv, "patrimoine_radar.csv", "text/csv")
else:
    if lancer_scan:
        st.warning("⚠️ Aucun vestige ou repère trouvé avec ces filtres sur cette commune. Tentez d'élargir les critères.")
