"""
╔══════════════════════════════════════════════════════════════╗
║                  DATA USER  (data_user.py)                    ║
║                                                               ║
║  Step 1 → Get secret key (SK) from Attribute Authority        ║
║  Step 2 → Fetch CKI (ABE ciphertext of KI) from Blockchain    ║
║  Step 3 → Decrypt CKI with SK  →  recover KI                  ║
║  Step 4 → Fetch encrypted messages (CTI) from Cloud           ║
║  Step 5 → Decrypt CTI with KI  →  read plaintext              ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import socket
import binascii
import traceback
import base64
from web3 import Web3
from charm.toolbox.pairinggroup import PairingGroup, GT, extract_key
from charm.schemes.abenc.abenc_maabe_yj14 import MAABE
from attribute_authority import aa

# ═══════════════════════════════════════════════════════════════
# 🎨  PRINT HELPERS
# ═══════════════════════════════════════════════════════════════
DIV = "═" * 60
div = "─" * 60

def section(title):
    print(f"\n{DIV}\n  {title}\n{DIV}")

def ok(tag, msg):   print(f"  ✅ [{tag}] {msg}")
def err(tag, msg):  print(f"  ❌ [{tag}] {msg}")
def info(tag, msg): print(f"  ℹ️  [{tag}] {msg}")
def warn(tag, msg): print(f"  ⚠️  [{tag}] {msg}")

# ═══════════════════════════════════════════════════════════════
# ⚙️  SHARED MA-ABE SETUP  (must mirror fog_server.py exactly)
# ═══════════════════════════════════════════════════════════════
section("MA-ABE SETUP")
print("  Initialising pairing group SS512…")
group  = PairingGroup('SS512')
maabe  = MAABE(group)
print("  Running maabe.setup()…")
GPP, GMK = maabe.setup()
ok("MA-ABE", "GPP ready")

auth_id     = "AUTH1"
authorities = {}
all_attrs   = aa.get_all_attributes()
print(f"  Setting up authority '{auth_id}' with attributes: {all_attrs}")
maabe.setupAuthority(GPP, auth_id, all_attrs, authorities)
ok("MA-ABE", f"Authority '{auth_id}' ready")

# ═══════════════════════════════════════════════════════════════
# 🔗  BLOCKCHAIN CONFIG
# ═══════════════════════════════════════════════════════════════
GANACHE_URL      = "http://127.0.0.1:8545"
CONTRACT_ADDRESS = "0xF7f3752ab7081C8774f1BcfDC18F0E697828fbCf"

CONTRACT_ABI = json.loads("""[
  {"inputs":[{"internalType":"string","name":"_userId","type":"string"}],
   "name":"getUserCKI","outputs":[{"internalType":"string","name":"","type":"string"}],
   "stateMutability":"view","type":"function"},
  {"inputs":[{"internalType":"string","name":"_userId","type":"string"}],
   "name":"isUserRegistered","outputs":[{"internalType":"bool","name":"","type":"bool"}],
   "stateMutability":"view","type":"function"}
]""")

# ═══════════════════════════════════════════════════════════════
# 🔧  DESERIALIZE
# ═══════════════════════════════════════════════════════════════
def _deserialize(obj):
    if isinstance(obj, dict):
        return {k: _deserialize(v) for k, v in obj.items()}
    if isinstance(obj, str):
        try:
            raw = binascii.a2b_base64(obj.encode())
            return group.deserialize(raw)
        except Exception:
            return obj
    return obj

# ═══════════════════════════════════════════════════════════════
# STEP 1 — GET SECRET KEY FROM ATTRIBUTE AUTHORITY
# ═══════════════════════════════════════════════════════════════
def get_secret_key(gid, user_attributes):
    section("STEP 1 — GET SECRET KEY FROM ATTRIBUTE AUTHORITY")
    print(f"  GID             : {gid}")
    print(f"  User attributes : {user_attributes}")

    valid_attrs = aa.get_all_attributes()
    unknown = [a for a in user_attributes if a not in valid_attrs]
    if unknown:
        err("AA", f"Unknown attribute(s): {unknown}")
        err("AA", f"Valid attributes    : {valid_attrs}")
        return None

    ok("AA", "All attributes recognised in the authority catalog")
    print("  📡 Calling maabe.keygen()…")

    try:
        SK = maabe.keygen(GPP, authorities[auth_id], gid, user_attributes)
        ok("AA", "Secret key obtained")
        print(f"  🔑 SK type : {type(SK).__name__}")
        if isinstance(SK, dict):
            print(f"  🔑 SK keys : {list(SK.keys())}")
        return SK
    except Exception as e:
        err("AA", f"keygen() failed — {type(e).__name__}: {e}")
        traceback.print_exc()
        return None

# ═══════════════════════════════════════════════════════════════
# STEP 2 — FETCH CKI FROM BLOCKCHAIN
# ═══════════════════════════════════════════════════════════════
def fetch_cki_from_blockchain(owner_id):
    section("STEP 2 — FETCH CKI FROM BLOCKCHAIN")
    print(f"  Owner ID : {owner_id}")
    print(f"  Ganache  : {GANACHE_URL}")
    print(f"  Contract : {CONTRACT_ADDRESS}")

    print("\n  🔌 Connecting to Ganache…")
    w3 = Web3(Web3.HTTPProvider(GANACHE_URL))
    if not w3.is_connected():
        err("BLOCKCHAIN", f"Cannot connect to Ganache at {GANACHE_URL}")
        err("BLOCKCHAIN", "Fix: ensure Ganache is running →  npx ganache --port 8545")
        return None
    ok("BLOCKCHAIN", f"Connected  |  Chain ID: {w3.eth.chain_id}")
    print(f"  Available accounts : {len(w3.eth.accounts)}")

    try:
        contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
        ok("CONTRACT", f"Loaded at {CONTRACT_ADDRESS}")
    except Exception as e:
        err("CONTRACT", f"Failed to load contract — {e}")
        traceback.print_exc()
        return None

    try:
        print(f"\n  🔍 isUserRegistered('{owner_id}')…")
        registered = contract.functions.isUserRegistered(owner_id).call()
        print(f"  📌 Result: {registered}")
        if not registered:
            err("BLOCKCHAIN", f"'{owner_id}' is NOT registered on-chain")
            err("BLOCKCHAIN", "The fog server must run first to register the owner")
            return None
        ok("BLOCKCHAIN", f"'{owner_id}' is registered")
    except Exception as e:
        err("BLOCKCHAIN", f"isUserRegistered() failed — {e}")
        traceback.print_exc()
        return None

    try:
        print(f"\n  📥 getUserCKI('{owner_id}')…")
        cki_json = contract.functions.getUserCKI(owner_id).call()
        print(f"  📦 CKI JSON length : {len(cki_json)} characters")
        if not cki_json:
            err("BLOCKCHAIN", "getUserCKI() returned empty string")
            return None
        cki_raw = json.loads(cki_json)
        ok("BLOCKCHAIN", f"CKI parsed  —  top-level keys: {list(cki_raw.keys())}")
    except json.JSONDecodeError as e:
        err("BLOCKCHAIN", f"CKI is not valid JSON — {e}")
        return None
    except Exception as e:
        err("BLOCKCHAIN", f"getUserCKI() failed — {e}")
        traceback.print_exc()
        return None

    print("\n  🔧 Deserialising CKI (base64 → charm elements)…")
    try:
        cki = _deserialize(cki_raw)
        ok("BLOCKCHAIN", "CKI deserialised successfully")
        print(f"  📦 CKI keys: {list(cki.keys())}")
        return cki
    except Exception as e:
        err("BLOCKCHAIN", f"Deserialisation failed — {e}")
        traceback.print_exc()
        return None

# ═══════════════════════════════════════════════════════════════
# STEP 3 — DECRYPT CKI → RECOVER KI
# ═══════════════════════════════════════════════════════════════
def decrypt_cki(SK, CKI, gid):
    section("STEP 3 — DECRYPT CKI → RECOVER KI")
    print(f"  GID : {gid}")
    print(f"  Building SK bundle for authority '{auth_id}'…")

    SK_bundle = {"GID": gid, "keys": {auth_id: SK}}
    print("  Calling maabe.decrypt()…")

    try:
        ki_element = maabe.decrypt(GPP, SK_bundle, CKI)
        if ki_element is False:
            err("MA-ABE", "Decryption → False")
            err("MA-ABE", "User attributes do NOT satisfy the access policy")
            err("MA-ABE", "Check USER_ATTRIBUTES vs the policy the fog used")
            return None
        ok("MA-ABE", "Decryption succeeded — KI element recovered")
        ki_bytes = extract_key(ki_element)
        ok("MA-ABE", f"KI extracted → {len(ki_bytes)} bytes")
        print(f"  🗝️  KI hex (preview): {binascii.hexlify(ki_bytes).decode()[:32]}…")
        return ki_bytes
    except Exception as e:
        err("MA-ABE", f"decrypt() raised — {type(e).__name__}: {e}")
        traceback.print_exc()
        return None

# ═══════════════════════════════════════════════════════════════
# STEP 4 — FETCH MESSAGES (CTI) FROM CLOUD
# ═══════════════════════════════════════════════════════════════
def fetch_messages_from_cloud(owner_id):
    section("STEP 4 — FETCH CTI MESSAGES FROM CLOUD")
    print(f"  Owner ID       : {owner_id}")
    print(f"  Cloud endpoint : 127.0.0.1:6001")

    req = {"action": "get_user", "owner_id": owner_id}
    print(f"  📤 Query: {req}")

    try:
        with socket.create_connection(("127.0.0.1", 6001), timeout=8) as s:
            s.sendall(json.dumps(req).encode())
            s.shutdown(socket.SHUT_WR)
            raw = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                raw += chunk
                print(f"  📦 Chunk: {len(chunk)} B  (total: {len(raw)} B)")
    except ConnectionRefusedError:
        err("CLOUD", "Connection refused — is cloud_server.py running on port 6001?")
        return []
    except socket.timeout:
        err("CLOUD", "Timed out after 8 s — cloud server did not respond")
        return []
    except Exception as e:
        err("CLOUD", f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return []

    print(f"  📦 Total received: {len(raw)} bytes")

    try:
        reply = json.loads(raw.decode())
    except json.JSONDecodeError as e:
        err("CLOUD", f"JSON decode error — {e}")
        err("CLOUD", f"Raw: {raw[:120]!r}")
        return []

    if reply.get("status") != "ok":
        err("CLOUD", f"Server error: {reply.get('reason', 'no reason given')}")
        return []

    messages = reply.get("messages", [])
    ok("CLOUD", f"Received {len(messages)} message(s)")

    if not messages:
        warn("CLOUD", "No messages found for this owner")
        warn("CLOUD", "Make sure IoT device has sent data through the fog first")
        return []

    for m in messages:
        preview = str(m.get("data", ""))[:50]
        print(f"  📧 Msg #{m.get('msg_id','?')} [{m.get('timestamp','?')}]  {preview}…")

    return messages

# ═══════════════════════════════════════════════════════════════
# STEP 5 — DECRYPT CTI → PLAINTEXT  (AES-128-CBC)
# ═══════════════════════════════════════════════════════════════
def decrypt_messages(messages, ki_bytes):
    section("STEP 5 — DECRYPT CTI MESSAGES")
    print(f"  Messages to decrypt : {len(messages)}")
    print(f"  AES key = first 16 bytes of KI")

    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        aes_ok = True
        ok("AES", "pycryptodome is available")
    except ImportError:
        warn("AES", "pycryptodome not found — messages shown as raw")
        warn("AES", "Install:  pip install pycryptodome")
        aes_ok = False

    aes_key = ki_bytes[:16]
    results = []

    for m in messages:
        entry = {
            "msg_id"    : m.get("msg_id"),
            "owner_id"  : m.get("owner_id"),
            "timestamp" : m.get("timestamp"),
        }
        raw_data = m.get("data", "")

        print(f"\n  {div}")
        print(f"  📧 Message #{entry['msg_id']}  [{entry['timestamp']}]")
        print(f"  Raw type    : {type(raw_data).__name__}")
        print(f"  Raw preview : {str(raw_data)[:60]}")

        if not aes_ok:
            entry["plaintext"] = str(raw_data)
            entry["status"]    = "⚠️  pycryptodome missing — shown raw"
            results.append(entry)
            continue

        try:
            raw_bytes  = base64.b64decode(str(raw_data))
            print(f"  Base64 decoded : {len(raw_bytes)} bytes")

            if len(raw_bytes) < 17:
                raise ValueError(f"Too short for IV+data ({len(raw_bytes)} bytes)")

            iv         = raw_bytes[:16]
            ciphertext = raw_bytes[16:]
            print(f"  IV (hex) : {binascii.hexlify(iv).decode()}")
            print(f"  CT size  : {len(ciphertext)} bytes")

            cipher    = AES.new(aes_key, AES.MODE_CBC, iv)
            plaintext = unpad(cipher.decrypt(ciphertext), AES.block_size).decode("utf-8")

            entry["plaintext"] = plaintext
            entry["status"]    = "✅ decrypted"
            ok("AES", f"Decrypted → {plaintext[:60]}")

        except (base64.binascii.Error, ValueError) as e:
            warn("AES", f"Not AES-base64 ({e}) — showing raw")
            entry["plaintext"] = str(raw_data)
            entry["status"]    = "⚠️  not AES-encrypted — shown raw"
        except Exception as e:
            err("AES", f"{type(e).__name__}: {e}")
            entry["plaintext"] = str(raw_data)
            entry["status"]    = f"❌ {e}"

        results.append(entry)

    return results

# ═══════════════════════════════════════════════════════════════
# 🚀  MAIN
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":

    # ── Configure here ────────────────────────────────────────
    OWNER_ID        = "DO_101"
    USER_GID        = "user_alice"
    USER_ATTRIBUTES = ["STUDENT"]
    #  policy1     → STUDENT or STAFF          ← use ["STUDENT"]
    #  policy2     → MANAGER and RESEARCHER    ← use ["MANAGER","RESEARCHER"]
    #  Admin_Only  → ADMIN                     ← use ["ADMIN"]
    # ──────────────────────────────────────────────────────────

    section("DATA USER CLIENT — START")
    print(f"  Target owner    : {OWNER_ID}")
    print(f"  User GID        : {USER_GID}")
    print(f"  User attributes : {USER_ATTRIBUTES}")

    SK = get_secret_key(USER_GID, USER_ATTRIBUTES)
    if SK is None:
        err("MAIN", "Cannot continue without secret key"); exit(1)

    CKI = fetch_cki_from_blockchain(OWNER_ID)
    if CKI is None:
        err("MAIN", "Cannot continue without CKI"); exit(1)

    KI = decrypt_cki(SK, CKI, USER_GID)
    if KI is None:
        err("MAIN", "Cannot continue without KI"); exit(1)

    messages = fetch_messages_from_cloud(OWNER_ID)
    if not messages:
        warn("MAIN", "No messages to decrypt — exiting"); exit(0)

    results = decrypt_messages(messages, KI)

    section("FINAL RESULTS SUMMARY")
    print(f"  Owner       : {OWNER_ID}")
    print(f"  User        : {USER_GID}  (attrs: {USER_ATTRIBUTES})")
    print(f"  Total msgs  : {len(results)}\n")

    for r in results:
        print(f"  {div}")
        print(f"  Msg #    : {r['msg_id']}")
        print(f"  Timestamp: {r['timestamp']}")
        print(f"  Status   : {r['status']}")
        print(f"  Content  : {r['plaintext']}")

    print(f"\n  {DIV}")
    ok("MAIN", "Session complete")
    print(f"  {DIV}\n")