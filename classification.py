"""Classer chaque demandeur (personne morale) en famille, par regles.

Chaque ligne de sortie garde la regle qui a decide et un niveau de confiance.
Ce qui n'est pas couvert reste "Non determine" (exigence du brief).

Lanceer avec : python3 classification.py
"""
import re
import pandas as pd

FICHIER = "data/logements.csv"
SORTIE = "data/permis_classes.csv"

# --- Signaux utilises par les regles ---
# Codes de categorie juridique INSEE
CJ_BAILLEUR = {"5546", "5646"}       # SA d'HLM (5546 pour les HLM à conseil d'administration et 5646 pour les HLM à directoire
CJ_PROMOTION = {"6540, 6541"}        # 6541 -> SCI de construction-vente | 6540 -> SCI (société civile immobilière)
APE_PROMOTEUR = {"41.10A", "41.10B", "41.10C", "41.10D", "41.20A", "41.20B", "68.10Z"}
APE_FONCIERE = {"68.20A", "68.20B"}
APE_PRO_IMMO = {"68.31Z", "68.32A", "68.32B"}
APE_HOLDING = {"64.20Z", "70.10Z"}

RE_BAILLEUR = re.compile(r"\bH\.? ?L\.? ?M\b|LOYER MODERE|\bOPH\b|OFFICE PUBLIC|POUR L'HABITAT|\bESH\b|IMMOBILIERE 3F")
RE_PROMOTEUR = re.compile(r"PROGRAMMES?\b|PROMOTION|NEXITY|BOUYGUES IMMO|KAUFMAN|MARIGNAN|COGEDIM|VINCI IMMO|ALTAREA")


def classer(cj, ape, den):
    """Renvoie (famille, regle, confiance). Ordre = priorite des regles."""
    cj = str(cj).strip() if pd.notna(cj) else ""
    ape = str(ape).strip() if pd.notna(ape) else ""
    den = str(den).strip().upper() if pd.notna(den) else ""
    
    if cj.startswith("7"):
        return "Collectivite / public", "CJ 7xxx", "haute"
    if cj in CJ_BAILLEUR:
        return "Bailleur social", "CJ SA d'HLM", "haute"
    if RE_BAILLEUR.search(den):
        return "Bailleur social", "denomination (HLM, OPH, ESH...)", "moyenne"
    if ape[:2] in ("86", "87", "88"):
        return "Medico-social / sante", "APE 86/87/88", "haute"
    if cj.startswith(("92", "93")):
        return "Association / fondation (secteur a preciser)", "CJ 92xx/93xx", "moyenne"
    if ape in APE_PROMOTEUR:
        return "Promoteur / constructeur", "APE promotion/construction", "haute"
    if cj in CJ_PROMOTION:
        return "Promoteur / constructeur", "CJ SCI construction-vente", "moyenne"
    if RE_PROMOTEUR.search(den):
        return "Promoteur / constructeur", "denomination (programme, groupe connu)", "moyenne"
    if cj.startswith("65") or ape in APE_FONCIERE:
        return "SCI / fonciere / investisseur", "CJ 65xx ou APE 68.20", "faible"
    if ape in APE_HOLDING:
        return "Holding / siege", "APE holding", "moyenne"
    if ape in APE_PRO_IMMO:
        return "Professionnel de l'immobilier (agence, syndic)", "APE 68.31/68.32", "moyenne"
    return "Non determine", "aucune regle", "-"


with open(FICHIER, encoding="utf-8", errors="replace") as f:
    entete = next((i for i, l in enumerate(f) if "NUM_DAU" in l), 0)
df = pd.read_csv(FICHIER, sep=None, engine="python", dtype=str, header=entete)

# --- Partie 1 : verifier le sens des codes (denominations d'exemple par code) ---
print("=== Verification : 4 denominations d'exemple pour les 12 CJ les plus frequents ===")
for cj in df["CJ_DEM"].value_counts().head(12).index:
    ex = df.loc[df["CJ_DEM"] == cj, "DENOM_DEM"].drop_duplicates().head(4).tolist()
    print(f"CJ {cj} : {ex}")

# --- Partie 2 : classification ---
res = df.apply(
    lambda r: classer(r["CJ_DEM"], r["APE_DEM"], r["DENOM_DEM"]),
    axis=1,
    result_type="expand"
)

df[["famille", "regle", "confiance"]] = res

print("\n=== Permis par famille ===")
print(df["famille"].value_counts().to_string())
print("\n=== SIREN distincts par famille ===")
print(df.drop_duplicates("SIREN_DEM")["famille"].value_counts().to_string())
print("\n=== Confiance ===")
print(df["confiance"].value_counts().to_string())

nd = df[df["famille"] == "Non determine"]
print(f"\nNon determine : {len(nd)} permis ({len(nd) / len(df) * 100:.1f} %)")
print("Top 20 non determines (pour affiner les regles ou passer au LLM) :")
print(nd.groupby(["SIREN_DEM", "DENOM_DEM", "CJ_DEM", "APE_DEM"]).size()
        .sort_values(ascending=False).head(20).to_string())

cols = ["NUM_DAU", "SIREN_DEM", "DENOM_DEM", "CJ_DEM", "APE_DEM", "famille", "regle", "confiance"]
df[cols].to_csv(SORTIE, index=False)
print(f"\nResultat ecrit dans {SORTIE}")