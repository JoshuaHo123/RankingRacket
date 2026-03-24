# RankingRacket

RankingRacket is a Python-based data pipeline for collecting college ranking lists from public ranking websites, standardizing the results, and matching each ranked school to a canonical `UnitId` from the MascotGo/Atlas reference data.

The project was built to turn messy ranking pages into analysis-ready CSV outputs. It supports both metadata collection for each ranking list and row-level extraction of ranking entries, with a review step for unmatched schools before the final dataset is saved.

## What This Project Does

At a high level, the pipeline:

1. Takes one or more ranking URLs.
2. Infers list metadata such as publisher, category, and list name.
3. Scrapes ranking rows from each site.
4. Extracts rank, school name, score, and tie information.
5. Matches school names against Atlas reference files such as `CollegeAliases.csv`, `CollegeNamePreferences.csv`, `CollegeSlugPreferences.csv`, and `HistoricalUrbanColleges.csv`.
6. Saves both final combined outputs and per-list review files.

The current implementation includes site-specific scraping behavior for sources such as:

- Forbes
- U.S. News
- Princeton Review
- Niche
- QS / TopUniversities
- Times Higher Education
- ShanghaiRanking / ARWU
- College Consensus
- Mastersportal

## Project Structure

- [Pipeline.py](/Users/joshuaho/Desktop/MascotGo/Pipeline.py): Main orchestration script. Builds metadata and ranking-entry tables.
- [scraper.py](/Users/joshuaho/Desktop/MascotGo/scraper.py): Scraping engine using `requests`, `BeautifulSoup`, and Playwright for JavaScript-heavy pages.
- [siteMetadata.py](/Users/joshuaho/Desktop/MascotGo/siteMetadata.py): Infers publisher, category, list name, and access metadata from a ranking URL.
- [requirements.txt](/Users/joshuaho/Desktop/MascotGo/requirements.txt): Python dependencies.
- [ranking_lists.csv](/Users/joshuaho/Desktop/MascotGo/ranking_lists.csv): Output table with one row per ranking list.
- [ranking_entries.csv](/Users/joshuaho/Desktop/MascotGo/ranking_entries.csv): Output table with one row per ranked institution.
- [ranking_entries_parts](/Users/joshuaho/Desktop/MascotGo/ranking_entries_parts): Per-URL output files plus unmatched-only review files.
- [AtlasDatabase/data](/Users/joshuaho/Desktop/MascotGo/AtlasDatabase/data): Reference data used for school matching and normalization.

## Inputs

The main runtime input is the list of ranking URLs hardcoded near the bottom of [Pipeline.py](/Users/joshuaho/Desktop/MascotGo/Pipeline.py).

Example:

```python
urls = [
    "https://www.forbes.com/value-colleges/list/#tab:rank",
]
```

The matching process also depends on reference CSV files in `AtlasDatabase/data`, especially:

- `CollegeAliases.csv`
- `CollegeNamePreferences.csv`
- `CollegeSlugPreferences.csv`
- `HistoricalUrbanColleges.csv`
- `Countries.csv`
- `States.csv`

## Outputs

### 1. `ranking_lists.csv`

One row per ranking list, with columns:

- `ListID`
- `Publisher`
- `ListName`
- `Category`
- `Year`
- `Year Collected/Accessed`
- `URL`
- `List Bias/ Weight`

### 2. `ranking_entries.csv`

One row per ranked school, with columns:

- `ListId`
- `UnitId`
- `Rank`
- `Score`
- `IsTied`
- `RawName`
- `Match Method`
- `Match Source CSV`
- `Match Confidence`

### 3. `ranking_entries_parts/`

For each URL, the pipeline writes:

- A full per-list extracted file
- An `_unmatched` file containing only rows that could not be matched to a `UnitId`

This makes it easier to manually review mismatches and rerun or edit before finalizing the combined output.

## How Matching Works

The pipeline does more than exact string matching. It tries several increasingly flexible strategies:

- Exact match
- Normalized match
- Variant match
- Token-sorted match
- Fuzzy match

Each final row includes:

- `Match Method`: how the school name was matched
- `Match Source CSV`: which reference source supplied the match
- `Match Confidence`: confidence score for the match

If no match is found, the row is marked `UNMATCHED` and written to the unmatched review file.

## How To Run The Project

### 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright browser binaries

```bash
playwright install chromium
```

### 4. Edit the ranking URLs you want to scrape

Update the `urls` list at the bottom of [Pipeline.py](/Users/joshuaho/Desktop/MascotGo/Pipeline.py).

### 5. Run the pipeline

```bash
python3 Pipeline.py
```

## Interactive Workflow

The script currently runs as an interactive workflow rather than a command-line tool with flags.

During execution it will prompt for:

- Metadata confirmation or overrides
- Ranking year
- List bias / weight
- Whether unmatched rows should be kept, dropped, or reviewed after inspecting the generated per-list CSVs

This means the expected workflow is:

1. Run `python3 Pipeline.py`
2. Confirm or edit metadata for each ranking list
3. Review any unmatched rows in `ranking_entries_parts/`
4. Choose whether to keep, drop, or use edited rows (probably gonna remove this part since it requires a lot of human parsing and editing)
5. Use the final `ranking_lists.csv` and `ranking_entries.csv` outputs

## Notes And Limitations

- The pipeline is optimized around the current HTML structures of supported ranking sites, so scraper logic may need updates when sites change.
- Some sources are JavaScript-heavy and require Playwright rather than plain HTTP requests.
- A few extracted rows can still be noisy, duplicated, or unmatched depending on the source page.
- URLs are currently configured directly in code instead of being passed as CLI arguments or config.
- The `RankingRacket/` directory exists, but the current runnable project files live at the repository root.

## Suggested Next Improvements

If this project is handed off or extended later, the most useful improvements would be:

- Move URL input into a config file or CLI arguments
- Add a non-interactive mode for batch runs
- Add automated tests for matching logic and per-site extraction
- Log run summaries such as matched vs. unmatched rates by source
- Add a dedicated export folder for outputs by run date

## Summary

This project captures the work of building a reusable college-ranking ingestion pipeline: scrape ranking pages, normalize the results, resolve each school to a canonical institutional ID, and save clean CSVs that can be used downstream in MascotGo.
