# UKMFolioPuller

Monitor UKMFolio (Moodle) for new/changed assignments, quizzes, and forum discussions (e.g. class announcements), and get notified via Telegram.

## What gets monitored

| Source | How it is pulled | What triggers a notification |
| ------ | ---------------- | ---------------------------- |
| Assignments / quizzes | Moodle AJAX `core_calendar_get_action_events_by_courses` | New item, or changed title / deadline |
| Forum discussions (announcements, replacement-class posts, etc.) | HTML scrape of course and forum pages + AJAX `mod_forum_get_discussion_posts` for the root post | New discussion, or changed subject / post-creation timestamp |

Forum **body text** is fetched and stored (in the `item_body` column of
`tbl_forum_discussions`) but is intentionally excluded from change detection —
so when a teacher edits the wording of an existing announcement you will not
be re-notified. New discussions and subject-line edits still alert.

## Setup

1. Install dependency:
   ```bash
   pip install requests
   ```

2. Edit `config.json`:
   ```json
   {
       "username": "your_matric_number",
       "password": "your_password",
       "base_url": "https://ukmfolio.ukm.my",
       "sso_url": "https://sso.ukm.my",
       "telegram_bot_token": "your_bot_token",
       "telegram_target_user_uuid": ["your_chat_id", "another_chat_id"],
       "filter": {
           "mode": "Default",
           "whitelist": [],
           "blacklist": []
       },
       "listen_filed": ["Quiz", "Assignment", "Form"]
   }
   ```

   > `listen_filed` is optional — omit it to monitor all three types. See
   > the "Type filter" subsection below for the full rule set.

   ### Telegram targets

   `telegram_target_user_uuid` is an **array** of chat-id strings. When
   `--tgbot` is used, every notification is delivered to every chat id in the
   list. A failure on one target does not block delivery to the others.

   ### Title filter

   The `filter` block controls which items (by `item_title`) are allowed
   through to change detection and notification. Both `--tgbot` runs and
   `--check` runs apply the same filter. The filter runs against the title
   of assignments/quizzes and of forum discussions alike (forum body text
   is never matched). Whitelist/blacklist entries are **regular expressions**
   (a plain substring works too).

   Modes:

   | Mode        | Behavior                                                                                          |
   | ----------- | ------------------------------------------------------------------------------------------------- |
   | `Default`   | Pass if title matches any whitelist rule; drop if it matches any blacklist rule; otherwise pass.  |
   | `BlackList` | Pass by default; drop only if title matches any blacklist rule.                                   |
   | `WhiteList` | Drop by default; pass only if title matches any whitelist rule.                                   |
   | `Disabled`  | Pass everything, no rules applied.                                                                |

   Example — only notify for items belonging to your class, explicitly
   excluding another class's assignments:

   ```json
   "filter": {
       "mode": "Default",
       "whitelist": ["TTTM2213", "Group\\s*A"],
       "blacklist": ["Group\\s*B", "Kelas\\s*2"]
   }
   ```

   ### Type filter (`listen_filed`)

   Optional. Controls **which kinds of items** are monitored at all. A
   string array; each entry is one of `"Quiz"`, `"Assignment"`, `"Form"`.
   Excluded streams are not fetched (so excluding `Form` also saves the
   HTML-scrape round-trips).

   | Config                                            | Behavior                                         |
   | ------------------------------------------------- | ------------------------------------------------ |
   | field omitted                                     | monitor everything (default)                     |
   | `["Quiz", "Assignment", "Form"]`                  | monitor everything (same as default)             |
   | `["Form"]`                                        | only forum discussions; assignments/quizzes skipped |
   | `["Quiz", "Assignment"]`                          | only action events; forums skipped               |
   | `[]` (empty array)                                | falls back to default, emits `[WARN]`            |
   | not an array (string/object/…)                    | falls back to default, emits `[WARN]`            |
   | contains typo (e.g. `["Quiz", "Foro"]`)           | the bad entry is ignored with `[WARN]`, the rest applies |
   | every entry is invalid (e.g. `["Foo", "Bar"]`)    | falls back to default, emits `[WARN]`            |

   All misconfigurations are logged as `[WARN]` lines at the start of the
   run so silent misbehavior is not possible.

   Example — only care about forum announcements:

   ```json
   "listen_filed": ["Form"]
   ```

   Note on switching: excluded types keep their existing rows in the
   database untouched, so turning a type back on later will NOT re-notify
   you about already-seen items.

## Usage

```bash
# First run — populate database (both assignments/quizzes AND forum
# discussions) without sending notifications
python main.py --initct

# Normal run — detect changes and print to stdout
python main.py

# Normal run with Telegram notifications
python main.py --tgbot

# Check upcoming deadlines (within 7 days); forum posts are excluded from
# this view because their stored date is the post creation time, not a
# future due date
python main.py --check
```

On the first `--initct` run, expect two "new" batches in the log: one for
assignments/quizzes (from the calendar AJAX endpoint) and one for forum
discussions (from the HTML-scrape + per-discussion AJAX pipeline). Forum
sync adds ~(#courses + #forums + #discussions) HTTP round-trips per run,
which is fine for a 15–30 minute cron cadence.

## Scheduled Execution

This program is designed to run as a periodic job rather than a long-running daemon. Use `cron` (Linux) or Task Scheduler (Windows) to run it at your preferred interval.

**Example crontab (every 30 minutes):**
```bash
crontab -e
```
```
*/30 * * * * cd /path/to/UKMFolioPuller && /path/to/python main.py >> checker.log 2>&1
```

## Deploying as a Linux systemd Service

Since this program is a one-shot job (run and exit), use a **systemd timer** instead of a long-running service.

### Single Account

1. Create the service unit `/etc/systemd/system/ukmfolio.service`:

   ```ini
   [Unit]
   Description=UKMFolioPuller - check for assignment updates
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=oneshot
   WorkingDirectory=/path/to/UKMFolioPuller
   ExecStart=/path/to/python main.py --tgbot
   User=youruser
   ```

2. Create the timer unit `/etc/systemd/system/ukmfolio.timer`:

   ```ini
   [Unit]
   Description=Run UKMFolioPuller every 30 minutes

   [Timer]
   OnBootSec=2min
   OnUnitActiveSec=30min

   [Install]
   WantedBy=timers.target
   ```

3. Enable and start:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now ukmfolio.timer

   # Check status
   systemctl status ukmfolio.timer
   systemctl list-timers | grep ukmfolio

   # View logs
   journalctl -u ukmfolio.service -f
   ```

### Multiple Accounts

The program reads `config.json` and `ukmfolio.db` from the script directory (`Path(__file__).parent`). To run multiple accounts, create separate copies of the project, each with its own config and database.

1. Set up per-account directories:

   ```bash
   # Copy project for each account
   cp -r /path/to/UKMFolioPuller /opt/ukmfolio/alice
   cp -r /path/to/UKMFolioPuller /opt/ukmfolio/bob

   # Edit each account's config
   vim /opt/ukmfolio/alice/config.json
   vim /opt/ukmfolio/bob/config.json

   # Initialize each account's database
   cd /opt/ukmfolio/alice && python main.py --initct
   cd /opt/ukmfolio/bob && python main.py --initct
   ```

2. Create a **template** service unit `/etc/systemd/system/ukmfolio@.service`:

   ```ini
   [Unit]
   Description=UKMFolioPuller for account %i
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=oneshot
   WorkingDirectory=/opt/ukmfolio/%i
   ExecStart=/path/to/python main.py --tgbot
   User=youruser
   ```

3. Create a **template** timer unit `/etc/systemd/system/ukmfolio@.timer`:

   ```ini
   [Unit]
   Description=Run UKMFolioPuller every 30 minutes for account %i

   [Timer]
   OnBootSec=2min
   OnUnitActiveSec=30min
   # Randomize to avoid all accounts hitting the server at the same time
   RandomizedDelaySec=60

   [Install]
   WantedBy=timers.target
   ```

4. Enable each account:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now ukmfolio@alice.timer
   sudo systemctl enable --now ukmfolio@bob.timer

   # Check status
   systemctl list-timers | grep ukmfolio

   # View logs for a specific account
   journalctl -u ukmfolio@alice.service -f
   ```

5. To add a new account later, just copy the directory and enable a new timer:

   ```bash
   cp -r /opt/ukmfolio/alice /opt/ukmfolio/charlie
   vim /opt/ukmfolio/charlie/config.json
   cd /opt/ukmfolio/charlie && python main.py --initct
   sudo systemctl enable --now ukmfolio@charlie.timer
   ```
