# litteratureaudio.com ripper

[Lire en francais](README_fr.md)

![Version](https://img.shields.io/badge/version-2.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-beta-yellow)

**⚠️ Beta notice:** This version includes significant improvements to collection/sommaire extraction. Please report any issues: https://github.com/L-at-nnes/litteratureaudio.com-ripper/issues

Command-line tool to scrape and download audiobooks from litteratureaudio.com
with a clean, Windows-friendly folder layout and useful metadata exports.

It is designed to be robust against site quirks: collective projects, pagination,
tracks loaded 10-by-10 ("load more"), MP3 vs ZIP variants, multiple versions
(different readers), and inconsistent naming.

## Repository

- https://github.com/L-at-nnes/litteratureaudio.com-ripper

## Installation

Requirements: Python 3.10+ recommended.

```bash
pip install -r requirements.txt
```

## Quick Start

### Download a single book

```bash
python main.py https://www.litteratureaudio.com/livre-audio-gratuit-mp3/jules-verne-le-tour-du-monde-en-80-jours.html
```

### Download a full author page (polite settings)

```bash
python main.py https://www.litteratureaudio.com/livre-audio-gratuit-mp3/auteur/jules-verne --threads 4 --sleep 0.5 --format default
```

### Download from a text file

```bash
python main.py --txt audiobooks.txt --threads 4 --sleep 0.5 --format default
```

## CLI Reference

### Available Options

The table below covers every CLI option exposed by the tool.

| Option | Type / values | Default | Description | Example |
| --- | --- | --- | --- | --- |
| `URL ...` | one or more URLs | | Direct URL(s) to process | `python main.py https://.../book.html` |
| `--txt` | file path | | Text file (one URL per line, `#` ignored) | `python main.py --txt audiobooks.txt` |
| `--output` | folder path | `./dl` | Output root folder | `python main.py --output D:\Audio` |
| `--threads` | integer | `1` | Parallel downloads (1 = sequential) | `python main.py --threads 4 --txt audiobooks.txt` |
| `--sleep` | float (seconds) | `0` | Minimum delay between HTTP requests | `python main.py --sleep 0.5 --txt audiobooks.txt` |
| `--format` | `default`, `mp3`, `zip`, `mp3+zip`, `all`, `unzip` | `default` | Download policy | `python main.py --format mp3 --txt audiobooks.txt` |
| `--no-json` | flag | `false` | Do not export JSON metadata | `python main.py --no-json URL` |
| `--no-cover` | flag | `false` | Do not download covers | `python main.py --no-cover URL` |
| `--no-description` | flag | `false` | Do not write `description.txt` | `python main.py --no-description URL` |
| `--no-id3` | flag | `false` | Do not write ID3 tags | `python main.py --no-id3 URL` |
| `--max-pages` | integer | `0` (no limit) | Limit listing pagination (author / reader / member) | `python main.py --max-pages 2 URL_LISTING` |
| `--dry-run` | flag | `false` | Extract only, no audio written | `python main.py --dry-run --txt audiobooks.txt` |
| `--metadata-only` | flag | `false` | Write cover + description + JSON only | `python main.py --metadata-only URL` |
| `--summary-report` | JSON file path | | Write a summary report (default filename: `summary-report.json`) | `python main.py --summary-report --txt audiobooks.txt` |
| `--csv-report` | CSV file path | | Write a CSV for indexing (default filename: `report.csv`) | `python main.py --csv-report --txt audiobooks.txt` |
| `--verify` | folder path | | Re-scan a folder and report missing tracks/files | `python main.py --verify dl` |
| `--no-duplicates` | flag | `false` | Skip downloading if audio files already exist on disk | `python main.py --no-duplicates --txt audiobooks.txt` |
| `--no-log` | flag | `false` | Do not create log files | `python main.py --no-log --txt audiobooks.txt` |

### Useful Command Recipes

| Goal | Command |
| --- | --- |
| Single book | `python main.py https://www.litteratureaudio.com/livre-audio-gratuit-mp3/luigi-pirandello-bonheur.html` |
| Full author (polite) | `python main.py https://www.litteratureaudio.com/livre-audio-gratuit-mp3/auteur/alexandre-dumas --threads 4 --sleep 0.5 --format default` |
| URL list (normal) | `python main.py --txt audiobooks.txt --threads 4 --sleep 0.5 --format default` |
| URL list (dry-run) | `python main.py --dry-run --txt audiobooks.txt --threads 4 --sleep 0.5 --format default` |
| Metadata only | `python main.py --metadata-only --txt audiobooks.txt --threads 4 --sleep 0.5 --format default` |
| Dry-run + reports | `python main.py --dry-run --summary-report summary.json --csv-report library.csv --txt audiobooks.txt` |
| Verify existing output | `python main.py --verify dl` |

### Windows Console Encoding (UTF-8)

French text (accented characters like é, è, à, ê, œ) may display incorrectly in Windows PowerShell or CMD. The log file (`litteratureaudio.log`) is always correctly encoded in UTF-8.

To fix console display in **PowerShell**, run this before the script:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
python main.py ...
```

Or create a one-liner:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; python main.py --txt audiobooks.txt
```

To make it permanent in PowerShell, add to your `$PROFILE`:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

In **CMD**, run `chcp 65001` first (may require a font that supports Unicode).

## Folder Layout Rules (expected behavior)

Behavior depends on the type of starting URL.

### 1) Author / reader / member URLs

- A root folder is created with the author/reader/member name.
- All works are placed under that folder.
- Collective projects discovered in this context are nested inside that root.

### 2) Direct collective project URLs (with single author)

- The project folder is created at the output root with the format: `[Author] - [Project]`.
- The project root contains metadata (cover, `description.txt`, JSON).
- Each book inside the project gets its own subfolder.

### 3) Direct collective project URLs (no author, e.g. Bible)

- The project folder is created at the output root with the project name only.
- Each book inside the project gets its own subfolder.

### 4) Direct book URLs

- The book folder is created at the output root with the format: `[Author] - [Title]`.
- It contains the audio files and metadata.

### 5) Nested projects

Some collective projects contain other collective projects (e.g., "Les Aventures de Sherlock Holmes" contains "La Vallée de la peur").

- Nested projects are placed inside their parent project folder.
- They use only the project name (no author prefix): `[Parent]/[NestedProject]/[Book]`.

### 6) Multi-author collective projects ("Auteurs divers")

Some collective projects feature works by multiple authors (e.g., "Des trains à ne pas rater", "Go West !", "Voyage à Marseille").

- These projects stay inside their parent folder (author/reader/member context).
- The author is recorded as "Auteurs divers" in the metadata.
- Each book inside keeps its original author in the JSON metadata.

## Example Folder Tree

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
  Arthur Conan Doyle/                                    <-- from author listing
    Go West !/                                           <-- multi-author collective (stays inside)
      La Capture du feu/
      La Vallee du desespoir/
    La Bande mouchetee/
  Arthur Conan Doyle - Les Aventures de Sherlock Holmes (Oeuvre integrale)/
    La Vallee de la peur (Oeuvre integrale)/   <-- nested project
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

## Multi-version books

Some books exist in multiple versions (different readers).

- Versions are placed at the same level (no hierarchy).
- Folder names include the reader name: `[Title] (Reader)`.
- Example: `Nana (Pomme)` and `Nana (René Depasse)`.

## ID3 Tags

MP3 files are tagged with:
- **TIT2 (Title):** track title or audiobook title
- **TPE1 (Artist):** reader/narrator name
- **TCOM (Composer):** book author (the writer of the original work)
- **TALB (Album):** audiobook title
- **APIC (Cover):** embedded album art

## What the scraper explicitly handles

- Listing pagination (author / reader / member pages).
- Collective projects that are actually collections of books.
- Track lists that load 10-by-10 via a "load more" button (WordPress loop-more).
- Sequential project processing: each project is fully scraped and downloaded before moving to the next.
- Automatic retry on download failures (up to 3 attempts with logged retries).
- Duplicate detection with `--no-duplicates`: creates shortcuts instead of re-downloading.
- Multi-version book handling (same title with different readers).

If a page has more than 10 tracks, the tool calls the internal endpoint that loads the next track batches, so the full track list is captured.

## Logs and Generated Reports

Depending on the options you use, you may see:

- `litteratureaudio.log`: detailed debug log.
- `dry-run-report.log`: human-readable dry-run report.
- your optional reports (`--summary-report`, `--csv-report`).

These files can be safely deleted after a run.

## Code Structure

The codebase is organized into clean subpackages:

```
src/
├── app/                    # Application layer
│   ├── cli.py              # Command-line interface
│   ├── pipeline.py         # Main entry point (run_pipeline)
│   ├── scraper.py          # URL crawling and metadata extraction
│   ├── downloader_pipeline.py  # Download logic and folder structure
│   ├── constants.py        # Shared constants (ItemExtra, FolderPaths)
│   ├── registry.py         # Thread-safe deduplication registries
│   └── ...
├── core/                   # Domain models and utilities
├── infra/                  # HTTP, parsing, file downloads
└── report/                 # Reporting and exports
```

Entry point:

```bash
python main.py ...
```

## Responsible Use

- Use `--sleep` to avoid overloading the site.
- Start with `--dry-run` on a small sample.
- Keep `litteratureaudio.log` when diagnosing issues.
