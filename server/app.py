"""
Flask server to receive WhatsApp exported chat files.
Parses .txt exports into structured JSON organized by contact.
"""

import os
import re
import json
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_from_directory

app = Flask(__name__)

UPLOAD_DIR = Path("/opt/whatsapp-extractor/uploads")
PARSED_DIR = Path("/opt/whatsapp-extractor/parsed")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PARSED_DIR.mkdir(parents=True, exist_ok=True)

# Max upload: 500MB (for many files with media references)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024


def parse_whatsapp_txt(filepath: str) -> dict:
    """Parse a WhatsApp exported .txt file into structured messages."""
    messages = []
    # Pattern: DD/MM/YYYY HH:MM - Sender: Message
    # Also handles: DD/MM/YY, MM/DD/YY, etc.
    pattern = re.compile(
        r"(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?)\s*(?:AM|PM|am|pm)?\s*-\s*(.*?):\s(.*)"
    )

    current_msg = None

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n")
            match = pattern.match(line)
            if match:
                if current_msg:
                    messages.append(current_msg)
                date_str, time_str, sender, text = match.groups()
                current_msg = {
                    "date": date_str.strip(),
                    "time": time_str.strip(),
                    "sender": sender.strip(),
                    "text": text.strip(),
                }
            elif current_msg:
                # Continuation of previous message (multiline)
                current_msg["text"] += "\n" + line

    if current_msg:
        messages.append(current_msg)

    # Extract contact name from filename
    # Format: "WhatsApp Chat with Contact Name.txt"
    filename = os.path.basename(filepath)
    contact = filename.replace("WhatsApp Chat with ", "").replace(".txt", "")
    contact = contact.replace("Conversa do WhatsApp com ", "").replace(".txt", "")

    return {
        "contact": contact,
        "message_count": len(messages),
        "messages": messages,
        "first_message": messages[0]["date"] if messages else None,
        "last_message": messages[-1]["date"] if messages else None,
    }


@app.route("/")
def index():
    return render_template("download.html")


@app.route("/whatsapp-upload", methods=["POST"])
def upload_files():
    """Receive uploaded chat export files."""
    if "files" not in request.files:
        return jsonify({"error": "No files received"}), 400

    files = request.files.getlist("files")
    saved = []
    parsed_results = []

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_dir = UPLOAD_DIR / timestamp
    batch_dir.mkdir(exist_ok=True)

    for f in files:
        if f.filename:
            safe_name = f.filename.replace("/", "_").replace("\\", "_")
            save_path = batch_dir / safe_name
            f.save(str(save_path))
            saved.append(safe_name)

            # Parse the file
            if safe_name.endswith(".txt"):
                try:
                    parsed = parse_whatsapp_txt(str(save_path))
                    parsed_results.append(parsed)
                except Exception as e:
                    parsed_results.append({"file": safe_name, "error": str(e)})

    # Save parsed results as JSON
    if parsed_results:
        json_path = PARSED_DIR / f"{timestamp}_conversations.json"
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(parsed_results, jf, ensure_ascii=False, indent=2)

    return jsonify({
        "status": "ok",
        "count": len(saved),
        "files": saved,
        "conversations_parsed": len([r for r in parsed_results if "error" not in r]),
    })


DIAGNOSTICS_DIR = Path("/opt/whatsapp-extractor/diagnostics")
DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)


@app.route("/whatsapp-diagnostics", methods=["POST"])
def upload_diagnostics():
    """Receive diagnostic screenshots and UI dumps from the extractor."""
    if "files" not in request.files:
        return jsonify({"error": "No files received"}), 400

    files = request.files.getlist("files")
    saved = []

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    diag_dir = DIAGNOSTICS_DIR / timestamp
    diag_dir.mkdir(exist_ok=True)

    for f in files:
        if f.filename:
            safe_name = f.filename.replace("/", "_").replace("\\", "_")
            save_path = diag_dir / safe_name
            f.save(str(save_path))
            saved.append(safe_name)

    return jsonify({
        "status": "ok",
        "count": len(saved),
        "files": saved,
        "diagnostic_dir": str(diag_dir),
    })


@app.route("/whatsapp-diagnostics", methods=["GET"])
def list_diagnostics():
    """List all diagnostic sessions with their files."""
    sessions = []
    if DIAGNOSTICS_DIR.exists():
        for session_dir in sorted(DIAGNOSTICS_DIR.iterdir(), reverse=True):
            if session_dir.is_dir():
                files = sorted([f.name for f in session_dir.iterdir()])
                sessions.append({
                    "timestamp": session_dir.name,
                    "file_count": len(files),
                    "files": files,
                    "screenshots": [f for f in files if f.endswith(".png")],
                    "ui_dumps": [f for f in files if f.endswith(".xml")],
                })
    return jsonify({"sessions": sessions})


@app.route("/whatsapp-diagnostics/<session>/<filename>")
def download_diagnostic(session, filename):
    """Download a specific diagnostic file (screenshot or UI dump)."""
    session_dir = DIAGNOSTICS_DIR / session
    return send_from_directory(str(session_dir), filename)


@app.route("/whatsapp-data", methods=["GET"])
def list_data():
    """List all uploaded batches and parsed conversations."""
    batches = []
    for batch_dir in sorted(UPLOAD_DIR.iterdir(), reverse=True):
        if batch_dir.is_dir():
            files = [f.name for f in batch_dir.iterdir()]
            batches.append({
                "timestamp": batch_dir.name,
                "file_count": len(files),
                "files": files,
            })

    parsed = []
    for json_file in sorted(PARSED_DIR.glob("*.json"), reverse=True):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            parsed.append({
                "file": json_file.name,
                "conversations": len(data),
                "total_messages": sum(c.get("message_count", 0) for c in data if "error" not in c),
            })

    return jsonify({"batches": batches, "parsed": parsed})


@app.route("/whatsapp-export/<filename>")
def download_parsed(filename):
    """Download a parsed JSON file."""
    return send_from_directory(str(PARSED_DIR), filename)


@app.route("/download-extractor")
def download_extractor():
    """Serve the .exe file for download."""
    exe_dir = "/opt/whatsapp-extractor/dist"
    return send_from_directory(exe_dir, "WhatsAppExtractor.exe", as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
