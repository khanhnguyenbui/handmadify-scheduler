import json
import os
from pathlib import Path

DB_PATH = Path(__file__).parent / "markets.json"

class Database:
    def __init__(self):
        self.data = {"markets": [], "dashboards": []}
        self.load()

    def load(self):
        if os.path.exists(DB_PATH):
            with open(DB_PATH, "r") as f:
                self.data = json.load(f)
        else:
            self.save()

    def save(self):
        with open(DB_PATH, "w") as f:
            json.dump(self.data, f, indent=4)

    def create_market(self, market_type: str, date: str, notes: str, staff: list[str], channel_id: int) -> int:
        new_id = 1
        if self.data["markets"]:
            new_id = max(m["id"] for m in self.data["markets"]) + 1
        
        market = {
            "id": new_id,
            "market_type": market_type,
            "date": date,
            "notes": notes,
            "assigned_staff": staff,
            "channel_id": channel_id,
            "message_id": None
        }
        self.data["markets"].append(market)
        self.save()
        return new_id

    def update_market(self, market_id: int, date: str, notes: str, staff: list[str]):
        market = self._find_market(market_id)
        if market:
            market["date"] = date
            market["notes"] = notes
            market["assigned_staff"] = staff
            self.save()

    def set_message_id(self, market_id: int, message_id: int):
        market = self._find_market(market_id)
        if market:
            market["message_id"] = message_id
            self.save()

    def get_market(self, market_id: int) -> dict | None:
        return self._find_market(market_id)

    def get_all_markets(self) -> list[dict]:
        return self.data["markets"]

    def add_dashboard(self, channel_id: int, message_id: int):
        self.data["dashboards"].append({"channel_id": channel_id, "message_id": message_id})
        self.save()

    def get_dashboards(self) -> list[dict]:
        return self.data.get("dashboards", [])

    def _find_market(self, market_id: int) -> dict | None:
        return next((m for m in self.data["markets"] if m["id"] == market_id), None)