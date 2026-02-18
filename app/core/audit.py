from pathlib import Path
from datetime import datetime

LOGS_DIR = Path(__file__).parent.parent.parent / "logs"


def write_audit_log(user_name: str, user_role: str, action: str, details: str = ""):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    month_str = datetime.now().strftime("%Y_%m")
    log_file = LOGS_DIR / f"audit_{month_str}.log"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {user_role} | {user_name} | {action} | {details}\n")
