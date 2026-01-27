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
python -m py_compile main.py src\app\cli.py src\app\pipeline.py src\app\verify.py src\app\logging_utils.py src\infra\http.py src\infra\downloader.py src\infra\parser.py src\report\export.py src\report\reporting.py src\core\models.py src\core\utils.py
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
- Grouping by author / reader / member.
- MP3-first then ZIP fallback in `--format default`.
- Windows-safe filename cleaning (forbidden characters, `:`).

## Code organization

The project is structured into clear subpackages:

- `src/app/`: CLI, pipeline, verification, logging.
- `src/core/`: models and utilities.
- `src/infra/`: HTTP, link resolution, HTML parsing.
- `src/report/`: exports and reporting.

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
