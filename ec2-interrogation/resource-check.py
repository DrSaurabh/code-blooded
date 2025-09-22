#!/usr/bin/env python3
import subprocess
import re
import os
from datetime import datetime

# ANSI colors
CYAN = "\033[96m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
WHITE = "\033[97m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RED = "\033[91m"
PURPLE = "\033[35m"
BOLD = "\033[1m"
ITALICS = "\x1B[3m"
RESET = "\033[0m"

def run_cmd(cmd):
    """Run a shell command and return output as string."""
    try:
        return subprocess.check_output(cmd, shell=True, text=True).strip()
    except subprocess.CalledProcessError:
        return ""

def get_ec2_metrics():
    """Fetch EC2-level resource utilization."""
    loadavg = run_cmd("uptime").split("load average:")[-1].strip()

    meminfo = run_cmd("free -m").splitlines()
    mem_line = meminfo[1].split()
    total_mem, used_mem = int(mem_line[1]), int(mem_line[2])
    mem_pct = used_mem * 100 / total_mem if total_mem else 0

    disk_line = run_cmd("df -h /").splitlines()[-1].split()
    disk_size, disk_used, _, disk_use_pct = disk_line[1:5]

    return {
        "CPU Load (1/5/15m)": loadavg,
        "Memory Used": f"{used_mem} MB / {total_mem} MB ({mem_pct:.1f}%)",
        "Disk Root": f"{disk_used} / {disk_size} ({disk_use_pct})"
    }

def get_ebs_volume():
    """Get only the root volume capacity and usage."""
    return run_cmd("df -h /").splitlines()[-1]

def get_container_metrics():
    """Fetch Docker container metrics: ps + stats merged."""
    ps_cmd = (
        "docker ps --format "
        "'{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}'"
    )
    ps_lines = run_cmd(ps_cmd).splitlines()
    ps_data = {}
    for line in ps_lines:
        parts = line.split("\t")
        if len(parts) >= 4:
            cid, name, image, status = parts[:4]
            ps_data[cid] = {
                "Name": name,
                "Image": image,
                "Status": status,
                "CPU %": "-",
                "Mem %": "-"
            }

    stats_cmd = (
        "docker stats --no-stream --format "
        "'{{.ID}}\t{{.CPUPerc}}\t{{.MemPerc}}'"
    )
    stats_lines = run_cmd(stats_cmd).splitlines()
    for line in stats_lines:
        parts = line.split("\t")
        if len(parts) == 3:
            cid, cpu, mem = parts
            if cid in ps_data:
                ps_data[cid]["CPU %"] = cpu
                ps_data[cid]["Mem %"] = mem

    header = ["CONTAINER ID", "NAME", "IMAGE", "STATUS", "CPU %", "MEM %"]
    rows = ["\t".join(header)]
    for cid, info in ps_data.items():
        rows.append("\t".join([
            cid, info["Name"], info["Image"],
            info["Status"], info["CPU %"], info["Mem %"]
        ]))

    return rows if rows else ["No containers running."]

def parse_size(size_str):
    """Convert human-readable size to MB (float).

    Accepts tokens like:
      - '24MB', '512kB', '1.2GB'
      - pure bytes like '12345' (interpreted as bytes)
      - strings containing a size token (we extract the first match)
    Returns float MB.
    """
    if not size_str:
        return 0.0
    s = size_str.strip()

    # pure numeric -> treat as bytes
    if re.fullmatch(r'\d+', s):
        return int(s) / (1024.0 * 1024.0)

    # find first size token like '1.2GB' or '512kB' or '24MB' or '123B'
    m = re.search(r'([\d\.]+)\s*([kKmMgG]?B)', s)
    if not m:
        # try to find digits (last resort, treat as bytes)
        m2 = re.search(r'(\d+)', s)
        if m2:
            return int(m2.group(1)) / (1024.0 * 1024.0)
        return 0.0

    value = float(m.group(1))
    unit = m.group(2).upper()

    if unit == 'KB':
        return value / 1024.0
    if unit == 'MB':
        return value
    if unit == 'GB':
        return value * 1024.0
    if unit == 'B':
        return value / (1024.0 * 1024.0)
    return 0.0

def get_docker_housekeeping():
    """Compute unused images size + stopped containers size and return an estimated reclaimable summary."""
    
    # Get image IDs currently used by running containers
    used_image_ids = set()
    running_containers = run_cmd("docker ps -q --no-trunc")
    if running_containers.strip():
        for cid in running_containers.splitlines():
            image_id = run_cmd(f"docker inspect --format '{{{{.Image}}}}' {cid}").strip()
            if image_id:
                used_image_ids.add(image_id)

    # Get ALL images with their full IDs
    all_images_raw = run_cmd("docker images -a --no-trunc --format '{{.ID}} {{.Repository}}:{{.Tag}} {{.Size}}'")
    unused_total_mb = 0.0
    unused_items = []
    
    for line in all_images_raw.splitlines():
        if not line.strip():
            continue
        parts = line.rsplit(" ", 1)
        if len(parts) == 2:
            info, size_token = parts
            image_id = info.split()[0]
            
            # Consider image unused if it's NOT used by any running container
            if image_id not in used_image_ids:
                unused_total_mb += parse_size(size_token)
                repo_tag_part = ' '.join(info.split()[1:])
                unused_items.append(f"{repo_tag_part} ({size_token})")
                # unused_items.append(f"{info} ({size_token})")

    # Stopped containers
    stopped_raw = run_cmd("docker ps -a -f status=exited --format '{{.ID}} {{.Names}}'")
    stopped_lines = [l for l in stopped_raw.splitlines() if l.strip()]

    stopped_total_mb = 0.0
    stopped_items = []
    for line in stopped_lines:
        cid, name = line.split(maxsplit=1) if " " in line else (line, line)
        size_bytes = run_cmd(f"docker inspect --size --format '{{{{.SizeRw}}}}' {cid}").strip()
        size_str = "?"
        if size_bytes and size_bytes.isdigit():
            stopped_total_mb += int(size_bytes) / (1024.0 * 1024.0)
            size_str = f"{int(size_bytes)/(1024*1024):.1f}MB"
        stopped_items.append(f"{cid} {name} ({size_str})")

    reclaim_mb = unused_total_mb + stopped_total_mb

    def fmt_mb(mb):
        return f"{mb/1024:.2f}GB" if mb >= 1024 else f"{mb:.1f}MB"

    reclaim_str = (
        f"\nestimated total reclaimable space: {fmt_mb(reclaim_mb)}\n"
        f"unused images: {fmt_mb(unused_total_mb)}\n"
        f"stopped containers: {fmt_mb(stopped_total_mb)}"
    )

    suggestion = ""
    if reclaim_mb > 100.0:
        suggestion = f"Consider {ITALICS}{RED}docker system prune -af{RESET} to free up space."

    return {
        "Unused Images": "\n"+"\n".join(unused_items) if unused_items else "None",
        "Stopped Containers": "\n"+"\n".join(stopped_items) if stopped_items else "None",
        "Reclaimable Space": reclaim_str,
        "Suggestion": suggestion
    }

def print_table(title, rows, color=CYAN):
    """Print a section with aligned columns and colors."""
    print(f"\n{color}=== {title} ==={RESET}")
    if isinstance(rows, dict):
        for k, v in rows.items():
            if v and k == "Suggestion":
                print(f"{YELLOW}{k:<20}:{RESET} {WHITE}{v}{RESET}")
            elif v:
                print(f"{YELLOW}{k:<20}:{RESET} {WHITE}{v}{RESET}")
    else:
        split_rows = [r.split("\t") for r in rows]
        col_widths = [max(len(col) for col in column) for column in zip(*split_rows)]
        for i, row in enumerate(split_rows):
            colored = []
            for j, col in enumerate(row):
                if i == 0:  # header row
                    colored.append(f"{YELLOW}{col.ljust(col_widths[j])}{RESET}")
                else:
                    colored.append(f"{WHITE}{col.ljust(col_widths[j])}{RESET}")
            print("  ".join(colored))

def print_header():
    """Print script header."""
    now = datetime.now()
    formatted_time = now.strftime("%H:%M  UTC, %d-%b-%Y")
    padding = " " * (45 - len(formatted_time))
    print()
    print(f"{MAGENTA}    ╔══════════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{MAGENTA}    ║                     Docker Resource Check                        ║{RESET}")
    print(f"{MAGENTA}    ║                     System Analysis Report                       ║{RESET}")
    print(f"{MAGENTA}    ║                     {formatted_time}{padding}║{RESET}")
    print(f"{MAGENTA}    ╚══════════════════════════════════════════════════════════════════╝{RESET}")


def main():
    os.system("clear")  # clear screen at start
    ec2_metrics = get_ec2_metrics()
    ebs_volume = get_ebs_volume()
    container_metrics = get_container_metrics()
    docker_housekeeping = get_docker_housekeeping()

    print_header()
    print_table("EC2 Host Metrics", ec2_metrics)
    print_table("Attached EBS Volume (root)", [ebs_volume])
    print_table("Docker Containers", container_metrics)
    print_table("Docker Housekeeping", docker_housekeeping)

if __name__ == "__main__":
    main()
