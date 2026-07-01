# --- GESTION DE LA SÉLECTION DANS LE TABLEAU ---
            df_affichage = pd.DataFrame(gdf_final.drop(columns='geometry'))
            
            # Coordonnées d'affichage par défaut
            if not gdf_final.empty:
                center_y = gdf_final.geometry.y.mean()
                center_x = gdf_final.geometry.x.mean()
                zoom_carte = 12
            else:
                center_y, center_x, zoom_carte = 46.0, 2.0, 6
                
            id_selectionne = None
            
            # Placeholder pour maintenir la carte en haut et le tableau en bas
            zone_carte = st.empty()
            st.markdown("---")
            st.subheader("📋 Données détaillées des résultats")
            
            # Correction : "single-row" avec tiret et indentation correcte
            evenement_clic = st.dataframe(
                df_affichage, 
                selection_mode="single-row", 
                on_select="rerun", 
                use_container_width=True
            )
            
            # Analyse de la ligne sélectionnée
            if evenement_clic and evenement_clic.selection.rows:
                index_ligne_selectionnee = evenement_clic.selection.rows[0]
                entite_cible = gdf_final.iloc[index_ligne_selectionnee]
                center_y = entite_cible.geometry.y
                center_x = entite_cible.geometry.x
                zoom_carte = 16  
                id_selectionne = entite_cible.name
