"""Etape 4 : un LLM classe uniquement les demandeurs que les regles n'ont pas su classer
(famille "Non determine" ou confiance "faible"). Un appel par SIREN, resultat mis en cache.

Le LLM ne voit que : denomination, categorie juridique, code APE (donnees publiques,
personnes morales). Il n'a aucun acces au web et n'enrichit aucune fiche.

Prerequis : pip install anthropic ; variable d'environnement ANTHROPIC_API_KEY
Lance : python 04_llm_cas_ambigus.py
"""
import json
import os
import time

import anthropic
import pandas as pd

ENTREE = "data/permis_classes.csv"
SORTIE = "data/permis_classes_final.csv"
CACHE = "data/cache_llm.json"
MODEL = os.environ.get("MODEL", "claude-haiku-5-5")   # modele rapide et peu cher
MAX_APPELS = int(os.environ.get("MAX_APPELS", "400"))
PAUSE_S = 0.5                                         # cadence raisonnable

FAMILLES = [
    "Collectivite / public", "Bailleur social", "Medico-social / sante",
    "Association / fondation (secteur a preciser)", "Promoteur / constructeur",
    "SCI / fonciere / investisseur", "Holding / siege",
    "Professionnel de l'immobilier (agence, syndic)", "Entreprise (autre secteur)",
    "Non determine",
]

SYSTEME = f"""Tu classes le demandeur d'un permis de construire (une personne morale) dans une famille.
Familles autorisees : {FAMILLES}.
Tu recois uniquement sa denomination, sa categorie juridique INSEE et son code APE.
Regles : n'invente rien ; si les indices ne suffisent pas, reponds "Non determine".
La confiance est "haute" seulement si la denomination ou les codes sont sans ambiguite.
Reponds UNIQUEMENT par un JSON : {{"famille": "...", "confiance": "haute|moyenne|faible", "justification": "une phrase"}}"""

df = pd.read_csv(ENTREE, dtype=str)
cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}

a_traiter = (
    df[(df["famille"] == "Non determine") | (df["confiance"] == "faible")]
    .drop_duplicates("SIREN_DEM")
)
print(f"{len(a_traiter)} demandeurs ambigus, {len(cache)} deja en cache")

client = anthropic.Anthropic()
appels = 0
for _, r in a_traiter.iterrows():
    siren = r["SIREN_DEM"]
    if siren in cache or appels >= MAX_APPELS:
        continue
    msg = json.dumps({"denomination": r["DENOM_DEM"], "categorie_juridique": r["CJ_DEM"],
                      "code_ape": r["APE_DEM"]}, ensure_ascii=False)
    try:
        rep = client.messages.create(model=MODEL, max_tokens=300, system=SYSTEME,
                                     messages=[{"role": "user", "content": msg}])
        texte = rep.content[0].text.strip().strip("`").removeprefix("json").strip()
        cache[siren] = json.loads(texte)
    except Exception as e:  # reponse non JSON, erreur reseau... : reste non determine
        cache[siren] = {"famille": "Non determine", "confiance": "faible",
                        "justification": f"echec appel : {type(e).__name__}"}
    appels += 1
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    time.sleep(PAUSE_S)

# --- Fusion : on n'accepte le LLM que s'il est confiant et reste dans la liste ---
df["methode"] = "regles"
df["justification_llm"] = ""
for siren, res in cache.items():
    ok = res.get("famille") in FAMILLES and res.get("confiance") in ("haute", "moyenne")
    masque = (df["SIREN_DEM"] == siren) & ((df["famille"] == "Non determine") | (df["confiance"] == "faible"))
    if ok and res["famille"] != "Non determine":
        df.loc[masque, ["famille", "confiance", "methode"]] = [res["famille"], res["confiance"], "llm"]
        df.loc[masque, "justification_llm"] = res.get("justification", "")

print("\n=== Permis par famille apres LLM ===")
print(df["famille"].value_counts().to_string())
print("\nMethode :", df["methode"].value_counts().to_dict())
print(f"Non determine restant : {(df['famille'] == 'Non determine').sum()} permis")
df.to_csv(SORTIE, index=False)
print(f"Ecrit : {SORTIE}")