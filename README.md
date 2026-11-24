# sitadel-yvelines-agent

Qualification des demandeurs de permis de construire (Sitadel, Yvelines) : classification en
familles d'acteurs, puis détection de patterns utiles à un acteur de l'immobilier médico-social.

Cas métier réalisé dans le cadre d'un processus de recrutement. Données publiques uniquement.

## Angle choisi

Sitadel dit **qui construit** (SIREN, APE, catégorie juridique) mais pas **ce qu'est** le demandeur.
Le projet classe chaque permis en famille (bailleur social, promoteur, SCI, médico-social...),
puis cherche des patterns : récurrence, projets à vocation sociale, communes actives, délais, permis dormants.

## Périmètre

- Permis de construire (PC) de logements (`data/logements.csv`) et de locaux (`data/locaux.csv`), département des Yvelines (78).
- Un permis mixte peut figurer dans les deux fichiers : `common.py` les fusionne par numéro de dossier (`NUM_DAU`)
  pour ne compter chaque permis qu'une fois, et garde la colonne `source` (logements, locaux ou les deux).
- Demandeurs personnes morales uniquement (SIREN valide). Aucun nom de personne physique n'est enrichi.
- Hors périmètre : toute prise de contact avec les demandeurs.

## Sources

- Jeu de données « Liste des permis de construire et autres autorisations d'urbanisme » (SDES) :
  https://www.statistiques.developpement-durable.gouv.fr/catalogue?page=dataset&datasetId=6513f0189d7d312c80ec5b5b
- Fichiers téléchargés le : `21/11/2026`

## Pipeline

| Étape | Script | Rôle |
|---|---|---|
| 1 | `0_exploration.py` | qualité, volumes, valeurs vides |
| 2 | `1_regles_classification.py` | familles par règles (CJ, APE, dénomination) |
| 3 | `agent.py classifier` | agent à outils (modèle local Ollama) sur les cas ambigus |
| 4 | `2_patterns.py` | patterns et synthèse avec liens sources |
| 5b | `agent.py explorer` | agent qui formule et teste des hypothèses |

`agent.py` (avec `common.py`) contient deux agents à outils, qui tournent en local avec Ollama (sans clé API) :

- `python agent.py classifier` : pour chaque demandeur ambigu, le modèle enquête avec des outils
  (autres permis du SIREN, recherche de sociétés de même nom) puis conclut ou reste « Non déterminé ».
- `python agent.py explorer` : le modèle formule des hypothèses, les teste avec des outils d'agrégation
  bornés, et enregistre des patterns avec chiffres, limites et sources (`resultats/agent_patterns.md`).
  Chaque appel d'outil est tracé dans `resultats/agent_trace_*.jsonl`.

Garde-fous : outils limités au jeu de données local (personnes morales), pas d'exécution de code libre,
aucun nom de personne physique, un SIREN cité doit exister dans les données.
Un petit modèle local est moins fiable qu'un modèle hébergé : plus de « Non déterminé » sont à prévoir.
Les règles tranchent d'abord ; tout ce qui reste incertain est « Non déterminé ».


## Prérequis

Avant de lancer le projet, les éléments suivants doivent être installés :
- **Python 3.10+**
- **Ollama** : moteur permettant d'exécuter des modèles de langage localement.


### 1. Installer Ollama
Télécharger et installer Ollama selon votre système d'exploitation :
**macOS**
Télécharger l'application depuis [ollama.com/download](https://ollama.com/download) ou utiliser :
**Linux**
Exécuter la commande suivante dans un terminal :
```bash
curl -fsSL https://ollama.com/install.sh | sh
```
**Windows**
- Télécharger l'installateur depuis [ollama.com/download](https://ollama.com/download).

### 2. Vérifier l'installation
Vérifier qu'Ollama est correctement installé :
```bash
ollama --version
```
Démarrer le service Ollama si nécessaire :
```bash
ollama serve
```
Sur macOS et Windows, l'application Ollama peut démarrer automatiquement le service. Dans ce cas, il n'est pas nécessaire de lancer cette commande.

### 3. Télécharger le modèle utilisé par le projet

Le projet utilise `qwen2.5:3b` comme modèle local.
```bash
ollama pull qwen2.5:3b
```

Vérifier que le modèle est disponible :
```bash
ollama list
```

**Remarque :** Ollama exécute le modèle localement et expose une API compatible avec OpenAI sur `http://localhost:11434/v1`. Le client Python `openai` utilise cette API avec une clé fictive (`ollama`), ignorée par le serveur local. Aucune clé API Anthropic ou OpenAI n'est nécessaire pour exécuter les agents.

## Lancer

```bash
python -m pip install requirements.txt
python 1_regles_classification.py
python agent.py classifier
python agent.py explorer
python 2_patterns.py
```

Les fichiers sources vont dans `data/` : `data/logements.csv` et `data/locaux.csv`.
Pour explorer chaque fichier séparément : `python 0_exploration.py data/locaux.csv`.

## Limites

- Une ligne = dernier état connu du permis ; pas de permis modificatifs.
- Environ 15 % des ouvertures de chantier et des achèvements ne remontent jamais (note du ministère).
- La dénomination n'est diffusée que pour les personnes morales trouvées dans Sirene.
- La famille d'un demandeur est une inférence, pas un fait de la base.
- Tests de cohérence des codes de catégorie juridique à valider contre la nomenclature INSEE.

## Outils et temps

- Python, pandas, Ollama avec le modèle local `qwen2.5:7b` (client `openai` pour dialoguer avec Ollama).
- Assistant de code : Claude (aide à l'écriture des scripts).
- Temps passé : `18 h`.