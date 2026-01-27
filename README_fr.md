# Ripper litteratureaudio.com

[Read in English](README.md)

![Version](https://img.shields.io/badge/version-2.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Licence](https://img.shields.io/badge/licence-MIT-green)
![Statut](https://img.shields.io/badge/statut-beta-yellow)

**Notice beta :** Ce projet est actuellement en beta. Au moindre bug, merci d'ouvrir une issue : https://github.com/L-at-nnes/litteratureaudio.com-ripper/issues

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

| Option | Type / valeurs | Description | Exemple |
| --- | --- | --- | --- |
| `URL ...` | une ou plusieurs URL | URL(s) directes a traiter | `python main.py https://.../livre.html` |
| `--txt` | chemin fichier | Fichier texte (une URL par ligne, `#` ignore) | `python main.py --txt audiobooks.txt` |
| `--output` | chemin dossier | Dossier racine de sortie (defaut: `./dl`) | `python main.py --output D:\Audio` |
| `--threads` | entier | Nombre de workers (defaut: `4`) | `python main.py --threads 4 --txt audiobooks.txt` |
| `--sleep` | float (secondes) | Delai minimum entre requetes HTTP | `python main.py --sleep 0.5 --txt audiobooks.txt` |
| `--format` | `default`, `mp3`, `zip`, `mp3+zip`, `all`, `unzip` | Politique de telechargement | `python main.py --format default --txt audiobooks.txt` |
| `--no-json` | flag | Ne pas exporter le JSON metadata | `python main.py --no-json URL` |
| `--no-cover` | flag | Ne pas telecharger les covers | `python main.py --no-cover URL` |
| `--no-description` | flag | Ne pas ecrire `description.txt` | `python main.py --no-description URL` |
| `--no-id3` | flag | Ne pas ecrire les tags ID3 | `python main.py --no-id3 URL` |
| `--max-pages` | entier | Limiter la pagination des listings (auteur / voix / membre) | `python main.py --max-pages 2 URL_LISTING` |
| `--dry-run` | flag | Extraction seule, sans ecriture audio | `python main.py --dry-run --txt audiobooks.txt` |
| `--metadata-only` | flag | Ecrit cover + description + JSON uniquement | `python main.py --metadata-only URL` |
| `--summary-report` | chemin JSON | Ecrit un resume (par auteur/projet + totaux) | `python main.py --summary-report summary.json --txt audiobooks.txt` |
| `--csv-report` | chemin CSV | Ecrit un CSV d'indexation | `python main.py --csv-report library.csv --txt audiobooks.txt` |
| `--verify` | chemin dossier | Re-scan un dossier et signale les manques | `python main.py --verify dl` |

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

### 2) URL projet collectif directe

- Le dossier du projet est cree a la racine de `--output`.
- La racine du projet contient les metadonnees (cover, `description.txt`, JSON).
- Chaque livre du projet a son propre sous-dossier.

### 3) URL livre direct

- Le dossier du livre est cree a la racine de `--output`.
- Il contient l'audio et les metadonnees.

## Exemple d'arborescence

```text
dl/
  Alexandre Dumas/
    Le Comte de Monte-Cristo (Oeuvre integrale)/
      description.txt
      Le Comte de Monte-Cristo (Oeuvre integrale).json
      cover.jpg
      Le Comte de Monte-Cristo (Tome 1)/
        ...mp3
      Le Comte de Monte-Cristo (Tome 2)/
        ...mp3
```

## Ce que le scraper gere explicitement

- Pagination des pages auteur / voix / membre.
- Projets collectifs qui sont en realite des collections de livres.
- Listes de pistes chargees 10 par 10 via un bouton "voir plus" (loop-more).

Si une page contient plus de 10 pistes, l'outil appelle l'endpoint interne qui charge la suite, afin d'obtenir la liste complete des pistes.

## Logs et rapports generes

Selon les options, vous pouvez voir apparaitre:

- `litteratureaudio.log` : log detaille (debug).
- `dry-run-report.log` : rapport lisible du dry-run.
- vos rapports optionnels (`--summary-report`, `--csv-report`).

Ces fichiers peuvent etre supprimes sans risque apres execution.

## Structure du code

Le projet est organise en sous-packages clairs:

- `src/app/` : CLI, pipeline, verification, logging.
- `src/core/` : modeles et utilitaires.
- `src/infra/` : HTTP, resolution des liens, parsing HTML.
- `src/report/` : exports et rapports.

Point d'entree:

```bash
python main.py ...
```

## Utilisation responsable

- Utilisez `--sleep` pour eviter de surcharger le site.
- Commencez par `--dry-run` sur un petit echantillon.
- Gardez `litteratureaudio.log` pour diagnostiquer un probleme.
