import os
import datetime as dt
from typing import Dict, Any, Optional
import csv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def _now_iso():
    # Log in UTC by default; Google Sheets will show as-is
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def log_contact(entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    entry keys: name, email, organization, question, version, mode
    """
    enabled = os.getenv("GOOGLE_SHEETS_ENABLED", "false").lower() == "true"
    if enabled:
        creds_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "").strip()
        doc_title = os.getenv("GOOGLE_SHEETS_DOC_TITLE", "Relativity Releases Chatbot Contacts")
        if not creds_path or not os.path.exists(creds_path):
            return _csv_fallback(entry, note="Missing Google credentials file; wrote to CSV instead.")
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, SCOPE)
            client = gspread.authorize(creds)
            try:
                sh = client.open(doc_title)
            except gspread.SpreadsheetNotFound:
                sh = client.create(doc_title)
            ws = sh.sheet1
            if ws.row_count < 1 or ws.cell(1,1).value is None:
                ws.append_row(["timestamp","name","email","organization","question","version","mode"])
            ws.append_row([_now_iso(), entry.get("name",""), entry.get("email",""), entry.get("organization",""), entry.get("question",""), entry.get("version",""), entry.get("mode","")])
            return {"ok": True, "where": "sheets"}
        except Exception as e:
            return _csv_fallback(entry, note=f"Sheets error: {e}")
    else:
        return _csv_fallback(entry, note="Sheets disabled; wrote to CSV.")

def _csv_fallback(entry: Dict[str, Any], note: str):
    os.makedirs("logs", exist_ok=True)
    path = os.path.join("logs", "contacts.csv")
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(["timestamp","name","email","organization","question","version","mode"])
        w.writerow([_now_iso(), entry.get("name",""), entry.get("email",""), entry.get("organization",""), entry.get("question",""), entry.get("version",""), entry.get("mode","")])
    return {"ok": True, "where": "csv", "note": note}
