# Gmail Cleanup

A CLI tool that connects to your Gmail via the official Gmail API and performs cleanup operations.

> This is the Python implementation. There is also an [Apps Script version](gmail_script/apps_scripts/Cleanup.gs) that runs inside your Google account without any local setup.

## Features

1. **Delete non-starred** — trashes everything except starred emails.
2. **Delete non-important** — trashes everything except Gmail's auto-"important" emails.
3. **Delete non-starred & non-important** — trashes everything that has neither star nor important flag.
4. **Delete all** — trashes your entire inbox across all categories.
5. **Delete by time** — trashes emails older than a given threshold (`7d`, `1y`, `6m`, etc).
6. **Delete by sender** — trashes emails from specific senders/domains you choose.
7. **Report** — no deletion; lists every sender domain with a count so you can decide what to target.

All modes sweep every inbox tab (Primary, Promotions, Social, Updates, Forums) — no category filter, so tab placement doesn't protect an email.

Deleted threads go to Gmail's Trash, recoverable for 30 days. No permanent deletion.

## Prerequisites

- Python 
- A Google Cloud Project with the Gmail API enabled (see setup)

## Google Cloud Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or select an existing one).
3. Enable the **Gmail API** for that project.
4. Configure the **OAuth consent screen** (External, testing mode is fine for personal use).
5. Create **OAuth Client ID** credentials, type "Desktop app". Download as `credentials.json`.
6. Place `credentials.json` in this directory (it is gitignored, safe).

## Installation

```bash
# Clone the repo
git clone <repo-url>
cd gmail-cleanup

# Install dependencies
pip install -r requirements.txt
```

## Usage

Run the tool via the `gmail-cleanup` command.

First run — **always test with report or dry-run first**:

```bash
# Generate a report of all senders and their counts
gmail-cleanup report

# Dry-run: see what would be deleted without actually deleting
gmail-cleanup clean --mode non_starred --dry-run
gmail-cleanup clean --mode by_time --time 30d --dry-run
```

When you're ready to delete:

```bash
# Delete everything except starred emails
gmail-cleanup clean --mode non_starred --no-dry-run

# Delete everything older than 7 days
gmail-cleanup clean --mode by_time --time 7d --no-dry-run

# Delete from specific senders
gmail-cleanup clean --mode by_sender --senders classroom.google.com,noreply@x.com --no-dry-run
```

Use a config file instead of CLI flags:

```bash
gmail-cleanup clean --config myconfig.yaml
```

**Safety**: `--dry-run` is always the default. You must explicitly pass `--no-dry-run` to perform deletion.

## Config File

Copy `config.example.yaml` to `config.yaml` and edit:

```yaml
mode: report
time_threshold: "30d"
sender_list: []
dry_run: true
credentials_path: "credentials.json"
token_path: "token.json"
```

CLI flags override config file values. Safety-critical flags (`--dry-run`) always default to `true`.

## Audit Trail

Every deletion batch is logged to `cleanup.log` with timestamp, query used, and count.

## Scheduled Cleanup (Optional)

A GitHub Actions workflow is provided in `.github/workflows/scheduled-cleanup.yml` for unattended daily cleanup. This requires storing a refresh token as the `GMAIL_REFRESH_TOKEN` repository secret. See the workflow file for details.

## Security

- `credentials.json`, `token.json`, and `config.yaml` are gitignored — never committed.
- CI checks for accidentally committed secrets and fails the build if found.
- Only `gmail.modify` scope is requested (read + trash). No `compose` or `settings` scopes.

## Related

- [Apps Script version](gmail_script/apps_scripts/Cleanup.gs) — runs entirely inside Google, no local setup needed.
- go to script.google.com 
- create a new project
- replace the content of the project with the one inside gmail_script/apps_scripts/Cleanup.gs
- To the right of the debug button, you will find the option to run different functions. 
- when you are ready set `DRY_RUN = false` and click on Run function.