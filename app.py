# --- TRAITEMENT ET FILTRAGE LOCAL ---

if st.session_state.commune_validee:
    gdf_brut = charger_tous_vestiges_osm(st.session_state.commune_validee)
    
    if gdf_brut is not None and not gdf_brut.empty:
        tags_actifs = []
        if choix_ruines: tags_actifs.append("ruins")
        if choix_chateaux: tags_actifs.extend(["castle", "fortress"])
        if choix_archeo: tags_actifs.append("archaeological_site")
        if choix_monuments: tags_actifs.extend(["monument", "memorial"])
        
        gdf_filtre_type = gdf_brut[gdf_brut['historic'].isin(tags_actifs)]
        
        if not gdf_filtre_type.empty:
            utm_crs = gdf_filtre_type.estimate_utm_crs()
            gdf_proj = gdf_filtre_type.to_crs(utm_crs)
            
            if rayon_isolement > 0:
                gdf_batiments = charger_batiments_osm(st.session_state.commune_validee)
                if gdf_batiments is not None and not gdf_batiments.empty:
                    gdf_batiments_proj = gdf_batiments.to_crs(utm_crs)
                    sindex_bats = gdf_batiments_proj.sindex
                    def verifier_isolement(point, index, gdf_bats, rayon):
                        bbox = point.buffer(rayon)
                        match_idx = index.query(bbox, predicate="intersects")
                        if len(match_idx) == 0: return True
                        candidats = gdf_bats.iloc[match_idx]
                        return candidats.distance(point).min() >= rayon
                    mask_isole = gdf_proj.geometry.apply(lambda pt: verifier_isolement(pt, sindex_bats, gdf_batiments_proj, rayon_isolement))
                    gdf_filtre_spatial_proj = gdf_proj[mask_isole]
                else:
                    gdf_filtre_spatial_proj = gdf_proj
            else:
                gdf_filtre_spatial_proj = gdf_proj
            
            gdf_final = gdf_filtre_spatial_proj.to_crs(epsg=4326)
            
            df_affichage = pd.DataFrame(gdf_final.drop(columns='geometry'))
            
            if not gdf_final.empty:
                center_y = gdf_final.geometry.y.mean()
                center_x = gdf_final.geometry.x.mean()
                zoom_carte = 12
            else:
                center_y, center_x, zoom_carte = 46.0, 2.0, 6
                
            id_selectionne = None
            
            zone_carte = st.empty()
            st.markdown("---")
            st.subheader("📋 Données détaillées des résultats")
            
            evenement_clic = st.dataframe(
                df_affichage, 
                selection_mode="single-row", 
                on_select="rerun", 
                use_container_width=True
            )
            
            if evenement_clic and evenement_clic.selection.rows:
                index_ligne_selectionnee = evenement_clic.selection.rows[0]
                entite_cible = gdf_final.iloc[index_ligne_selectionnee]
                center_y = entite_cible.geometry.y
                center_x = entite_cible.geometry.x
                zoom_carte = 16  
                id_selectionne = entite_cible.name 

            with zone_carte.container():
                st.subheader(f"📍 {len(gdf_final)} élément(s) historique(s) repéré(s)")
                m = folium.Map(location=[center_y, center_x], zoom_start=zoom_carte)
                folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Satellite').add_to(m)
                
                for idx, row in gdf_final.iterrows():
                    ligne_cliquee = (idx == id_selectionne)
                    folium.Marker(
                        location=[row.geometry.y, row.geometry.x],
                        icon=folium.Icon(color="green" if ligne_cliquee else "red", icon="star" if ligne_cliquee else "landmark", prefix="fa")
                    ).add_to(m)
                st_folium(m, width=None, height=650)
        else:
            st.warning("Aucun résultat ne correspond aux filtres.")
    else:
        st.error("Aucune donnée trouvée. Relancez le scan.")
