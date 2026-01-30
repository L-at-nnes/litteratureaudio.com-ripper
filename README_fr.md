# Ripper litteratureaudio.com

[Read in English](README.md)

![Version](https://img.shields.io/badge/version-2.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Licence](https://img.shields.io/badge/licence-MIT-green)
![Statut](https://img.shields.io/badge/statut-beta-yellow)

**⚠️ Notice beta :** Cette version inclut des ameliorations significatives sur l'extraction des sommaires/collections. Merci de signaler tout probleme : https://github.com/L-at-nnes/litteratureaudio.com-ripper/issues

**Limitations connues :**
- Les livres avec plusieurs versions (differents lecteurs) peuvent etre fusionnes dans un meme dossier
- Certains cas speciaux avec des noms d'auteurs inverses dans les URLs sont geres mais peuvent necessiter des ajustements

Outil en ligne de commande pour scraper et telecharger les livres audio depuis
litteratureaudio.com, avec une arborescence propre (compatible Windows) et des
exports de metadonnees utiles.

Il est concu pour etre robuste face aux particularites du site: projets
collectifs, pagination, pistes chargees 10 par 10 ("voir plus"), variantes
MP3/ZIP et nommages incoherents.

## Depot

- https://github.com/L-at-nnes/litteratureaudio.com-ripper

## Installation

Pre-requis: Python 3.10+ recommande.

```bash
pip install -r requirements.txt
```

## Demarrage rapide

### Telecharger un livre

```bash
python main.py https://www.litteratureaudio.com/livre-audio-gratuit-mp3/jules-verne-le-tour-du-monde-en-80-jours.html
```

### Telecharger un auteur (reglages polis)

```bash
python main.py https://www.litteratureaudio.com/livre-audio-gratuit-mp3/auteur/jules-verne --threads 4 --sleep 0.5 --format default
```

### Telecharger depuis un fichier texte

```bash
python main.py --txt audiobooks.txt --threads 4 --sleep 0.5 --format default
```

## Reference CLI

### Options disponibles

Le tableau ci-dessous couvre toutes les options exposees par la CLI.

| Option | Type / valeurs | Défaut | Description | Exemple |
| --- | --- | --- | --- | --- |
| `URL ...` | une ou plusieurs URL | | URL(s) directes à traiter | `python main.py https://.../livre.html` |
| `--txt` | chemin fichier | | Fichier texte (une URL par ligne, `#` ignoré) | `python main.py --txt audiobooks.txt` |
| `--output` | chemin dossier | `./dl` | Dossier racine de sortie | `python main.py --output D:\Audio` |
| `--threads` | entier | `1` | Téléchargements parallèles (1 = séquentiel) | `python main.py --threads 4 --txt audiobooks.txt` |
| `--sleep` | float (secondes) | `0` | Délai minimum entre requêtes HTTP | `python main.py --sleep 0.5 --txt audiobooks.txt` |
| `--format` | `default`, `mp3`, `zip`, `mp3+zip`, `all`, `unzip` | `default` | Politique de téléchargement | `python main.py --format mp3 --txt audiobooks.txt` |
| `--no-json` | flag | `false` | Ne pas exporter le JSON metadata | `python main.py --no-json URL` |
| `--no-cover` | flag | `false` | Ne pas télécharger les covers | `python main.py --no-cover URL` |
| `--no-description` | flag | `false` | Ne pas écrire `description.txt` | `python main.py --no-description URL` |
| `--no-id3` | flag | `false` | Ne pas écrire les tags ID3 | `python main.py --no-id3 URL` |
| `--max-pages` | entier | `0` (illimité) | Limiter la pagination des listings (auteur / voix / membre) | `python main.py --max-pages 2 URL_LISTING` |
| `--dry-run` | flag | `false` | Extraction seule, sans écriture audio | `python main.py --dry-run --txt audiobooks.txt` |
| `--metadata-only` | flag | `false` | Écrit cover + description + JSON uniquement | `python main.py --metadata-only URL` |
| `--summary-report` | chemin JSON | | Écrit un résumé (nom par défaut: `summary-report.json`) | `python main.py --summary-report --txt audiobooks.txt` |
| `--csv-report` | chemin CSV | | Écrit un CSV d'indexation (nom par défaut: `report.csv`) | `python main.py --csv-report --txt audiobooks.txt` |
| `--verify` | chemin dossier | | Re-scan un dossier et signale les manques | `python main.py --verify dl` |
| `--no-duplicates` | flag | `false` | Crée des raccourcis au lieu de re-télécharger les doublons | `python main.py --no-duplicates --txt audiobooks.txt` |

### Exemples de commandes utiles

| Objectif | Commande |
| --- | --- |
| Livre unique | `python main.py https://www.litteratureaudio.com/livre-audio-gratuit-mp3/luigi-pirandello-bonheur.html` |
| Auteur complet (poli) | `python main.py https://www.litteratureaudio.com/livre-audio-gratuit-mp3/auteur/alexandre-dumas --threads 4 --sleep 0.5 --format default` |
| Liste d'URL (mode normal) | `python main.py --txt audiobooks.txt --threads 4 --sleep 0.5 --format default` |
| Liste d'URL (dry-run) | `python main.py --dry-run --txt audiobooks.txt --threads 4 --sleep 0.5 --format default` |
| Metadonnees uniquement | `python main.py --metadata-only --txt audiobooks.txt --threads 4 --sleep 0.5 --format default` |
| Dry-run + rapports | `python main.py --dry-run --summary-report summary.json --csv-report library.csv --txt audiobooks.txt` |
| Verification d'une sortie | `python main.py --verify dl` |

## Regles d'arborescence (comportement attendu)

Le comportement depend du type d'URL de depart.

### 1) URL auteur / lecteur / membre

- Un dossier racine est cree avec son nom.
- Tous les livres sont ranges dedans.
- Un projet collectif rencontre dans ce contexte est place a l'interieur.

### 2) URL projet collectif directe (avec auteur unique)

- Le dossier du projet est cree a la racine avec le format : `[Auteur] - [Projet]`.
- La racine du projet contient les metadonnees (cover, `description.txt`, JSON).
- Chaque livre du projet a son propre sous-dossier.

### 3) URL projet collectif directe (sans auteur, ex: Bible)

- Le dossier du projet est cree a la racine avec le nom du projet uniquement.
- Chaque livre du projet a son propre sous-dossier.

### 4) URL livre direct

- Le dossier du livre est cree a la racine avec le format : `[Auteur] - [Titre]`.
- Il contient l'audio et les metadonnees.

### 5) Projets imbriques

Certains projets collectifs contiennent d'autres projets collectifs (ex: "Les Aventures de Sherlock Holmes" contient "La Vallee de la peur").

- Les projets imbriques sont places dans le dossier du projet parent.
- Ils utilisent uniquement le nom du projet (sans prefixe auteur) : `[Parent]/[ProjetImbrique]/[Livre]`.

### 6) Projets collectifs multi-auteurs ("Auteurs divers")

Certains projets collectifs regroupent des oeuvres de plusieurs auteurs (ex: "Des trains a ne pas rater", "Go West !", "Voyage a Marseille").

- Ces projets restent dans le dossier de leur contexte parent (auteur/lecteur/membre).
- L'auteur est enregistre comme "Auteurs divers" dans les metadonnees.
- Chaque livre garde son auteur d'origine dans les metadonnees JSON.

## Exemple d'arborescence

```text
dl/
  Alexandre Dumas - Le Comte de Monte-Cristo (Oeuvre integrale)/
    description.txt
    Le Comte de Monte-Cristo (Oeuvre integrale).json
    cover.jpg
    Le Comte de Monte-Cristo (Tome 1)/
      ...mp3
    Le Comte de Monte-Cristo (Tome 2)/
      ...mp3
  Arthur Conan Doyle/                                    <-- depuis page auteur
    Go West !/                                           <-- projet multi-auteurs (reste dedans)
      La Capture du feu/
      La Vallee du desespoir/
    La Bande mouchetee/
  Arthur Conan Doyle - Les Aventures de Sherlock Holmes (Oeuvre integrale)/
    La Vallee de la peur (Oeuvre integrale)/   <-- projet imbrique
      La Vallee de la peur (Episode 1)/
      La Vallee de la peur (Episode 2)/
    Le Chien des Baskerville/
    Une etude en rouge/
  Jacques Bainville - Histoire de France/
    cover.jpg
    description.txt
    Histoire de France.json
    ...mp3
```

## Ce que le scraper gere explicitement

- Pagination des pages auteur / voix / membre.
- Projets collectifs qui sont en realite des collections de livres.
- Listes de pistes chargees 10 par 10 via un bouton "voir plus" (loop-more).
- Traitement sequentiel des projets : chaque projet est entierement scrape et telecharge avant de passer au suivant.
- Retry automatique en cas d'echec de telechargement (jusqu'a 3 tentatives avec logs).
- Detection des doublons avec `--no-duplicates` : cree des raccourcis au lieu de re-telecharger.

Si une page contient plus de 10 pistes, l'outil appelle l'endpoint interne qui charge la suite, afin d'obtenir la liste complete des pistes.

## Logs et rapports generes

Selon les options, vous pouvez voir apparaitre:

- `litteratureaudio.log` : log detaille (debug).
- `dry-run-report.log` : rapport lisible du dry-run.
- vos rapports optionnels (`--summary-report`, `--csv-report`).

Ces fichiers peuvent etre supprimes sans risque apres execution.

## Structure du code

Le projet est organise en sous-packages clairs:

```
src/
├── app/                    # Couche application
│   ├── cli.py              # Interface ligne de commande
│   ├── pipeline.py         # Point d'entree principal (run_pipeline)
│   ├── scraper.py          # Crawling des URLs et extraction des metadonnees
│   ├── downloader_pipeline.py  # Logique de telechargement et arborescence
│   ├── constants.py        # Constantes partagees (ItemExtra, FolderPaths)
│   ├── registry.py         # Registres thread-safe pour deduplication
│   └── ...
├── core/                   # Modeles et utilitaires
├── infra/                  # HTTP, parsing, telechargement
└── report/                 # Rapports et exports
```

Point d'entree:

```bash
python main.py ...
```

## Utilisation responsable

- Utilisez `--sleep` pour eviter de surcharger le site.
- Commencez par `--dry-run` sur un petit echantillon.
- Gardez `litteratureaudio.log` pour diagnostiquer un probleme.
