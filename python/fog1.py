"""
╔══════════════════════════════════════════════════════════════╗
║                    FOG SERVER  (fog_server.py)                ║
║                                                               ║
║  Port 5000 ← IoT devices connect here                         ║
║  Port 6000 → Cloud server (forwards encrypted sensor data)    ║
║  Port 8545 → Ganache blockchain (stores CKI)                  ║
╚══════════════════════════════════════════════════════════════╝
"""

import socket
import json
import binascii
import traceback
from web3 import Web3
from charm.toolbox.pairinggroup import PairingGroup, GT, extract_key
from charm.schemes.abenc.abenc_maabe_yj14 import MAABE
from attribute_authority import aa, fog_payload

# ═══════════════════════════════════════════════════════════════
# 🎨  PRINT HELPERS
# ═══════════════════════════════════════════════════════════════
DIV  = "═" * 60
div  = "─" * 60
TICK = "✅"
FAIL = "❌"
WARN = "⚠️ "
INFO = "ℹ️ "

def section(title: str):
    print(f"\n{DIV}")
    print(f"  {title}")
    print(DIV)

def ok(tag: str, msg: str):
    print(f"  {TICK} [{tag}] {msg}")

def err(tag: str, msg: str):
    print(f"  {FAIL} [{tag}] {msg}")

def info(tag: str, msg: str):
    print(f"  {INFO} [{tag}] {msg}")

def warn(tag: str, msg: str):
    print(f"  {WARN} [{tag}] {msg}")

# ═══════════════════════════════════════════════════════════════
# 🔐  MA-ABE SETUP
# ═══════════════════════════════════════════════════════════════
section("MA-ABE SETUP")
print("  Initialising pairing group SS512…")
group = PairingGroup('SS512')
maabe = MAABE(group)

print("  Running maabe.setup()…")
GPP, GMK = maabe.setup()
ok("MA-ABE", "Global public parameters (GPP) and master key (GMK) ready")

auth_id     = "AUTH1"
authorities = {}
all_attrs   = aa.get_all_attributes()

print(f"  Setting up authority '{auth_id}' with attributes: {all_attrs}")
maabe.setupAuthority(GPP, auth_id, all_attrs, authorities)
ok("MA-ABE", f"Authority '{auth_id}' initialised")
print(f"  Authority keys available: {list(authorities.keys())}")

# ═══════════════════════════════════════════════════════════════
# 🔗  BLOCKCHAIN CONFIG
# ═══════════════════════════════════════════════════════════════
GANACHE_URL      = "http://127.0.0.1:8545"
CONTRACT_ADDRESS = "0xF7f3752ab7081C8774f1BcfDC18F0E697828fbCf"

CONTRACT_ABI = json.loads("""
[
  {
    "anonymous": false,
    "inputs": [
      {"indexed":false,"internalType":"string","name":"userId","type":"string"},
      {"indexed":false,"internalType":"string","name":"cki","type":"string"}
    ],
    "name": "UserRegistered",
    "type": "event"
  },
  {
    "inputs": [
      {"internalType":"string","name":"_userId","type":"string"},
      {"internalType":"string","name":"_cki","type":"string"}
    ],
    "name": "registerUser",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [{"internalType":"string","name":"_userId","type":"string"}],
    "name": "getUserCKI",
    "outputs": [{"internalType":"string","name":"","type":"string"}],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "inputs": [{"internalType":"string","name":"_userId","type":"string"}],
    "name": "isUserRegistered",
    "outputs": [{"internalType":"bool","name":"","type":"bool"}],
    "stateMutability": "view",
    "type": "function"
  },
  {
    "inputs": [{"internalType":"uint256","name":"","type":"uint256"}],
    "name": "userList",
    "outputs": [{"internalType":"string","name":"","type":"string"}],
    "stateMutability": "view",
    "type": "function"
  }
]
""")

# ═══════════════════════════════════════════════════════════════
# 🔧  SERIALIZATION  (charm element → base64 string)
# ═══════════════════════════════════════════════════════════════
def _serialize(obj):
    """Recursively serialise charm pairing-group elements to base64."""
    try:
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        return binascii.b2a_base64(group.serialize(obj)).decode().strip()
    except Exception as e:
        warn("SERIALIZE", f"Non-element value kept as string — {e}")
        return str(obj)

# ═══════════════════════════════════════════════════════════════
# 🔗  BLOCKCHAIN FUNCTIONS
# ═══════════════════════════════════════════════════════════════
def init_blockchain():
    """Connect to Ganache and return the contract instance."""
    section("BLOCKCHAIN INIT")
    w3 = Web3(Web3.HTTPProvider(GANACHE_URL))

    print(f"  Connecting to Ganache at {GANACHE_URL}…")
    if not w3.is_connected():
        err("BLOCKCHAIN", f"Cannot reach Ganache at {GANACHE_URL}")
        err("BLOCKCHAIN", "Make sure Ganache is running: npx ganache --port 8545")
        return None, None

    ok("BLOCKCHAIN", f"Connected  |  Chain ID: {w3.eth.chain_id}")
    print(f"  Available accounts : {len(w3.eth.accounts)}")
    print(f"  Default account    : {w3.eth.accounts[0]}")

    try:
        contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
        ok("CONTRACT", f"Loaded at {CONTRACT_ADDRESS}")
        return w3, contract
    except Exception as e:
        err("CONTRACT", f"Failed to load contract — {e}")
        traceback.print_exc()
        return None, None


def store_on_blockchain(owner_id: str, cki_data: dict) -> bool:
    """
    Store (owner_id → CKI) on-chain.
    Returns True on success, False on any failure.
    Skips silently if the user is already registered.
    """
    section("BLOCKCHAIN STORE")
    print(f"  Owner ID : {owner_id}")
    print(f"  CKI keys : {list(cki_data.keys())}")

    w3, contract = init_blockchain()
    if contract is None:
        err("BLOCKCHAIN", "Cannot proceed — contract not available")
        return False

    try:
        account = w3.eth.accounts[0]
        print(f"\n  👤 Transacting from: {account}")

        # ── Check if already registered ────────────────────────
        print("  🔍 Checking if user is already registered…")
        exists = contract.functions.isUserRegistered(owner_id).call()
        print(f"  📌 isUserRegistered('{owner_id}') → {exists}")

        if exists:
            warn("BLOCKCHAIN", f"User '{owner_id}' already registered — skipping")
            return True

        # ── Serialise CKI to JSON string ───────────────────────
        cki_string = json.dumps(cki_data)
        print(f"  📦 CKI JSON length : {len(cki_string)} characters")

        # ── Send transaction ───────────────────────────────────
        print("  📤 Sending registerUser() transaction…")
        tx_hash = contract.functions.registerUser(owner_id, cki_string).transact({
            "from" : account,
            "gas"  : 1_000_000,
        })
        print(f"  ⏳ TX submitted — hash: {tx_hash.hex()}")

        # ── Wait for receipt ───────────────────────────────────
        print("  ⏳ Waiting for transaction receipt…")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        # ── Confirm ─────────────────────────────────────────────
        print(f"\n  {div}")
        ok("BLOCKCHAIN", "✅ TRANSACTION CONFIRMED!")
        print(f"  {'🆔 Stored Owner ID':<22}: {owner_id}")
        print(f"  {'📦 Block Number':<22}: {receipt.blockNumber}")
        print(f"  {'⛽ Gas Used':<22}: {receipt.gasUsed}")
        print(f"  {'🧾 TX Hash':<22}: {tx_hash.hex()}")
        print(f"  {'📋 CKI Keys Stored':<22}: {list(cki_data.keys())}")
        print(f"  {div}")

        # ── Verification read-back ──────────────────────────────
        print("\n  🔎 Verifying stored data (read-back)…")
        stored_raw  = contract.functions.getUserCKI(owner_id).call()
        stored_keys = list(json.loads(stored_raw).keys())
        ok("BLOCKCHAIN", f"Read-back successful — CKI keys on-chain: {stored_keys}")

        return True

    except Exception as e:
        err("BLOCKCHAIN", f"Transaction failed — {type(e).__name__}: {e}")
        traceback.print_exc()
        return False

# ═══════════════════════════════════════════════════════════════
# ☁️  CLOUD FORWARD
# ═══════════════════════════════════════════════════════════════
def send_to_cloud(owner_id: str, encrypted_data: str) -> bool:
    """Forward a sensor message to the cloud server (port 6000)."""
    print(f"\n  ☁️  [CLOUD FORWARD] owner='{owner_id}'  data_len={len(str(encrypted_data))}")

    try:
        payload = {"owner_id": owner_id, "data": encrypted_data}
        with socket.create_connection(("127.0.0.1", 6000), timeout=5) as cloud_conn:
            cloud_conn.sendall(json.dumps(payload).encode())
        ok("CLOUD", "Data forwarded successfully")
        return True

    except ConnectionRefusedError:
        err("CLOUD", "Connection refused — is cloud_server.py running on port 6000?")
        return False
    except socket.timeout:
        err("CLOUD", "Connection timed out after 5 seconds")
        return False
    except Exception as e:
        err("CLOUD", f"{type(e).__name__}: {e}")
        traceback.print_exc()
        return False

# ═══════════════════════════════════════════════════════════════
# 🌐  IOT CONNECTION HANDLER
# ═══════════════════════════════════════════════════════════════
def handle_iot(conn, addr):
    """Handle a single IoT device connection end-to-end."""
    section(f"NEW IoT CONNECTION — {addr[0]}:{addr[1]}")

    with conn:
        f = conn.makefile('r')

        # ── 1. Assign owner ID + generate session key KI ───────
        owner_id = "DO_101"
        print(f"  🆔 Assigned owner ID : {owner_id}")

        print("  🎲 Generating random KI (GT element)…")
        ki      = group.random(GT)
        ki_hex  = binascii.hexlify(extract_key(ki)).decode()
        print(f"  🗝️  KI (hex preview) : {ki_hex[:32]}…")
        ok("FOG", "KI generated")

        # ── 2. Send init payload to IoT device ─────────────────
        init_payload = {
            "id"      : owner_id,
            "ki"      : ki_hex,
            "policies": list(fog_payload.keys()),
        }
        print(f"\n  📤 Sending init payload to IoT device…")
        print(f"     Policies offered : {init_payload['policies']}")
        try:
            conn.sendall((json.dumps(init_payload) + "\n").encode())
            ok("FOG", "Init payload sent")
        except Exception as e:
            err("FOG", f"Failed to send init payload — {e}")
            return

        # ── 3. Receive policy choice ────────────────────────────
        print("\n  ⏳ Waiting for policy selection from IoT device…")
        try:
            line = f.readline().strip()
            if not line:
                err("FOG", "IoT device closed connection before sending policy")
                return

            print(f"  📥 Raw policy response : {line}")
            choice     = json.loads(line)
            policy_key = choice.get("selected_policy")

            if policy_key not in fog_payload:
                err("FOG", f"Unknown policy '{policy_key}' — valid: {list(fog_payload.keys())}")
                return

            policy_expr = fog_payload[policy_key]
            print(f"  🎯 Selected policy   : {policy_key}")
            print(f"  📜 Policy expression : {policy_expr}")
            ok("FOG", "Policy choice accepted")

        except json.JSONDecodeError as e:
            err("FOG", f"Could not parse policy JSON — {e}")
            err("FOG", f"Raw data was: {line!r}")
            return
        except Exception as e:
            err("FOG", f"Error reading policy choice — {e}")
            traceback.print_exc()
            return

        # ── 4. Encrypt KI under the chosen policy → CKI ────────
        print(f"\n  🔐 Encrypting KI under policy '{policy_key}'…")
        try:
            ct = maabe.encrypt(GPP, policy_expr, ki, authorities[auth_id])
            ok("MA-ABE", "Encryption successful")
            print(f"  📦 CKI top-level keys : {list(ct.keys())}")
        except Exception as e:
            err("MA-ABE", f"Encryption failed — {e}")
            traceback.print_exc()
            return

        # ── 5. Serialise CKI ────────────────────────────────────
        print("\n  🔧 Serialising CKI (charm elements → base64)…")
        try:
            cki_serialized = _serialize(ct)
            ok("SERIALIZE", "CKI serialised successfully")
        except Exception as e:
            err("SERIALIZE", f"Serialisation failed — {e}")
            traceback.print_exc()
            return

        # ── 6. Store CKI on blockchain ──────────────────────────
        success = store_on_blockchain(owner_id, cki_serialized)
        if not success:
            warn("FOG", "Blockchain store failed — continuing with streaming anyway")

        # ── 7. Stream encrypted sensor data → cloud ─────────────
        section("STREAMING MODE — forwarding sensor data to Cloud")
        msg_count = 0

        while True:
            try:
                line = f.readline().strip()
            except Exception as e:
                err("STREAM", f"Socket read error — {e}")
                break

            if not line:
                info("STREAM", "IoT device closed the connection (empty line)")
                break

            msg_count += 1
            print(f"\n  📦 [MSG #{msg_count}] Raw line length: {len(line)}")

            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                err("STREAM", f"JSON parse error — {e}")
                err("STREAM", f"Raw: {line[:80]!r}")
                continue

            # Validate expected fields
            if "owner_id" not in data:
                warn("STREAM", "Missing 'owner_id' in message — skipping")
                continue
            if "payload" not in data or "data" not in data.get("payload", {}):
                warn("STREAM", "Missing 'payload.data' in message — skipping")
                continue

            oid           = data["owner_id"]
            payload_data  = data["payload"]["data"]

            print(f"  👤 Owner ID  : {oid}")
            print(f"  📊 Data preview : {str(payload_data)[:60]}…")

            send_to_cloud(oid, payload_data)

        print(f"\n  {div}")
        info("STREAM", f"Session ended — total messages forwarded: {msg_count}")
        print(f"  {div}")

# ═══════════════════════════════════════════════════════════════
# 🌐  MAIN SERVER LOOP
# ═══════════════════════════════════════════════════════════════
def start_fog():
    section("FOG SERVER STARTING")

    try:
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 5000))
        s.listen(5)
    except OSError as e:
        err("FOG", f"Cannot bind to port 5000 — {e}")
        err("FOG", "Is another fog server already running?")
        return

    print(f"  🌐 Listening on 127.0.0.1:5000  (IoT devices)")
    print(f"  ☁️  Will forward data to        127.0.0.1:6000  (Cloud)")
    print(f"  🔗 Will store CKI on           127.0.0.1:8545  (Blockchain)")
    print(f"\n  ⏳ Waiting for IoT connections…")

    conn_count = 0
    while True:
        try:
            conn, addr = s.accept()
            conn_count += 1
            print(f"\n  🟢 Connection #{conn_count} accepted from {addr[0]}:{addr[1]}")
            handle_iot(conn, addr)
        except KeyboardInterrupt:
            print("\n\n  🛑 Fog server stopped by user (Ctrl+C)")
            break
        except Exception as e:
            err("FOG", f"Unexpected error in accept loop — {e}")
            traceback.print_exc()

    s.close()
    print("  🔌 Fog server socket closed.")


if __name__ == "__main__":
    start_fog()