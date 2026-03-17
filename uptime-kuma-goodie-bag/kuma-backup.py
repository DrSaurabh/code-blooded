#!/usr/bin/env python3
"""
kuma-backup.py
v 1.6.0 dated 23 Feb 2026
This script creates a consistent snapshot of the Uptime Kuma SQLite database and uploads it to an S3 bucket.
"""
#!/usr/bin/env python3
import os
import subprocess
import sqlite3
import sys
import json
import urllib.request
from pathlib import Path

# Configuration
AWS_SECRET_NAME = "kuma-secret"
DB_PATH = "/opt/kuma-data/kuma.db"
BACKUP_TEMP = "/tmp/kuma_snapshot.db"
BUCKET_NAME = os.getenv('BACKUP_BUCKET_NAME')

# Systemd configurations
SERVICE_PATH = Path("/etc/systemd/system/kuma-backup.service")
TIMER_PATH = Path("/etc/systemd/system/kuma-backup.timer")
SERVICE_TEMPLATE = """[Unit]
Description=Kuma Backup
After=network.target

[Service]
Type=oneshot
User={user}
WorkingDirectory={work_dir}
Environment="BACKUP_BUCKET_NAME={bucket}"
ExecStart=/usr/bin/python3 {script_path} --now
"""
TIMER_TEMPLATE = """[Unit]
Description=Daily Kuma Backup

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
"""

def run_command(command, capture=True):
    """Run a command with sudo and return result"""
    full_cmd = f"sudo {command}" if not command.startswith('sudo') else command
    try:
        result = subprocess.run(full_cmd,
                                shell=True,
                                check=True,
                                capture_output=capture,
                                text=True)
        return result.stdout.strip() if capture else None
    except subprocess.CalledProcessError as e:
        if capture:
            print_error(e.stderr.strip() if e.stderr else str(e))
        return None
def get_aws_region():
    """Detects AWS region using IMDSv2."""
    try:
        token_url = "http://169.254.169.254/latest/api/token"
        req = urllib.request.Request(token_url, method='PUT')
        req.add_header("X-aws-ec2-metadata-token-ttl-seconds", "60")
        with urllib.request.urlopen(req, timeout=2) as response:
            token = response.read().decode('utf-8')

        az_url = "http://169.254.169.254/latest/meta-data/placement/availability-zone"
        req = urllib.request.Request(az_url)
        req.add_header("X-aws-ec2-metadata-token", token)
        with urllib.request.urlopen(req, timeout=2) as response:
            return response.read().decode('utf-8')[:-1]
    except:
        return "us-east-1"
def get_slack_details():
    """Fetch Slack details from Secrets Manager."""
    region = get_aws_region()
    cmd = ["aws", "secretsmanager", "get-secret-value", "--secret-id", AWS_SECRET_NAME, "--region", region, "--query", "SecretString", "--output", "text"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except:
        return None
def send_slack_alert(error_message):
    """Sends a formatted Slack Block notification on failure."""
    details = get_slack_details()
    if not details:
        print("Could not fetch Slack details for alerting.")
        return
    payload = {
        "channel": details.get("channel"),
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Uptime Kuma Backup Failed"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Error:* {error_message}"}
            }
        ]
    }

    try:
        req = urllib.request.Request(details['webhook'], data=json.dumps(payload).encode('utf-8'))
        req.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Failed to send Slack alert: {e}")
def run_backup():
    if not os.path.exists(DB_PATH):
        msg = "Source database file not found."
        print(msg)
        send_slack_alert(msg)
        return

    try:
        if os.path.exists(BACKUP_TEMP): os.remove(BACKUP_TEMP)
        # Consistent snapshot
        conn = sqlite3.connect(DB_PATH)
        conn.execute(f"VACUUM INTO '{BACKUP_TEMP}'")
        conn.close()
        # Upload to S3
        subprocess.run(["aws", "s3", "cp", BACKUP_TEMP, f"s3://{BUCKET_NAME}/kuma.db"], check=True)
        print("Backup uploaded to S3.")
    except Exception as e:
        error_msg = str(e)
        print(f"Backup failed: {error_msg}")
        send_slack_alert(error_msg)
    finally:
        if os.path.exists(BACKUP_TEMP): os.remove(BACKUP_TEMP)
def write_service_files():
    """Write systemd service and timer files"""
    script_path = os.path.abspath(__file__)
    work_dir = os.path.dirname(script_path)
    user = "ec2-user"
    # Write service file
    svc_content = SERVICE_TEMPLATE.format(
        work_dir=work_dir,
        script_path=script_path,
        bucket=BUCKET_NAME,
        user=user
    )
    run_command(f"echo '{svc_content}' | sudo tee {SERVICE_PATH} > /dev/null")
    # Write timer file
    run_command(f"echo '{TIMER_TEMPLATE}' | sudo tee {TIMER_PATH} > /dev/null")
def install_timer():
    write_service_files()
    run_command("systemctl daemon-reload", capture=False)
    run_command("systemctl enable --now kuma-backup.timer", capture=False)
    run_command(f"systemctl restart {TIMER_PATH.name}", capture=False)
if __name__ == "__main__":
    if "--now" in sys.argv:
        run_backup()
    else:
        install_timer()
        run_backup()