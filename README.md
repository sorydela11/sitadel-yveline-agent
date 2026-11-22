# sitadel-yvelines-agent

Qualification des demandeurs de permis de construire (Sitadel, Yvelines) : classification en
familles d'acteurs, puis détection de patterns utiles à un acteur de l'immobilier médico-social.

Cas métier réalisé dans le cadre d'un processus de recrutement. Données publiques uniquement.

## Angle choisi

Sitadel dit **qui construit** (SIREN, APE, catégorie juridique) mais pas **ce qu'est** le demandeur.
Le projet classe chaque permis en famille (bailleur social, promoteur, SCI, médico-social...),
puis cherche des patterns : récurrence, projets à vocation sociale, communes actives, délais, permis dormants.

## Périmètre

- Permis de construire (PC) de logements et de locaux, département des Yvelines (78).
- Demandeurs personnes morales uniquement (SIREN valide). Aucun nom de personne physique n'est enrichi.
- Hors périmètre : toute prise de contact avec les demandeurs.

## Sources

- Jeu de données « Liste des permis de construire et autres autorisations d'urbanisme » (SDES) :
  https://www.data.gouv.fr/datasets/689c42fa521ccf80ce954f83/
- Fichiers téléchargés le : `<DATE>` (à compléter). Fiches entreprises : annuaire-entreprises.data.gouv.fr

## Pipeline

| Étape | Script | Rôle |
|---|---|---|
| 1 | `01_explorer_sitadel.py` | structure des fichiers |
| 2 | `02_exploration_pandas_v2.py` | qualité, volumes, valeurs vides |
| 3 | `03_classification_regles.py` | familles par règles (CJ, APE, dénomination) |
| 4 | `04_llm_cas_ambigus.py` | LLM uniquement sur les cas ambigus, sortie JSON, cache |
| 5 | `05_patterns.py` | patterns et synthèse avec liens sources |

C'est un pipeline avec une étape LLM, pas un agent autonome : les règles tranchent d'abord,
le LLM n'intervient que sur les cas restants, et tout ce qui reste incertain est « Non déterminé ».

## Lancer

```bash
pip install pandas anthropic
export ANTHROPIC_API_KEY=...        # seulement pour l'étape 4
python 03_classification_regles.py
python 04_llm_cas_ambigus.py
python 05_patterns.py
```

Les fichiers sources vont dans `data/` (ignoré par Git).

## Limites

- Une ligne = dernier état connu du permis ; pas de permis modificatifs.
- Environ 15 % des ouvertures de chantier et des achèvements ne remontent jamais (note du ministère).
- La dénomination n'est diffusée que pour les personnes morales trouvées dans Sirene.
- La famille d'un demandeur est une inférence, pas un fait de la base.
- Tests de cohérence des codes de catégorie juridique à valider contre la nomenclature INSEE.

## Outils et temps

- Python, pandas, API Anthropic (modèle indiqué dans `04_llm_cas_ambigus.py`).
- Assistant de code : Claude (aide à l'écriture des scripts et à la structuration de la note).
- Temps passé : `<X> h` (à compléter honnêtement).