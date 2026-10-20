# Third-party notices

## Contact extraction modules

- Upstream project: https://github.com/omkarcloud/website-email-contact-scraper
- Upstream license: MIT, Copyright (c) 2024-2025 Chetan Jain.
- Affected directory: `scripts/contact_core/`.
- License text: [LICENSE](LICENSE).

The bundled modules were carried over from an earlier local adaptation of the upstream project. They retain the extraction logic and comments used by that adaptation, including HTML text processing, email decoding and filtering, phone extraction, and social profile matching. The exact upstream source commit was not recorded; this release does not claim to match the latest upstream revision.

The skill instructions, command-line workflow, directory adapters, enrichment workflow, export handling and tests are distributed with this project. This repository is not the upstream project's web application and does not include its frontend or technology detection service.

Python dependencies listed under `scripts/requirements*.txt` are installed separately and retain their own licenses. They are not vendored in the download.
