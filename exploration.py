"""
    Explorations des datasets

    Renseigne les fichiers logements.csv et locaux.csv et un dictionnaire COL avec les vrais nom de colonnes
    des fichihers (mets None si la colonnes n'existe pas)
    
    Installation : python3 -m pip install pandas
"""
import sys
import pandas as pd

LOGEMENTS = "data/logements.csv"
LOCAUX = "data/locaux.csv"

COL = {
    "id": "NUM_DAU",     # identifiant du permis
    "type": "TYPE_DAU",    # type du permis (PC)
    "dep": "DEP_LIBELLE",   # libelle du département (Yvelines) du lieux des travaux
    "commune": "COMM",      # code de la commune du lieu des travaux 
    "siren": "SIREN_DEM",   # siren du demandeur
    "siret": "SIRET_DEM",   # siret du demandeur
    "denom": "DENOM_DEM",   # dénomination du demandeur
    "ape": "APE_DEM",       # code principal de l'établissement du demandeur 
    "cat_jur": "CJ_DEM",    # catégorie juridique du demandeur 
    "etat": "ETAT_DAU",     # état d'avancement du projet 
    "date_autor": "DATE_REELLE_AUTORISATION",   # date réelle d'autorisation du PC (permis de contruire)
    "date_doc": "DATE_REELLE_DOC",  # date réelle d'ouverture du chantier
    "date_daact":"DATE_REELLE_DAACT",   # date réelle d'achèvement des travaux
}

df = pd.read_csv(LOGEMENTS, sep=None, engine="python", dtype=str, encoding="utf-8", header=1)
print(f"Fichier brut -> logements.csv: {len(df)} lignes, {df.shape[1]} colonnes")
#print("Colonnes reelles :", list(df1.columns))

df2 = pd.read_csv(LOCAUX, sep=None, engine="python", dtype=str, encoding="utf-8")
print(f"Fichier brut -> locaux.csv: {len(df2)} lignes, {df2.shape[1]} colonnes")
#print("Colonnes reelles :", list(df2.columns))

# Arret clair si une colonne est introuvable (plus de section sautee en silence)
manquantes = [v for v in COL.values() if v not in df.columns]
if manquantes:
    print("Colonnes introuvables :", manquantes)
    print("Colonnes reelles :", list(df.columns))
    sys.exit(1)

# --- Controle de ce que contient le fichier (verifie tes filtres) ---
for cle in ("type", "dep"):
    print(f"\n=== Valeurs de {COL[cle]} ===")
    print(df[COL[cle]].value_counts(dropna=False).head(10).to_string())

# --- Qualite ---
print("\n=== Part de valeurs vides (%) sur les colonnes utiles ===")
print((df[list(COL.values())].isna().mean() * 100).round(1).sort_values(ascending=False).to_string())
print(f"\nDoublons sur {COL['id']} : {df[COL['id']].duplicated().sum()}")
siren_ok = df[COL["siren"]].str.fullmatch(r"\d{9}", na=False)
print(f"SIREN au format valide (9 chiffres) : {siren_ok.sum()} / {len(df)}")

# --- Repartitions ---
for cle, titre in [("cat_jur", "Categories juridiques"), ("ape", "Codes APE"),
                   ("etat", "Etats d'avancement"), ("commune", "Communes")]:
    print(f"\n=== Top 15 : {titre} ===")
    print(df[COL[cle]].value_counts(dropna=False).head(15).to_string())

# --- Demandeurs recurrents ---
par_siren = df[COL["siren"]].value_counts()
print(f"\nSIREN distincts : {len(par_siren)}")
print(f"SIREN avec plus d'un permis : {(par_siren > 1).sum()}")
top = par_siren.head(20).rename("nb_permis").reset_index()
top.columns = [COL["siren"], "nb_permis"]
noms = df.drop_duplicates(COL["siren"]).set_index(COL["siren"])[COL["denom"]]
top["denomination"] = top[COL["siren"]].map(noms)
print("\nTop 20 demandeurs recurrents :")
print(top.to_string(index=False))

# --- Dates et coherence ---
d = {k: pd.to_datetime(df[COL[k]], errors="coerce") for k in ("date_autor", "date_doc", "date_daact")}
for k, s in d.items():
    print(f"\n{COL[k]} : {s.min()} -> {s.max()}, vide = {s.isna().mean() * 100:.1f} %")
print(f"\nChantier ouvert avant autorisation : {(d['date_doc'] < d['date_autor']).sum()}")
print(f"Achevement avant ouverture : {(d['date_daact'] < d['date_doc']).sum()}")
print(f"Autorises sans ouverture de chantier : {(d['date_autor'].notna() & d['date_doc'].isna()).sum()}")
print(f"Ouverts sans achevement : {(d['date_doc'].notna() & d['date_daact'].isna()).sum()}")
