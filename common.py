"""Chargement commun des permis Sitadel (Yvelines) : logements.csv + locaux.csv.

Un meme permis peut figurer dans les deux fichiers (projet mixte logements + locaux) :
on fusionne par NUM_DAU pour ne compter chaque permis qu'une fois.
"""
import os

import pandas as pd

FICHIERS = {"logements": "data/logements.csv", "locaux": "data/locaux.csv"}
SOURCE_URL = "https://www.data.gouv.fr/datasets/689c42fa521ccf80ce954f83/"
ANNUAIRE = "https://annuaire-entreprises.data.gouv.fr/entreprise/"
SEUIL_DORMANT_ANS = 3

FAMILLES = [
    "Collectivite / public", "Bailleur social", "Medico-social / sante",
    "Association / fondation", "Promoteur / constructeur",
    "SCI / fonciere / investisseur", "Holding / siege",
    "Professionnel de l'immobilier (agence, syndic)", "Entreprise (autre secteur)",
    "Non determine",
]

BASE = ["NUM_DAU", "TYPE_DAU", "DEP_LIBELLE", "COMM", "SIREN_DEM", "SIRET_DEM", "DENOM_DEM",
        "APE_DEM", "CJ_DEM", "ETAT_DAU", "DATE_REELLE_AUTORISATION", "DATE_REELLE_DOC",
        "DATE_REELLE_DAACT"]


def _fichier_classes():
    for f in ("data/permis_classes_agent.csv", "data/permis_classes_final.csv", "data/permis_classes.csv"):
        if os.path.exists(f):
            return f
    raise FileNotFoundError("Lance d'abord 1_regles_classification.py")


def lire_brut(chemin):
    """Lit un fichier Sitadel : trouve la ligne des noms courts, renvoie (donnees, libelles longs)."""
    with open(chemin, encoding="utf-8", errors="replace") as f:
        idx = next((i for i, l in enumerate(f) if "NUM_DAU" in l), 0)
    data = pd.read_csv(chemin, sep=None, engine="python", dtype=str, header=idx)
    longs = {}
    if idx > 0:
        ent = pd.read_csv(chemin, sep=None, engine="python", header=None,
                          skiprows=idx - 1, nrows=2, dtype=str)
        longs = dict(zip(ent.iloc[1], ent.iloc[0]))
    return data, longs


def _preparer(chemin, nom):
    data, longs = lire_brut(chemin)

    def col(*motifs):
        for court, long in longs.items():
            if all(m.lower() in str(long).lower() for m in motifs):
                return court
        return None

    def num(c):
        if not c:
            return pd.Series(float("nan"), index=data.index)
        return pd.to_numeric(data[c].str.replace(",", ".", regex=False), errors="coerce")

    def vrai(c):
        if not c:
            return pd.Series(False, index=data.index)
        return data[c].fillna("").str.strip().str.upper().isin({"1", "1.0", "O", "OUI", "TRUE", "T", "X"})

    manquantes = [c for c in BASE if c not in data.columns]
    if manquantes:
        print(f"  ! {nom} : colonnes absentes {manquantes}")
    out = data.reindex(columns=BASE).copy()
    out["lgt"] = num(col("Nombre total de logements créés"))
    out["lgt_soc"] = num(col("Nb de logements locatifs sociaux"))
    out["surf_non_res"] = num(col("non résidentiels", "nouvelle construite"))
    out["residence_med_soc"] = (vrai(col("résidence pour personnes âgées"))
                                | vrai(col("résidence pour personnes handicapées"))
                                | vrai(col("Présence d’une résidence sociale")))
    c_dest = col("Destination principale")
    out["destination"] = data[c_dest] if c_dest else pd.NA
    out["source"] = nom
    return out


def charger(avec_familles=True):
    """Renvoie un DataFrame : un permis par ligne (logements + locaux fusionnes), avec famille."""
    morceaux = []
    for nom, chemin in FICHIERS.items():
        if not os.path.exists(chemin):
            print(f"  ! fichier absent : {chemin}")
            continue
        m = _preparer(chemin, nom)
        print(f"{nom} : {len(m)} lignes")
        morceaux.append(m)
    if not morceaux:
        raise FileNotFoundError("Aucun fichier Sitadel trouve dans data/")

    tout = pd.concat(morceaux, ignore_index=True)
    agg = {c: "first" for c in tout.columns if c != "NUM_DAU"}
    agg.update(lgt="max", lgt_soc="max", surf_non_res="max", residence_med_soc="max",
               source=lambda s: "+".join(sorted(set(s))))
    df = tout.groupby("NUM_DAU", as_index=False).agg(agg)
    print(f"{len(df)} permis uniques ; repartition des sources : {df['source'].value_counts().to_dict()}")

    for k, nom in {"aut": "DATE_REELLE_AUTORISATION", "doc": "DATE_REELLE_DOC", "dac": "DATE_REELLE_DAACT"}.items():
        df[k] = pd.to_datetime(df[nom], errors="coerce")
    df["annee"] = df["aut"].dt.year
    df["delai_chantier_mois"] = (df["doc"] - df["aut"]).dt.days / 30.4
    df["duree_travaux_mois"] = (df["dac"] - df["doc"]).dt.days / 30.4
    limite = pd.Timestamp.today() - pd.DateOffset(years=SEUIL_DORMANT_ANS)
    df["dormant"] = df["doc"].isna() & (df["aut"] < limite)

    if not avec_familles:   # utilise par 03, qui produit justement les familles
        return df
    classes = pd.read_csv(_fichier_classes(), dtype=str)
    cols = [c for c in ("NUM_DAU", "famille", "confiance", "methode") if c in classes.columns]
    return df.merge(classes[cols].drop_duplicates("NUM_DAU"), on="NUM_DAU", how="left")