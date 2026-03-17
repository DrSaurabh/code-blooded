#!/usr/bin/env python3
"""
kuma-setup.py
v 1.10.0 dated 19 Feb 2026
Injects monitors and notifications directly into the Uptime Kuma SQLite database.
This has been designed and tested specifically for use with Uptime Kuma docker image: louislam/uptime-kuma:2.0.2 
The script will fetch the Slack details and initial user information from AWS Secrets Manager and add it as a notification channel,
then create monitors based on a kuma-config.json file. This allows for fully automated setup without using the Uptime Kuma UI at all.
The script runs in an automated mode as part of the EC2 userdata, but also includes an interactive menu for manual execution and troubleshooting.
"""
import json
import os
import sqlite3
import subprocess
import urllib.request
import sys
from pathlib import Path
import time

# GLOBAL CONFIGURATION ----------------------------------
AWS_SECRET_NAME = "kuma-secret"    # name of the secret in AWS Secrets Manager containing the Slack webhook URL and channel
DB_FILE = "/opt/kuma-data/kuma.db" # path as created in the ec2 user-data
COMPOSE_SERVICE = "uptime-kuma"    # name as defined in the ec2 user-data docker compose heredoc
COMPOSE_DIR = "/opt/uptime-stack"  # directory where the docker-compose.yml is located (for context when running docker commands)
BUCKET_NAME = os.getenv('BACKUP_BUCKET_NAME') # existing S3 bucket for backups

# FORMATTING AND UTILITY FUNCTIONS ----------------------
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'
single_line_separator = "-" * 40
double_line_separator = "=" * 40
def print_success(message): print(f"{Colors.GREEN}[SUCCESS]{Colors.END} {message}")
def print_error(message):   print(f"{Colors.RED}[ERROR]{Colors.END} {message}")
def print_info(message):    print(f"{Colors.CYAN}[INFO]{Colors.END} {message}")
def print_warning(message): print(f"{Colors.YELLOW}[WARNING]{Colors.END} {message}")
def wait_for_enter():
    """Wait for user to press Enter"""
    input("\nPress Enter to clear screen and continue...")
    os.system('clear')
# GET SPECIFIC INFO -------------------------------------
def get_aws_region():
    """Automatically detects AWS region using IMDSv2"""
    try:
        # 1. Get Token for IMDSv2
        token_url = "http://169.254.169.254/latest/api/token"
        req = urllib.request.Request(token_url, method='PUT')
        req.add_header("X-aws-ec2-metadata-token-ttl-seconds", "60")
        with urllib.request.urlopen(req, timeout=2) as response:
            token = response.read().decode('utf-8')

        # 2. Get Region (via Availability Zone)
        az_url = "http://169.254.169.254/latest/meta-data/placement/availability-zone"
        req = urllib.request.Request(az_url)
        req.add_header("X-aws-ec2-metadata-token", token)
        with urllib.request.urlopen(req, timeout=2) as response:
            az = response.read().decode('utf-8')
            return az[:-1] # e.g., 'us-east-1a' -> 'us-east-1'
    except Exception as e:
        print_error(f"Could not auto-detect region: {e}")
        return None
def get_aws_secret_info():
    """
    Fetch the Slack details from AWS Secrets Manager using the CLI.
    Expects a JSON secret with 'webhook' and 'channel' keys.
    """
    region = get_aws_region()
    print_info(f"Connecting to Secrets Manager in {region}...")
    cmd = [
        "aws", "secretsmanager", "get-secret-value",
        "--secret-id", AWS_SECRET_NAME,
        "--region", region,
        "--query", "SecretString",
        "--output", "text"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        secret_dict = json.loads(result.stdout)
        webhook = secret_dict.get('webhook')
        channel = secret_dict.get('channel')
        username = secret_dict.get('username', 'Kuma')
        password = secret_dict.get('password', 'Kuma')
        if not webhook or not channel:
            print_error(f"Secret '{AWS_SECRET_NAME}' found, but required keys 'webhook' or 'channel' are missing.")
            return None
        else:
            print_success("Successfully fetched AWS secret details from AWS Secrets Manager.")
            print_info(f"Webhook URL: ****{webhook[-10:]}")
            print_info(f"Channel: {channel}")
            print_info(f"Username: {username}")
            print_info("Password: *******")
        details = {
            "webhook": webhook,
            "channel": channel,
            "username": username,
            "password": password
        }
        return details
    except subprocess.CalledProcessError as e:
        print_error(f"AWS CLI Error: {e.stderr.strip()}")
        return None
    except json.JSONDecodeError:
        print_error(f"Secret '{AWS_SECRET_NAME}' is not a valid JSON string.")
        return None
##################
def interactive_db_restore():
    """
    Manually switch between S3 state or Config-file state.
    This is idempotent: it nukes the current DB and rebuilds from the chosen source.
    """
    def restore_from_config():
        print_info("Rebuilding from kuma-config.json...")
        bootstrap_kuma_db(source='config') 
        print_info("Injecting monitors from config...")
        perform_setup_cycle()
        return

    print(f"\n{Colors.BOLD}--- Database Restore / Switch Source ---{Colors.END}")
    print("1. Restore from S3 (Latest User-defined State)")
    print("2. Restore from Config (Standard kuma-config.json)")
    print("q. Quit this menu")
    
    while True:
        source_choice = input(f"\n{Colors.BOLD}Select source: {Colors.END}")
        if source_choice == 'q':
            print_info("Operation cancelled.")
            return
        if source_choice in ['1', '2']:
            break
    confirm = input(f"{Colors.RED}This will DELETE your current database and monitors. Proceed? (y/N): {Colors.END}")
    if confirm.lower() != 'y':
        return

    try:
        # 1. Preparation: Stop services and clear current state
        print_info("Stopping Uptime Kuma to release file locks...")
        subprocess.run(["docker", "compose", "stop", COMPOSE_SERVICE], cwd=COMPOSE_DIR, check=True)
        
        if Path(DB_FILE).exists():
            print_warning(f"Removing current database at {DB_FILE}...")
            os.remove(DB_FILE)

        # 2. Execution based on choice
        if source_choice == '1':
            # Option 1: Restore from S3
            if restore_from_s3() and is_db_valid(DB_FILE):
                print_success("Database restored from S3.")
            else:
                print_error("S3 Restore failed or no backup found. Resorting to config-based setup instead.")
                print("Press enter to attempt config restore")
                input()
                restore_from_config()

        elif source_choice == '2': 
            restore_from_config()

        print_info("Restarting Uptime Kuma...")
        subprocess.run(["docker", "compose", "up", "-d", COMPOSE_SERVICE], cwd=COMPOSE_DIR, check=True)
        print_success("Restore complete and service is back online.")

    except Exception as e:
        print_error(f"Restore operation failed: {e}")
def get_latest_valid_backup_version():
    """
    Lists all versions of kuma.db in S3 and returns the VersionId 
    of the most recent one that passes the is_db_valid check. This is to prevent restoring from a bad backup.
    """
    print_info(f"Scanning S3 version history for {BUCKET_NAME}...")
    try:
        # Get versions in JSON format, ordered by date
        cmd = [
            "aws", "s3api", "list-object-versions", 
            "--bucket", BUCKET_NAME, 
            "--prefix", "kuma.db",
            "--query", "Versions[].{VersionId:VersionId, LastModified:LastModified}",
            "--output", "json"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        versions = json.loads(result.stdout)
        if not versions:
            print_warning("No versions found in S3 history.")
            return None
        # S3 usually returns them chronologically, but we sort to be certain (newest first)
        versions.sort(key=lambda x: x['LastModified'], reverse=True)
        temp_check_path = "/tmp/kuma_check.db"
        for v in versions:
            version_id = v['VersionId']
            m_date = v['LastModified']
            print_info(f"Checking version from {m_date} (ID: {version_id})...")
            # Download this specific version to a temp location
            download_cmd = [
                "aws", "s3api", "get-object",
                "--bucket", BUCKET_NAME,
                "--key", "kuma.db",
                "--version-id", version_id,
                temp_check_path
            ]
            subprocess.run(download_cmd, capture_output=True, check=True)

            # validation logic
            if is_db_valid(temp_check_path):
                print_success(f"Found valid backup version from {m_date}")
                # Clean up the temp file
                if os.path.exists(temp_check_path): os.remove(temp_check_path)
                return version_id
            else:
                print_warning(f"Version {version_id} is corrupt or uninitialized. Trying next...")
        return None
    except Exception as e:
        print_error(f"Failed to scan S3 versions: {e}")
        return None
def restore_from_s3():
    """
    Determines a recent, viable restorable version from S3 and downloads it.
    """
    if not BUCKET_NAME:
        print_error("No S3 bucket name provided.")
        return False

    # 1. Find the best version
    target_version_id = get_latest_valid_backup_version()
    
    if not target_version_id:
        print_error("No valid backup versions found in S3.")
        return False

    # 2. Download that specific version to the live path
    print_info(f"Restoring verified version {target_version_id}...")
    try:
        cmd = [
            "aws", "s3api", "get-object",
            "--bucket", BUCKET_NAME,
            "--key", "kuma.db",
            "--version-id", target_version_id,
            DB_FILE
        ]
        subprocess.run(cmd, check=True)
        
        # Set ownership for Docker
        os.chown(DB_FILE, 1000, 1000)
        print_success("Database restored and verified.")
        return True
    except Exception as e:
        print_error(f"Final restoration download failed: {e}")
        return False
def is_db_valid(path):
    """Checks if the database file exists and contains the required tables."""
    if not Path(path).exists():
        return False
    try:
        print_info("Checking if the database file exists and contains the required tables.")
        print(f"Trying to connect to database file at {path}...")
        conn = sqlite3.connect(path)
        print("Connected successfully.")
        cursor = conn.cursor()
        print("Checking for 'setting' table in the database...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='setting';")
        exists = cursor.fetchone() is not None
        conn.close()
        print(f"{'Found' if exists else 'Did not find'} 'setting' table in the database.")
        return exists
    except sqlite3.Error as e:
        print_error(f"Error checking database: {e}")
        return False
def bootstrap_kuma_db(source='auto'):
    """
    Orchestrated setup:
    source='auto': Checks local, then S3, then API Fallback.
    source='config': Skips S3 and goes straight to fresh API initialization.
    """
    try:
        # 1. Skip checks if we are forcing a config rebuild
        if source == 'auto':
            print_info("Checking local database state...")
            if is_db_valid(DB_FILE):
                print_info("Database valid. Skipping bootstrap.")
                return

            # Try S3 Restoration only in auto mode
            if restore_from_s3():
                if is_db_valid(DB_FILE):
                    print_info("Restored S3 database is valid. Skipping API initialization.")
                    return
                else:
                    print_info("Restored file invalid. Removing...")
                    if Path(DB_FILE).exists(): os.remove(DB_FILE)

        # 2. Fresh API Bootstrap (Required for 'config' source or failed S3/Local)
        print_info("Initializing New Database Schema via API...")
        
        # Ensure permissions
        subprocess.run(["chown", "-R", "1000:1000", "/opt/kuma-data"], check=True)
        
        # Start container for API access
        subprocess.run(["docker", "compose", "start", COMPOSE_SERVICE], cwd=COMPOSE_DIR, check=True)

        setup_url = "http://localhost:3001/setup-database"
        payload = json.dumps({
            "dbConfig": {"type": "sqlite", "port": 3306, "hostname": "", "username": "", "password": "", "dbName": "kuma"}
        })
       
        max_retries = 15
        for i in range(max_retries):
            try:
                cmd = ["curl", "-s", "-X", "POST", "-H", "Content-Type: application/json", "-d", payload, setup_url]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    print_success("Database type selected successfully.")
                    break
            except Exception: pass
            time.sleep(2)
        else:
            raise Exception("Failed to connect to Uptime Kuma API.")

        print_info("Stopping container to finalize setup...")
        subprocess.run(["docker", "compose", "stop", COMPOSE_SERVICE], cwd=COMPOSE_DIR, check=True)

    except Exception as e:
        print_error(f"Bootstrap sequence failed: {e}")
        raise
def create_manual_backup():
    """Triggers an immediate S3 backup with an option to reset the timer."""
    print(f"\n{Colors.BOLD}{Colors.HEADER}--- MANUAL S3 BACKUP ---{Colors.END}")
    print(f"{Colors.YELLOW}[WARNING] This will create a snapshot of the database in its CURRENT state.{Colors.END}")
    print("If there are errors or malformed data currently in Kuma, they will be backed up to S3.")
    confirm = input(f"\nProceed with backup? (y/N): ")
    if confirm.lower() != 'y':
        print_info("Backup cancelled.")
        return
    
    print_info("Starting backup process...")
    try:
        subprocess.run(["python3", "/home/ec2-user/utilities/kuma-backup.py", "--now"], check=True)
        print_success("Manual backup completed and uploaded to S3.")
    except subprocess.CalledProcessError:
        print_error("Backup script failed. Check Slack for details.")
        return
##################
# CORE FUNCTIONALITY ------------------------------------
def get_or_create_notification(cursor, slack_details):
    """Ensures the Slack notification exists and returns its ID."""
    notif_name = "Global Slack Alerts"
   
    # Configuration mapped exactly to SQLite schema dump
    # obtained by populating a notification called 'My Test Slack Alert' via the UI and then dumping the config column using
    # sqlite3 /opt/kuma-data/kuma.db "SELECT * FROM notification WHERE name = 'My Test Slack Alert';"

    config_dict = {
        "name": notif_name,
        "type": "slack",
        "isDefault": True,
        "telegramServerUrl":"https://api.telegram.org", # some legacy field perhaps, won't be used for Slack but part of schema
        "slackwebhookURL": slack_details['webhook'].strip(),
        "slackchannel": slack_details['channel'].strip(),
        "slackusername": "Kuma",
        "slackiconemo": "🐻", 
        "slackrichmessage": True,
        "slackchannelnotify": True,
        "applyExisting": True
    }
    
    notif_config = json.dumps(config_dict)

    # Check for existing
    cursor.execute("SELECT id, config FROM notification WHERE name = ?", (notif_name,))
    row = cursor.fetchone()
    
    if row:
        print_info(f"Found existing notification '{notif_name}' (ID: {row[0]}). Updating config...")
        # Update without touching the 'type' column
        cursor.execute("UPDATE notification SET config = ?, active = 1 WHERE id = ?", (notif_config, row[0]))
        return row[0]
    else:
        print_info(f"Creating new notification '{notif_name}'...")
        # Insert without touching the 'type' column
        cursor.execute("""
            INSERT INTO notification (name, active, user_id, is_default, config) 
            VALUES (?, 1, 1, 1, ?)
        """, (notif_name, notif_config))
        return cursor.lastrowid   
def sync_monitor(cursor, mon, notif_id):
    """Inserts or updates a monitor and ensures it is linked to the notification."""
    name = mon['name']
    m_type = mon.get('type', 'http')
    url = mon['url']
    interval = mon.get('interval', 60)
    keyword = mon.get('keyword', None)

    # 1. Check if monitor exists by name
    cursor.execute("SELECT id, url, interval, keyword FROM monitor WHERE name = ?", (name,))
    existing = cursor.fetchone()

    if existing:
        m_id = existing[0]
        # Update if anything changed
        if (existing[1] != url or existing[2] != interval or existing[3] != keyword):
            print_info(f"Updating existing monitor: {name} (ID: {m_id})")
            cursor.execute("""
                UPDATE monitor SET url = ?, interval = ?, keyword = ?, type = ? 
                WHERE id = ?
            """, (url, interval, keyword, m_type, m_id))
        else:
            print(f"  - Monitor '{name}' is up to date. Skipping.")
    else:
        print_success(f"Creating new monitor: {name}")
        cursor.execute("""
            INSERT INTO monitor (name, type, url, interval, active, user_id, weight, conditions, keyword)
            VALUES (?, ?, ?, ?, 1, 1, 2000, '[]', ?)
        """, (name, m_type, url, interval, keyword))
        m_id = cursor.lastrowid

    # 2. Force the link to the notification
    # Using INSERT OR IGNORE to prevent duplicate IDs
    cursor.execute("""
        INSERT OR IGNORE INTO monitor_notification (monitor_id, notification_id) 
        VALUES (?, ?)
    """, (m_id, notif_id))
def ensure_admin_user_exists(cursor, username, password):
    """
    Checks if User ID 1 exists. If not, creates it using htpasswd for hashing.
    Idempotent: Does nothing if the user already exists.
    """
    # 1. Check if the user already exists
    cursor.execute("SELECT id FROM user WHERE id = 1")
    if cursor.fetchone():
        print_info("Admin user already exists. Skipping creation.")
        return

    print_info("Admin user not found. Creating automatically...")
    
    # 2. Generate Bcrypt hash using htpasswd (standard library substitute)
    # -n: Don't update file; output to stdout
    # -b: Use password from command line (not prompt)
    # -B: Force bcrypt encryption
    try:
        cmd = ["htpasswd", "-nbB", username, password]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Output format is "username:$2y$10$hash..."
        # We need to split it to get the hash part
        _, password_hash = result.stdout.strip().split(':', 1)
        
        # 3. Insert into DB
        # Note: 'active' = 1, 'timezone' is optional but good to set
        cursor.execute("""
            INSERT INTO user (id, username, password, active, timezone) 
            VALUES (1, ?, ?, 1, 'UTC')
        """, (username, password_hash))
        print_success(f"Admin user '{username}' created successfully.")
        
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to generate password hash. Is 'httpd-tools' installed? Error: {e.stderr}")
        raise Exception("Admin user creation failed")
    except FileNotFoundError:
        print_error("'htpasswd' command not found. Please run: sudo dnf install httpd-tools")
        raise Exception("Admin user creation failed")
def inject_database_config():
    """Main orchestrator for the DB injection."""
    slack_details = get_aws_secret_info()
    if not slack_details:
        return
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        # 1. Handle Admin User Creation (Idempotent)
        try:
            admin_user = slack_details.get("username")
            admin_pass = slack_details.get("password")
            ensure_admin_user_exists(cursor, admin_user, admin_pass)
        except Exception as e:
            # If user creation fails, we should probably stop here to avoid a broken setup
            print_error("Halting setup due to Admin User creation failure.")
            if conn: conn.close()
            return

        # 2. Start the Monitor/Notification Sync
        notif_id = get_or_create_notification(cursor, slack_details)
        with open('/home/ec2-user/utilities/kuma-config.json', 'r') as f:
            config_data = json.load(f)
        for mon in config_data.get("monitors", []):
            sync_monitor(cursor, mon, notif_id)
        conn.commit()
        print_success("Database sync completed successfully.")
        
    except sqlite3.Error as e:
        print_error(f"Database error: {e}")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()
def perform_setup_cycle():
    """
    Stops the container, injects the configuration, and restarts the container.
    Handles errors and returns True on success, False on failure.
    """
    try:
        print_info("Stopping Uptime Kuma service...")
        subprocess.run(["docker", "compose", "stop", COMPOSE_SERVICE], cwd=COMPOSE_DIR, check=True)
     
        print_info("Injecting configuration (Monitors & Notifications)...")
        inject_database_config()
        
        print_info("Starting Uptime Kuma service...")
        subprocess.run(["docker", "compose", "start", COMPOSE_SERVICE], cwd=COMPOSE_DIR, check=True)
        
        print_success("Setup cycle completed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Docker command failed: {e}")
        return False
    except Exception as e:
        print_error(f"Setup failed: {e}")
        return False
def run_automated():
    """Executes the setup flow without user interaction."""
    print_info(f"{Colors.BOLD}Running in Automated Mode...{Colors.END}")
    try:
        # Step 1: Bootstrap
        bootstrap_kuma_db()
        # Step 2: Configuration Injection (Safe to run repeatedly)
        success = perform_setup_cycle()
        return 0 if success else 1
    except Exception as e:
        print_error(f"Critical failure in automated mode: {e}")
        return 1
def fresh_start_kuma():
    """ 
    Nuclear option for Uptime Kuma.
    1. Stops and removes the Uptime Kuma container.
    2. Deletes the /opt/kuma-data directory contents.
    3. Recreates the container to return to 'Setup' mode.
    Leaves Caddy running and untouched.
    """
    print_info(f"{Colors.RED}!!! INITIATING FRESH START FOR UPTIME KUMA !!!{Colors.END}")
    print_info("This will nuke Kuma and all its database files.")
    input("Press Enter to continue, Oppenheimer...")

    try:
        # 1. Stop and Remove Kuma Container
        print_info("Stopping and removing Uptime Kuma container...")
        subprocess.run(["docker", "compose", "rm", "-sfv", COMPOSE_SERVICE], cwd=COMPOSE_DIR, check=True)
        # 2. DELETE the directory and recreate it
        data_dir = os.path.dirname(DB_FILE)
        print_info(f"Deleting data directory: {data_dir}")
        subprocess.run(["sudo", "rm", "-rf", data_dir], check=True)
        # Recreate the directory with correct ownership
        subprocess.run(["sudo", "mkdir", "-p", data_dir], check=True)
        subprocess.run(["sudo", "chown", "-R", "ec2-user:ec2-user", data_dir], check=True)
        # 3. Verify cleanup
        print_info("Verifying directory is empty...")
        result = subprocess.run(["ls", "-la", data_dir], capture_output=True, text=True)
        print(result.stdout) # This will show us if anything is left
        # 4. Recreate the Container
        print_info("Recreating Uptime Kuma container...")
        subprocess.run(["docker", "compose", "up", "-d", COMPOSE_SERVICE], cwd=COMPOSE_DIR, check=True)
        print_success(f"{Colors.GREEN}Fresh Start Complete!{Colors.END}")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed during fresh start: {e}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False
# MAIN INTERACTIVE MENU
def main_menu():
    """Interactive Menu for the User."""
    os.system('clear')
    while True:
        print(f"\n{Colors.BOLD}{Colors.HEADER}{double_line_separator}")
        print("      UPTIME KUMA DIRECT SETUP")
        print(f"{double_line_separator}{Colors.END}")
        print("1. Run Configuration Injection")
        print("2. Display System Info (Region/Paths)")
        print("3. Fresh Start (Nuke Kuma)")
        print("4. Restore Database from S3 Backup or config file")
        print("5. Create a manual backup now")
        print("q. Quit")
        print(f"{single_line_separator}")
        choice = input(f"{Colors.BOLD}Select an option: {Colors.END}")
        if choice == '1':
            perform_setup_cycle()
            wait_for_enter()
        elif choice == '2':
            print_info(f"Detected Region: {get_aws_region()}")
            print_info(f"DB Path: {DB_FILE}")
            wait_for_enter()
        elif choice == '3':
            confirm = input(f"{Colors.RED}Are you sure? This deletes all monitors/data (y/N): {Colors.END}")
            if confirm.lower() == 'y':
                fresh_start_kuma()
                wait_for_enter()
        elif choice == '4':
            interactive_db_restore()
        elif choice == '5':
            create_manual_backup()
            wait_for_enter()
        elif choice.lower() == 'q':
            print_info("Exiting...")
            sys.exit(0)
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--run":
        sys.exit(run_automated())
    else:
        main_menu()