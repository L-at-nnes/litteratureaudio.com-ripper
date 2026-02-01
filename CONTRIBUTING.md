# Contributing

Thanks for contributing. The top priority is reliability on
litteratureaudio.com, without breaking extraction or download behavior.

## Non-negotiable rules

- Do not change the extraction / download method if it already works, unless
  you have a proven bug.
- Prefer behavior-preserving refactors.
- Any change to folder layout, naming, or reports must be documented in the
  README.
- Keep the load on the site reasonable (use `--sleep`).

## Local setup

Example with a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Recommended workflow

1) Reproduce on a small sample with `--dry-run`.
2) Modify the code.
3) Re-test with `--dry-run`.
4) Run a real download only if needed, then clean artifacts.

## Minimum checks before proposing changes

### 1) Quick compilation check

```bash
python -m py_compile main.py src\app\cli.py src\app\pipeline.py src\app\scraper.py src\app\downloader_pipeline.py src\app\constants.py src\app\registry.py src\app\verify.py src\app\logging_utils.py src\infra\http.py src\infra\downloader.py src\infra\parser.py src\report\export.py src\report\reporting.py src\core\models.py src\core\utils.py
```

### 2) Short dry-run (no download)

```bash
python main.py --dry-run --threads 1 --sleep 0.5 https://www.litteratureaudio.com/livre-audio-gratuit-mp3/luigi-pirandello-bonheur.html
```

### 3) Folder verification (optional)

```bash
python main.py --verify dl
```

If you ran a real download, delete `dl/`, logs, and reports before delivering.

## Sensitive areas (do not break these)

When you touch scraping or the pipeline, explicitly verify:

- Track loading beyond the first 10 items (loop-more).
- Collective projects (root folder + book subfolders).
- **Multi-author collective projects** ("Auteurs divers" must go to independent folders).
- Grouping by author / reader / member.
- MP3-first then ZIP fallback in `--format default`.
- Windows-safe filename cleaning (forbidden characters, `:`).
- **Sommaire extraction thresholds** (70%/50% fallbacks for collection URLs).
- **Multi-version books** (URLs with `-version-N` get folder names with reader only: `Title (Reader)`).
- **ID3 tagging** (TPE1=reader, TCOM=author, TALB=album title).

### Folder naming conventions

- **Single album (direct URL):** `[Author] - [Title]` at output root.
- **Multi-version albums:** `[Title] (Reader)` for versioned URLs (all versions at same level).
- **Collective project with author (direct URL):** `[Author] - [Project]` at output root.
- **Collective project without author (e.g. Bible):** `[Project]` at output root.
- **Nested projects:** `[Author] - [ParentProject]/[NestedProject]/[Book]` (no author prefix on nested).
- **Author/reader/member listing:** `[Author]/[Book]` or `[Author]/[Project]/[Book]`.
- **Multi-author collective projects:** `Auteurs divers - [Project]` at output root (even when discovered from an author page).

### Sequential project processing

Projects are processed one at a time: all metadata is scraped, then all files are downloaded, before moving to the next project. Multithreading is used *within* a project, not *between* projects.

### Duplicate detection (`--no-duplicates`)

When enabled, the tool skips downloading if audio files already exist in the target folder. This checks for `.mp3`, `.zip`, `.m4a`, `.ogg` files on disk.

### Retry logic

Downloads retry up to 3 times on failure. Each retry is logged:
- `Retry (2/3) for [url]` before the attempt.
- `Download failed, will retry (1/3) for [url]: [error]` after failure.

## Code organization

The project is structured into clear subpackages:

```
src/
├── app/                    # Application layer
│   ├── cli.py              # Command-line interface and argument parsing
│   ├── pipeline.py         # Main entry point (run_pipeline)
│   ├── scraper.py          # URL crawling and metadata extraction
│   ├── downloader_pipeline.py  # Download logic and folder structure
│   ├── constants.py        # Shared constants and data classes
│   ├── registry.py         # Thread-safe deduplication registries
│   ├── verify.py           # --verify mode implementation
│   └── logging_utils.py    # Logger configuration
├── core/                   # Domain models and utilities
│   ├── models.py           # AudioItem, DownloadLink, Track
│   └── utils.py            # sanitize_filename, ensure_dir, etc.
├── infra/                  # Infrastructure (HTTP, parsing)
│   ├── http.py             # Session, rate limiting, fetch functions
│   ├── downloader.py       # File downloads, ID3 tagging, unzip
│   └── parser.py           # HTML parsing with BeautifulSoup
└── report/                 # Reporting and exports
    ├── export.py           # JSON and description export
    └── reporting.py        # Summary, CSV, dry-run reporters
```

Entry point:

```bash
python main.py ...
```

## Style and readability

- Code comments should be in English and genuinely useful.
- Avoid obvious comments. Focus on the subtle parts.
- Avoid duplication: reuse existing functions.
- Keep functions short and testable where possible.

## How to report a bug well

Please include:

- the exact command you ran,
- a relevant snippet from `litteratureaudio.log`,
- one or two URLs that clearly reproduce the issue,
- what you expected vs what happened.

## Quick checklist

Before proposing:

- [ ] `py_compile` passes.
- [ ] A short dry-run passes.
- [ ] Sensitive areas are verified if you touched them.
- [ ] The README is updated if visible behavior changes.
- [ ] No artifacts (`dl/`, logs, reports) remain in the repo.
