# Charusat Results Fetcher

## This project is a Python-based reverse-engineering and data collection tool built as part of an academic task to analyze the CHARUSAT University Examination Result Portal.

### The goal of the project is not exploitation, but to study:
    authentication gaps
    rate-limiting behavior
    backend performance under concurrent access
    feasibility of bulk data enumeration
    impact on data privacy and availability
    All testing was done in a controlled and limited manner, strictly within the scope of a college-assigned challenge.

## Disclaimer

    This project is created solely for educational and academic purposes.
    No vulnerabilities were exploited beyond what was required to demonstrate impact.
    Concurrency was intentionally capped to avoid denial-of-service behavior.
    The tool does not bypass authentication mechanisms because none are implemented on the target endpoint.
    Do not use this code against systems you do not own or have permission to test.

## Features
    Arrow-key based terminal UI (↑ ↓ Enter)
    Fully automated ASP.NET WebForms navigation
    Single result fetch (for validation)
    Bulk result download with bounded concurrency
    Safe parallel execution using thread pools
    HTML result archival
    CSV export (Roll No vs SGPA vs Credits)
    Automatic highest-SGPA detection
    Linux-native (no Selenium, no headless browser)

## Requirements

    Python 3.9+
    Linux terminal (required for curses)
    Internet access
```bash
Python Dependencies
pip install requests beautifulsoup4
```

## How It Works (High Level)

    The CHARUSAT result portal is built using ASP.NET WebForms, which relies on:
    __VIEWSTATE
    __EVENTTARGET
    server-side control state
    This script:

        Mimics browser behavior using requests
        Walks the WebForms POST chain step-by-step
        Extracts valid hidden fields on every request
        Submits enrollment numbers programmatically
        Parses result data from returned HTML
        No cached or replayed state is used.
        Each request follows the same flow as a legitimate browser session.

## Usage
Run the script in a real terminal:

```bash
python main.py
```

    Navigation
        Use ↑ ↓ to move
        Press Enter to select

    Modes
        1. Single Result
            Enter full enrollment number (e.g. 25CE099)
            Fetches and saves one result
            Useful for verification

        2. Bulk Download
            Enter roll prefix (e.g. 25CE)
            Automatically generates roll numbers (25CE001, 25CE002, …)
            Downloads results concurrently

    Generates:

    HTML files
    sgpa_summary.csv
    Highest SGPA summary in terminal

## Configuration

    Inside charusat_final.py:
    MAX_WORKERS = 3    # Recommended: 2–3
    ROLL_LIMIT = 150   # Upper bound for roll numbers

    Concurrency is intentionally limited to avoid stressing the server.

## Observations & Findings

    From controlled testing:
        No authentication or authorization is enforced
        Any user can fetch any student’s result using only the enrollment number
        No HTTP-level rate limiting was observed
        Backend serializes result generation, causing high response latency under concurrency
        Lack of throttling combined with backend queuing presents availability risks
        These findings were derived without aggressive traffic generation.

## Suggested Mitigations (High Level)

    For the institution:
        Enforce authentication before result access
        Bind results to authenticated student accounts
        Implement rate limiting and request throttling
        Add anomaly detection for enumeration patterns
        Use CAPTCHA or secondary verification for repeated access