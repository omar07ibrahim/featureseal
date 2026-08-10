# Evidence lifecycle and reproduction

The files in this directory are generated from the real FeatureSeal CLI and the checked-in synthetic scenario. They are portfolio evidence, regression artifacts, and an auditable rendering contract—not hand-edited mockups.

## What is tracked

| Artifact | Source |
|---|---|
| <code>featureseal-receipt.json</code> | Installed CLI analysis of the reference snapshot |
| <code>featureseal-report.html</code> | Verified self-contained report renderer |
| <code>featureseal-cli.txt</code> | Exact analyze, verify, inspect, and report transcript |
| Desktop, full-page, and mobile PNGs | Chromium capture of that HTML |
| CLI PNG | Chromium capture of the exact transcript |
| Three-frame GIF | Real report header, findings, and receipt sections |
| Four SVG diagrams | Derived from receipt summary, events, findings, and digests |
| <code>featureseal-evidence.json</code> | Source, toolchain, dimensions, bytes, and SHA-256 manifest |

The manifest intentionally does not hash itself. It hashes every other evidence artifact plus every declared source input.

## Reproduce through the workflow

Open a pull request that changes any evidence input. The [FeatureSeal evidence workflow](../.github/workflows/evidence.yml) will:

1. derive the exact source revision and tree;
2. execute the installed application against <code>scenarios/late-feature-incident.json</code>;
3. capture browser artifacts without network access;
4. validate image dimensions, GIF frames, SVG structure, sensitive markers, source hashes, and receipt replay;
5. commit drift back to the same repository branch as Omar Ibrahim.

A forked pull request can run read-only validation but cannot receive an evidence write. On <code>main</code>, drift fails rather than mutating the protected branch.

## Local semantic reproduction

Browser output is intentionally produced in CI because its image, architecture, browser, Python, Playwright, and Pillow versions are pinned. The semantic artifacts can be reproduced locally:

    python -m pip install .
    featureseal analyze scenarios/late-feature-incident.json --output receipt.json
    featureseal verify receipt.json
    featureseal inspect receipt.json
    featureseal report receipt.json --output report.html

Compare the three reported digests with [the tracked transcript](evidence/featureseal-cli.txt).

## Pinned rendering contract

- container: <code>mcr.microsoft.com/playwright/python@sha256:51d31fdfacb0cff99a1a724152e34ae408d2bd4e7da310ff157450f49261cc59</code>
- platform: <code>linux/amd64</code>
- browser: Chromium 151.0.7922.34
- Playwright: 1.62.0
- Pillow: 12.3.0
- application Python: 3.14.6
- wheel downloader Python: 3.12.3
- browser network: disabled
- source mount: read-only

The image metadata is recorded in <code>requirements/evidence-browser-image.lock.json</code>. Python browser wheels and hashes are recorded in <code>requirements/evidence-browser.txt</code>.

## Updating evidence safely

Do not edit generated evidence by hand. Change the source, fixture, report, or generator in a focused commit and let the workflow regenerate the bundle. Review both the visual diff and manifest diff before merge.

When a visual legitimately changes, verify:

- the source revision reflects the intended source commit;
- summary counts and receipt digests changed only when semantic inputs changed;
- screenshots contain no secrets, local paths, usernames, or personal data;
- mobile and desktop text remains readable;
- diagrams still represent data present in the receipt;
- the full-page image captures every report section;
- all workflow checks pass on the post-generation branch head.

## Current reference result

The source-bound bundle currently proves:

    4 typed features
    18 events
    7 observations
    3 entities
    28 join cells
    22 exact matches
    6 findings, one per primary rule
    35 append-only ledger entries

Receipt SHA-256:

    ead8f767d0f8e8da4cca8a459a878319490eebadc4568d4bd04776c1758ee8ae
