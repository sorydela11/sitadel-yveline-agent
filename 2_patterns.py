""" Patterns a exploiter pour un acteur de l'immobilier medico-social.

Entrees : data/logements.csv et data/locaux.csv + data/permis_classes_final.csv (familles).
Sorties : resultats/*.csv et resultats/synthese.md (chaque resultat renvoie a sa source).

Lance : python 2_patterns.py
"""
import os

import pandas as pd

from common import charger

CLASSES = "data/permis_classes_final.csv"
DOSSIER = "resultats"
SOURCE_URL = "https://www.statistiques.developpement-durable.gouv.fr/catalogue?page=dataset&datasetId=6513f0189d7d312c80ec5b5b"
ANNUAIRE = "https://annuaire-entreprises.data.gouv.fr/entreprise/"
ANNEE_MIN = 2021          # fenetre "recente" pour la recurrence
SEUIL_DORMANT_ANS = 3     # autorise depuis plus de N ans sans ouverture de chantier

os.makedirs(DOSSIER, exist_ok=True)

df = charger()   # logements + locaux fusionnes
df["lien_siren"] = ANNUAIRE + df["SIREN_DEM"]
recent = df[df["annee"] >= ANNEE_MIN]

synthese = [f"# Synthese des patterns\n\nSource des permis : {SOURCE_URL}\n"
            f"Fenetre recente : autorisations depuis {ANNEE_MIN}. {len(df)} permis analyses.\n"]


def sortie(nom, titre, pourquoi, tableau):
    tableau.to_csv(f"{DOSSIER}/{nom}.csv", index=False)
    synthese.append(f"\n## {titre}\n*Interet pour le medico-social : {pourquoi}*\n\n```\n{tableau.to_string(index=False)}\n```\n")
    print(f"\n=== {titre} ===\n{tableau.head(10).to_string(index=False)}")


# P1 - Constructeurs reguliers (fenetre recente) par famille
p1 = (recent.groupby(["famille", "SIREN_DEM", "DENOM_DEM", "lien_siren"]).agg(
        permis=("NUM_DAU", "count"), logements=("lgt", "sum")).reset_index()
      .query("permis >= 3").sort_values("permis", ascending=False))
sortie("p1_constructeurs_reguliers", f"P1 - Constructeurs reguliers (>=3 permis depuis {ANNEE_MIN})",
       "ce sont les partenaires et concurrents qui produisent en continu dans le departement", p1)

# P2 - Projets a vocation sociale / medico-sociale : qui les porte ?
vocation = df[(df["residence_med_soc"]) | (df["lgt_soc"] > 0)]
p2 = (vocation.groupby(["famille", "SIREN_DEM", "DENOM_DEM", "lien_siren"]).agg(
        permis=("NUM_DAU", "count"), logements_soc=("lgt_soc", "sum")).reset_index()
      .sort_values("permis", ascending=False))
sortie("p2_projets_vocation_sociale", "P2 - Porteurs de projets a vocation sociale ou medico-sociale",
       "montre qui, au-dela des associations, construit des residences pour personnes agees, handicapees ou du logement social", p2)

# P3 - Communes ou bailleurs et promoteurs sont actifs en meme temps (co-presence, pas partenariat prouve)
sel = recent[recent["famille"].isin(["Bailleur social", "Promoteur / constructeur"])]
p3 = sel.pivot_table(index="COMM", columns="famille", values="NUM_DAU", aggfunc="count", fill_value=0)
p3 = p3[(p3 > 1).all(axis=1)].assign(total=lambda t: t.sum(axis=1)).sort_values("total", ascending=False).reset_index()
sortie("p3_communes_copresence", "P3 - Communes ou bailleurs sociaux et promoteurs sont tous deux actifs",
       "zones ou le foncier est dispute et ou des montages en partenariat sont plausibles (a verifier : la base ne relie pas les permis entre eux)", p3)

# P4 - Delais par famille (uniquement permis ayant les deux dates : biais de survie)
df["delai_chantier_mois"] = (df["doc"] - df["aut"]).dt.days / 30.4
df["duree_travaux_mois"] = (df["dac"] - df["doc"]).dt.days / 30.4
p4 = (df.groupby("famille").agg(permis=("NUM_DAU", "count"),
        delai_autorisation_chantier_med=("delai_chantier_mois", "median"),
        duree_travaux_med=("duree_travaux_mois", "median")).round(1).reset_index())
sortie("p4_delais_par_famille", "P4 - Delais medians par famille (mois)",
       "indique la rapidite de passage a l'acte de chaque type d'acteur ; attention, ~15 % des ouvertures et achevements ne remontent jamais", p4)

# P5 - Permis dormants : autorises depuis longtemps, sans ouverture de chantier
limite = pd.Timestamp.today() - pd.DateOffset(years=SEUIL_DORMANT_ANS)
dorm = df[df["doc"].isna() & (df["aut"] < limite)]
p5 = (dorm.groupby("famille").agg(dormants=("NUM_DAU", "count"), logements=("lgt", "sum")).reset_index()
      .merge(df.groupby("famille").size().rename("total").reset_index(), on="famille")
      .assign(part_pct=lambda t: (t.dormants / t.total * 100).round(1)).sort_values("dormants", ascending=False))
sortie("p5_dormants", f"P5 - Permis dormants (autorises depuis plus de {SEUIL_DORMANT_ANS} ans, sans chantier)",
       "terrains ou programmes potentiellement bloques, donc opportunites de reprise ou d'insertion d'un projet social (hypothese : peut aussi etre une non-remontee de la base)", p5)

# P6 - Concentration par commune
p6 = (recent.groupby("COMM").agg(permis=("NUM_DAU", "count"), logements=("lgt", "sum"),
        sociaux=("lgt_soc", "sum")).reset_index().sort_values("permis", ascending=False).head(20))
sortie("p6_communes", "P6 - Communes les plus actives (code INSEE)",
       "cible geographique pour une demarche de prospection", p6)

synthese.append("\n## Limites\n- Une ligne = dernier etat connu du permis ; pas de permis modificatifs.\n"
                "- ~15 % des ouvertures et achevements ne remontent jamais (note du ministere).\n"
                "- Familles obtenues par regles ; le reste est 'Non determine'.\n")
with open(f"{DOSSIER}/synthese.md", "w", encoding="utf-8") as f:
    f.write("".join(synthese))
print(f"\nEcrit : {DOSSIER}/synthese.md")
