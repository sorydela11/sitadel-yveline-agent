"""Agent Sitadel (Yvelines) : deux modes, tous deux avec une boucle d'outils, 100 % local.

  python agent.py classifier   # agent qui classe les demandeurs ambigus en enquetant
  python agent.py explorer     # agent qui formule et teste des hypotheses, puis rapporte

Prerequis : Ollama installe et lance, un modele qui sait appeler des outils
(ollama pull qwen2.5:3b)
Variables optionnelles : MODEL_CLASSIF, MODEL_EXPLORE, MAX_DEMANDEURS, LLM_BASE_URL.

Garde-fous : les outils n'ont acces qu'au jeu de donnees local (personnes morales),
ne renvoient jamais de nom de personne physique, et un SIREN cite dans un resultat
doit exister dans les donnees (sinon l'outil refuse).
"""
import json
import os
import sys
import time

import pandas as pd
from openai import OpenAI   # client compatible Ollama (aucune cle necessaire)

from common import ANNUAIRE, FAMILLES, SOURCE_URL, charger

# Modele local via Ollama (gratuit, sans cle). Le modele doit savoir appeler des outils.
MODEL_CLASSIF = os.environ.get("MODEL_CLASSIF", "qwen2.5:3b")
MODEL_EXPLORE = os.environ.get("MODEL_EXPLORE", "qwen2.5:3b")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
MAX_DEMANDEURS = int(os.environ.get("MAX_DEMANDEURS", "15"))
DOSSIER = "resultats"
os.makedirs(DOSSIER, exist_ok=True)
os.makedirs("data", exist_ok=True)

BASE_LIMITES = ("Limites de la base : une ligne = dernier etat connu du permis ; pas de permis modificatifs ; "
                "environ 15 % des ouvertures de chantier et des achevements ne remontent jamais ; "
                "la famille d'un demandeur est une inference, pas un fait de la base.")


# ----------------------------------------------------------------- outils (donnees)
class Outils:
    def __init__(self, df):
        self.df = df
        self.etat = {"fini": False, "resultat": None, "patterns": []}

    def permis_du_demandeur(self, siren):
        d = self.df[self.df["SIREN_DEM"] == str(siren)]
        if d.empty:
            return f"Aucun permis pour le SIREN {siren}."
        r = d.iloc[0]
        tete = (f"{r['DENOM_DEM']} | CJ {r['CJ_DEM']} | APE {r['APE_DEM']} | {len(d)} permis | "
                f"famille actuelle : {r['famille']}\n")
        cols = ["NUM_DAU", "source", "COMM", "annee", "ETAT_DAU", "lgt", "lgt_soc", "surf_non_res", "residence_med_soc"]
        return tete + d.sort_values("annee")[cols].head(15).to_string(index=False)

    def chercher_denomination(self, mot):
        if len(mot.strip()) < 3:
            return "Mot trop court (3 caracteres minimum)."
        d = self.df[self.df["DENOM_DEM"].str.contains(mot, case=False, regex=False, na=False)]
        if d.empty:
            return "Aucune denomination ne contient ce mot."
        g = (d.groupby(["SIREN_DEM", "DENOM_DEM", "famille"]).size().rename("permis")
             .reset_index().sort_values("permis", ascending=False).head(20))
        return f"{d['SIREN_DEM'].nunique()} demandeurs trouves. Top 20 :\n" + g.to_string(index=False)

    def resume_table(self):
        d = self.df
        return (f"{len(d)} permis, {d['SIREN_DEM'].nunique()} demandeurs, autorisations {int(d['annee'].min())}-{int(d['annee'].max())}.\n"
                f"Permis par famille :\n{d['famille'].value_counts().to_string()}\n"
                f"Dimensions (groupby) : famille, COMM, annee, SIREN_DEM, destination, source (logements/locaux). "
                f"Metriques : permis, logements, logements_sociaux, surface_locaux_non_res, projets_logement_social, residences_med_soc, "
                f"delai_chantier_med, duree_travaux_med, part_dormants_pct.")

    def agreger(self, groupby, metrique, famille=None, annee_min=None, min_permis=1, top=15):
        if groupby not in ("famille", "COMM", "annee", "SIREN_DEM", "destination", "source"):
            return "groupby invalide."
        d = self.df
        if famille:
            d = d[d["famille"] == famille]
        if annee_min:
            d = d[d["annee"] >= int(annee_min)]
        cles = ["SIREN_DEM", "DENOM_DEM"] if groupby == "SIREN_DEM" else [groupby]
        fonctions = {
            "permis": ("NUM_DAU", "count"), "logements": ("lgt", "sum"),
            "logements_sociaux": ("lgt_soc", "sum"), "surface_locaux_non_res": ("surf_non_res", "sum"),
            "projets_logement_social": ("lgt_soc", lambda s: (s > 0).sum()),
            "residences_med_soc": ("residence_med_soc", "sum"),
            "delai_chantier_med": ("delai_chantier_mois", "median"),
            "duree_travaux_med": ("duree_travaux_mois", "median"),
            "part_dormants_pct": ("dormant", lambda s: s.mean() * 100),
        }
        if metrique not in fonctions:
            return "metrique invalide."
        res = d.groupby(cles).agg(n_permis=("NUM_DAU", "count"), valeur=fonctions[metrique]).reset_index()
        res = res[res["n_permis"] >= int(min_permis)].sort_values("valeur", ascending=False).head(int(top))
        res["valeur"] = res["valeur"].astype(float).round(1)
        return f"{metrique} par {groupby} (famille={famille}, annee>={annee_min}) :\n" + res.to_string(index=False)

    def conclure(self, famille, confiance, justification):
        if famille not in FAMILLES:
            return f"Famille invalide. Choisir parmi {FAMILLES}"
        self.etat.update(fini=True, resultat={"famille": famille, "confiance": confiance,
                                              "justification": justification})
        return "Enregistre."

    def enregistrer_pattern(self, titre, constat, interet_medico_social, preuve, confiance, limites, siren_cites=None):
        siren_cites = siren_cites or []
        inconnus = [s for s in siren_cites if s not in set(self.df["SIREN_DEM"])]
        if inconnus:
            return f"Refuse : SIREN absents des donnees {inconnus}. Ne cite que des SIREN obtenus via les outils."
        self.etat["patterns"].append({
            "titre": titre, "constat": constat, "interet_medico_social": interet_medico_social,
            "preuve": preuve, "confiance": confiance, "limites": limites,
            "sources": [SOURCE_URL] + [ANNUAIRE + s for s in siren_cites]})
        return f"Pattern enregistre ({len(self.etat['patterns'])})."

    def terminer(self):
        self.etat["fini"] = True
        return "Termine."


# ----------------------------------------------------------------- definitions d'outils
def outil(nom, desc, props, requis):
    return {"name": nom, "description": desc,
            "input_schema": {"type": "object", "properties": props, "required": requis}}


S = {"type": "string"}
T_PERMIS = outil("permis_du_demandeur", "Liste les permis d'un demandeur (SIREN) avec denomination, CJ, APE.",
                 {"siren": S}, ["siren"])
T_DENOM = outil("chercher_denomination", "Cherche les demandeurs dont la denomination contient un mot "
                "(utile pour retrouver les societes d'un meme groupe).", {"mot": S}, ["mot"])
T_CONCLURE = outil("conclure", "Rend la classification finale. 'Non determine' si les indices ne suffisent pas.",
                   {"famille": {"type": "string", "enum": FAMILLES},
                    "confiance": {"type": "string", "enum": ["haute", "moyenne", "faible"]},
                    "justification": S}, ["famille", "confiance", "justification"])
T_RESUME = outil("resume_table", "Resume de la table : volumes, familles, dimensions et metriques disponibles.", {}, [])
T_AGREGER = outil("agreger", "Agregation sur les permis. groupby : famille|COMM|annee|SIREN_DEM|destination|source. "
                  "metrique : permis|logements|logements_sociaux|surface_locaux_non_res|projets_logement_social|residences_med_soc|"
                  "delai_chantier_med|duree_travaux_med|part_dormants_pct. Filtres optionnels : famille, annee_min, "
                  "min_permis (evite les medianes sur trop peu de cas), top.",
                  {"groupby": S, "metrique": S, "famille": S, "annee_min": {"type": "integer"},
                   "min_permis": {"type": "integer"}, "top": {"type": "integer"}}, ["groupby", "metrique"])
T_PATTERN = outil("enregistrer_pattern", "Enregistre un pattern TESTE avec chiffres issus des outils.",
                  {"titre": S, "constat": S, "interet_medico_social": S,
                   "preuve": {"type": "string", "description": "chiffres exacts vus dans les resultats d'outils"},
                   "confiance": {"type": "string", "enum": ["etabli", "fragile"]},
                   "limites": S, "siren_cites": {"type": "array", "items": S}},
                  ["titre", "constat", "interet_medico_social", "preuve", "confiance", "limites"])
T_TERMINER = outil("terminer", "A appeler quand tous les patterns utiles sont enregistres.", {}, [])


# ----------------------------------------------------------------- boucle d'agent
def creer_client():
    return OpenAI(base_url=LLM_BASE_URL, api_key="ollama")   # la cle est ignoree par Ollama


def boucle(client, model, systeme, message, tools, outils, max_etapes, trace):
    return boucle_openai(client, model, systeme, message, tools, outils, max_etapes, trace)


def _executer(outils, nom, args, autorises):
    if nom not in autorises:
        return f"Outil inconnu : {nom}"
    try:
        return str(getattr(outils, nom)(**args))[:6000]
    except Exception as e:
        return f"Erreur outil : {type(e).__name__} {e}"


def boucle_openai(client, model, systeme, message, tools, outils, max_etapes, trace):
    """Meme boucle d'agent pour un modele local (Ollama) ou un service compatible OpenAI."""
    fonctions = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                   "parameters": t["input_schema"]}} for t in tools]
    autorises = {t["name"] for t in tools}
    messages = [{"role": "system", "content": systeme}, {"role": "user", "content": message}]
    for etape in range(max_etapes):
        rep = client.chat.completions.create(model=model, messages=messages, tools=fonctions, temperature=0)
        msg = rep.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            return
        for a in msg.tool_calls:
            try:
                args = json.loads(a.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            sortie = _executer(outils, a.function.name, args, autorises)
            trace.write(json.dumps({"etape": etape, "outil": a.function.name, "entree": args,
                                    "sortie": sortie[:500]}, ensure_ascii=False) + "\n")
            messages.append({"role": "tool", "tool_call_id": a.id, "content": sortie})
        if outils.etat["fini"]:
            return


# ----------------------------------------------------------------- mode classifier
SYSTEME_CLASSIF = f"""Tu es un analyste qui qualifie le demandeur d'un permis de construire (personne morale, Yvelines).
Familles : {FAMILLES}.
Tu peux enqueter avec les outils sur le jeu de donnees local (ses autres permis, les societes de meme nom ou groupe).
Methode : lis la denomination, les codes CJ et APE, regarde la nature de ses projets (logements sociaux,
residences), puis conclus avec l'outil `conclure`. Maximum 5 appels d'outils.
Regles : n'invente rien ; si les indices ne suffisent pas, famille "Non determine".
Ne mentionne aucun nom de personne physique."""


def classifier():
    df = charger()
    cache_f = "data/cache_agent.json"
    cache = json.load(open(cache_f, encoding="utf-8")) if os.path.exists(cache_f) else {}
    cibles = df[(df["famille"] == "Non determine") | (df["confiance"] == "faible")].drop_duplicates("SIREN_DEM")
    print(f"{len(cibles)} demandeurs ambigus ; traitement de {MAX_DEMANDEURS} maximum ({len(cache)} en cache)")
    client = creer_client()
    tools = [T_PERMIS, T_DENOM, T_CONCLURE]
    n = 0
    with open(f"{DOSSIER}/agent_trace_classif.jsonl", "a", encoding="utf-8") as trace:
        for _, r in cibles.iterrows():
            siren = r["SIREN_DEM"]
            if siren in cache or n >= MAX_DEMANDEURS:
                continue
            outils = Outils(df)
            msg = f"Qualifie le demandeur SIREN {siren}. Indices : {r['DENOM_DEM']} | CJ {r['CJ_DEM']} | APE {r['APE_DEM']}"
            try:
                boucle(client, MODEL_CLASSIF, SYSTEME_CLASSIF, msg, tools, outils, 6, trace)
            except Exception as e:
                print(f"  erreur {siren} : {type(e).__name__}")
            cache[siren] = outils.etat["resultat"] or {"famille": "Non determine", "confiance": "faible",
                                                       "justification": "pas de conclusion"}
            json.dump(cache, open(cache_f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            n += 1
            time.sleep(0.5)

    if "methode" not in df.columns:
        df["methode"] = "regles"
    df["methode"] = df["methode"].fillna("regles")
    for siren, res in cache.items():
        ok = res["confiance"] in ("haute", "moyenne") and res["famille"] != "Non determine"
        m = (df["SIREN_DEM"] == siren) & ((df["famille"] == "Non determine") | (df["confiance"] == "faible"))
        if ok and m.any():
            df.loc[m, ["famille", "confiance", "methode"]] = [res["famille"], res["confiance"], "agent"]
    cols = ["NUM_DAU", "SIREN_DEM", "DENOM_DEM", "CJ_DEM", "APE_DEM", "famille", "confiance", "methode"]
    df[cols].to_csv("data/permis_classes_agent.csv", index=False)
    print(df["famille"].value_counts().to_string())
    print("Methode :", df["methode"].value_counts().to_dict())
    print("Ecrit : data/permis_classes_agent.csv")


# ----------------------------------------------------------------- mode explorer
SYSTEME_EXPLORE = f"""Tu es analyste pour Buddimm, direction immobiliere externalisee qui accompagne des associations
medico-sociales, des structures de l'economie sociale et solidaire et des bailleurs sociaux.
Tu disposes des permis de construire des Yvelines (demandeurs personnes morales) classes par famille.
Mission : trouver 4 a 6 patterns NON TRIVIAUX utiles a un acteur de l'immobilier medico-social
(ex. qui construit regulierement, qui porte des projets a vocation sociale, ou et avec quels acteurs
des projets se concentrent, delais, permis dormants). Sois creatif, mais teste chaque idee avec les outils.
Methode : commence par `resume_table`, formule des hypotheses, verifie-les avec `agreger` et
`permis_du_demandeur`, puis enregistre chaque pattern avec `enregistrer_pattern` (chiffres exacts vus dans les outils).
Honnetete : distingue 'etabli' et 'fragile' ; dis ce qui manque ; une co-presence n'est pas un partenariat prouve.
{BASE_LIMITES}
Interdit : aucune prise de contact, aucun nom de personne physique, aucun chiffre que tu n'as pas vu dans un outil.
Termine par `terminer` apres avoir enregistre tes patterns."""


def explorer():
    df = charger()
    outils = Outils(df)
    client = creer_client()
    tools = [T_RESUME, T_AGREGER, T_PERMIS, T_DENOM, T_PATTERN, T_TERMINER]
    with open(f"{DOSSIER}/agent_trace_explore.jsonl", "w", encoding="utf-8") as trace:
        boucle(client, MODEL_EXPLORE, SYSTEME_EXPLORE, "Commence ton analyse.", tools, outils, 30, trace)
    patterns = outils.etat["patterns"]
    md = [f"# Patterns trouves par l'agent\n\nSource : {SOURCE_URL}\n\n{BASE_LIMITES}\n"]
    for i, p in enumerate(patterns, 1):
        md.append(f"\n## {i}. {p['titre']}  ({p['confiance']})\n- Constat : {p['constat']}\n"
                  f"- Interet medico-social : {p['interet_medico_social']}\n- Preuve : {p['preuve']}\n"
                  f"- Limites : {p['limites']}\n- Sources : {', '.join(p['sources'])}\n")
    with open(f"{DOSSIER}/agent_patterns.md", "w", encoding="utf-8") as f:
        f.write("".join(md))
    print(f"{len(patterns)} patterns -> {DOSSIER}/agent_patterns.md (trace : {DOSSIER}/agent_trace_explore.jsonl)")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    {"classifier": classifier, "explorer": explorer}.get(mode, lambda: print(__doc__))()