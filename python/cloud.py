"""
╔══════════════════════════════════════════════════════════════╗
║                  CLOUD SERVER  (cloud_server.py)              ║
║                                                               ║
║  Port 6000 ← Fog server forwards encrypted sensor data here  ║
║  Port 8001 ← Data users query their stored messages here     ║
╚══════════════════════════════════════════════════════════════╝
"""

import socket
import json
import threading
import traceback
from datetime import datetime

# ═══════════════════════════════════════════════════════════════
# 🎨  PRINT HELPERS
# ═══════════════════════════════════════════════════════════════
DIV  = "═" * 60
div  = "─" * 60

def section(title: str):
    print(f"\n{DIV}")
    print(f"  {title}")
    print(DIV)

def ok(tag, msg):   print(f"  ✅ [{tag}] {msg}")
def err(tag, msg):  print(f"  ❌ [{tag}] {msg}")
def info(tag, msg): print(f"  ℹ️  [{tag}] {msg}")
def warn(tag, msg): print(f"  ⚠️  [{tag}] {msg}")

# ═══════════════════════════════════════════════════════════════
# 🗄️  IN-MEMORY STORAGE
# ═══════════════════════════════════════════════════════════════
storage: dict[str, list[dict]] = {}
storage_lock = threading.Lock()
msg_counter  = 0

def store_message(owner_id: str, data) -> int:
    global msg_counter
    with storage_lock:
        msg_counter += 1
        mid = msg_counter
        entry = {
            "msg_id"    : mid,
            "owner_id"  : owner_id,
            "data"      : data,
            "timestamp" : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        storage.setdefault(owner_id, []).append(entry)

    print(f"\n  📥 [STORED] msg #{mid} — owner='{owner_id}'  ts={entry['timestamp']}")
    preview = str(data)[:70]
    print(f"       Data preview : {preview}{'…' if len(str(data)) > 70 else ''}")
    _print_storage_table()
    return mid


def _print_storage_table():
    try:
        from tabulate import tabulate
        rows = []
        with storage_lock:
            for uid, messages in storage.items():
                for m in messages:
                    short = (str(m["data"])[:45] + "…") if len(str(m["data"])) > 45 else str(m["data"])
                    rows.append([m["msg_id"], uid, m["timestamp"], short])
        if rows:
            print(f"\n  📋 [CLOUD STORAGE — {len(rows)} message(s) total]")
            print(tabulate(rows,
                headers=["#", "Owner ID", "Timestamp", "Data (preview)"],
                tablefmt="rounded_outline"))
    except ImportError:
        with storage_lock:
            total = sum(len(v) for v in storage.values())
        print(f"\n  📋 [CLOUD STORAGE] {total} msg(s) across {len(storage)} owner(s)")
        print("     (run: pip install tabulate  for a pretty table)")


# ═══════════════════════════════════════════════════════════════
# 📥  FOG RECEIVER  — port 6000
# ═══════════════════════════════════════════════════════════════
def handle_fog_connection(conn, addr):
    section(f"FOG MESSAGE — from {addr[0]}:{addr[1]}")
    with conn:
        raw = b""
        try:
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                raw += chunk
                print(f"  📦 Chunk received: {len(chunk)} bytes  (running total: {len(raw)})")
        except Exception as e:
            err("FOG-RECV", f"Socket read error — {e}")
            traceback.print_exc()
            return

    print(f"  📦 Total bytes received: {len(raw)}")

    if not raw:
        warn("FOG-RECV", "Empty payload — nothing to store")
        return

    try:
        payload  = json.loads(raw.decode())
        owner_id = payload.get("owner_id")
        data     = payload.get("data")

        print(f"  🔍 owner_id='{owner_id}'  data_type={type(data).__name__}")

        if not owner_id:
            err("FOG-RECV", "Missing 'owner_id' — discarding")
            return
        if data is None:
            err("FOG-RECV", "Missing 'data' — discarding")
            return

        mid = store_message(owner_id, data)
        ok("FOG-RECV", f"Stored as message #{mid}")

    except json.JSONDecodeError as e:
        err("FOG-RECV", f"JSON decode error — {e}")
        err("FOG-RECV", f"Raw (first 100 bytes): {raw[:100]!r}")
    except Exception as e:
        err("FOG-RECV", f"{type(e).__name__}: {e}")
        traceback.print_exc()


def fog_listener():
    try:
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 6000))
        srv.listen(10)
    except OSError as e:
        err("FOG-LISTENER", f"Cannot bind port 6000 — {e}")
        return

    ok("FOG-LISTENER", "Listening on 127.0.0.1:6000")

    while True:
        try:
            conn, addr = srv.accept()
            print(f"\n  🟢 [FOG] Connection from {addr[0]}:{addr[1]}")
            threading.Thread(target=handle_fog_connection,
                             args=(conn, addr), daemon=True).start()
        except Exception as e:
            err("FOG-LISTENER", f"Accept error — {e}")
            traceback.print_exc()


# ═══════════════════════════════════════════════════════════════
# 🔎  USER QUERY SERVER  — port 8001 (Updated from 6001)
# ═══════════════════════════════════════════════════════════════
def handle_user_query(conn, addr):
    section(f"USER QUERY — from {addr[0]}:{addr[1]}")
    with conn:
        raw = b""
        try:
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                raw += chunk
        except Exception as e:
            err("USER-QUERY", f"Socket read error — {e}")
            return

        print(f"  📥 Query ({len(raw)} bytes): {raw[:120].decode(errors='replace')!r}")

        try:
            req    = json.loads(raw.decode())
            action = req.get("action", "").strip()
            print(f"  🎯 Action: '{action}'")

            if action == "get_all":
                with storage_lock:
                    all_msgs = [m for msgs in storage.values() for m in msgs]
                reply = {"status": "ok", "count": len(all_msgs), "messages": all_msgs}
                ok("USER-QUERY", f"Returning all {len(all_msgs)} message(s)")

            elif action == "get_user":
                uid = req.get("owner_id", "").strip()
                if not uid:
                    reply = {"status": "error", "reason": "'owner_id' is required for get_user"}
                    err("USER-QUERY", "get_user called without owner_id")
                else:
                    with storage_lock:
                        msgs = list(storage.get(uid, []))
                    reply = {"status": "ok", "owner_id": uid,
                             "count": len(msgs), "messages": msgs}
                    if msgs:
                        ok("USER-QUERY", f"Found {len(msgs)} message(s) for '{uid}'")
                    else:
                        warn("USER-QUERY", f"No messages for '{uid}'")
                        warn("USER-QUERY", f"Known owners: {list(storage.keys())}")

            elif action == "get_stats":
                with storage_lock:
                    stats = {uid: len(msgs) for uid, msgs in storage.items()}
                    total = sum(stats.values())
                reply = {"status": "ok", "total_messages": total, "per_owner": stats}
                ok("USER-QUERY", f"Stats served: {stats}")

            else:
                reply = {"status": "error",
                         "reason": f"Unknown action '{action}'",
                         "valid_actions": ["get_all", "get_user", "get_stats"]}
                err("USER-QUERY", f"Unknown action '{action}'")

            resp_bytes = json.dumps(reply, indent=2).encode()
            conn.sendall(resp_bytes)
            ok("USER-QUERY", f"Reply sent — {len(resp_bytes)} bytes")

        except json.JSONDecodeError as e:
            err("USER-QUERY", f"JSON decode error — {e}")
            try:
                conn.sendall(json.dumps({"status": "error",
                                         "reason": f"Invalid JSON: {e}"}).encode())
            except Exception:
                pass
        except Exception as e:
            err("USER-QUERY", f"{type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                conn.sendall(json.dumps({"status": "error", "reason": str(e)}).encode())
            except Exception:
                pass


def user_listener():
    try:
        srv = socket.socket()
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 8001)) # Port updated to 8001
        srv.listen(10)
    except OSError as e:
        err("USER-LISTENER", f"Cannot bind port 8001 — {e}")
        return

    ok("USER-LISTENER", "Listening on 127.0.0.1:8001")

    while True:
        try:
            conn, addr = srv.accept()
            print(f"\n  👤 [USER] Connection from {addr[0]}:{addr[1]}")
            threading.Thread(target=handle_user_query,
                             args=(conn, addr), daemon=True).start()
        except Exception as e:
            err("USER-LISTENER", f"Accept error — {e}")
            traceback.print_exc()


# ═══════════════════════════════════════════════════════════════
# 🚀  MAIN
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    section("CLOUD SERVER STARTING")
    print("  Port 6000  →  receives data from Fog")
    print("  Port 8001  →  answers Data User queries")
    print()

    t1 = threading.Thread(target=fog_listener,  daemon=True, name="FogListener")
    t2 = threading.Thread(target=user_listener, daemon=True, name="UserListener")
    t1.start()
    t2.start()

    ok("CLOUD", "Both listeners active — press Ctrl+C to stop")
    print()

    try:
        t1.join()
    except KeyboardInterrupt:
        print("\n\n  🛑 Cloud server stopped by user (Ctrl+C)")