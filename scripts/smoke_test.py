"""MANUAL smoke test — makes ONE real API-Football call (/status).

Never wired into pytest/CI: the free tier allows ~100 requests/day.
Run by hand: uv run python scripts/smoke_test.py
"""

import os

from dotenv import load_dotenv

from ingestion.football.client import ApiFootballClient


def main() -> None:
    load_dotenv()
    client = ApiFootballClient(os.environ.get("FOOTBALL_API_KEY", ""))
    status = client.get("/status")
    account = status.get("account", {})
    requests_info = status.get("requests", {})
    print(f"Auth OK for: {account.get('firstname')} {account.get('lastname')}")
    print(
        f"Requests today: {requests_info.get('current')}/{requests_info.get('limit_day')}"
    )


if __name__ == "__main__":
    main()
