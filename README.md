# UKMFolio Checker

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
*/30 * * * * cd /path/to/UKMFolioChecker && /path/to/python main.py >> checker.log 2>&1
```
