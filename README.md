# UKMFolioPuller

Monitor UKMFolio (Moodle) for new/changed assignments and quizzes, get notified via Telegram.

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
       "telegram_target_user_uuid": "your_chat_id"
   }
   ```

## Usage

```bash
# First run — populate database without sending notifications
python main.py --initct

# Normal run — detect changes and notify via Telegram
python main.py

# Check upcoming deadlines (within 7 days)
python main.py check
```

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
