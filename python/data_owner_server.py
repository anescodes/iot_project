import socket
import json
import binascii
import os
import time
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# --- الإعدادات ---
AES_KEY_IOT = bytes([0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,0x09,0x0A,0x0B,0x0C,0x0D,0x0E,0x0F,0x10])
FOG_ADDR = ("127.0.0.1", 5000)
COOJA_ADDR = ("127.0.0.1", 60001)

def run_data_owner():
    print("\n🚀 [DO] STARTING DATA OWNER...")
    
    try:
        # 1) الاتصال بالـ Fog لبدء مرحلة الإعداد (Initialization)
        fog_sock = socket.socket()
        fog_sock.connect(FOG_ADDR)
        f_fog = fog_sock.makefile('r')

        # استلام المعرف (ID) ومفتاح الجلسة (KI) والسياسات المتاحة
        init_data = json.loads(f_fog.readline().strip())
        OWNER_ID = init_data["id"]
        KI_HEX = init_data["ki"]
        POLICIES = init_data["policies"]
        
        print(f"🟢 [DO] Connected to Fog. ID: {OWNER_ID}")
        print(f"🔑 [DO] Session Key (KI) Received: {KI_HEX[:10]}...")

        # 2) اختيار السياسة وإرسالها للـ Fog (ليقوم الـ Fog بتخزين الـ CKI في الجدول)
        selected_policy = POLICIES[0] # اختيار أول سياسة تلقائياً
        fog_sock.sendall((json.dumps({"selected_policy": selected_policy}) + "\n").encode())
        print(f"📤 [DO] Policy Choice Sent: {selected_policy}")
        print("--------------------------------------------------")

        # 3) حلقة بث البيانات (Streaming Phase)
        # هنا يقوم الـ DO باستقبال بيانات IoT، تشفيرها بـ KI، وإرسالها للـ Fog
        print(f"📡 [DO] Entering Streaming Mode...")
        
        while True:
            try:
                # الاتصال بمحاكي Cooja (IoT Node)
                iot_sock = socket.socket()
                iot_sock.connect(COOJA_ADDR)
                f_iot = iot_sock.makefile('r')
                
                while True:
                    line = f_iot.readline().strip()
                    if not line: break
                    if "[" in line: continue # تجاهل سجلات النظام (Logs)

                    # --- فك تشفير البيانات القادمة من IoT (AES-ECB) ---
                    cipher_iot = AES.new(AES_KEY_IOT, AES.MODE_ECB)
                    # تحويل النص من Hex إلى بايتات وفك تشفيره
                    plaintext = cipher_iot.decrypt(binascii.unhexlify(line)).decode().strip("\x00")
                    print(f"🔓 [FROM IoT] Raw Data: {plaintext}")

                    # --- إعادة التشفير باستخدام مفتاح الجلسة KI (AES-CBC) ---
                    iv = os.urandom(16) # توليد IV عشوائي لكل حزمة لزيادة الأمان
                    cipher_ki = AES.new(binascii.unhexlify(KI_HEX), AES.MODE_CBC, iv)
                    ciphertext_ki = cipher_ki.encrypt(pad(plaintext.encode(), 16))
                    
                    # تحويل النتيجة لـ Hex للإرسال
                    ct_hex = binascii.hexlify(ciphertext_ki).decode()
                    iv_hex = binascii.hexlify(iv).decode()

                    # 4) إرسال البيانات المشفرة فقط للـ Fog
                    # لاحظ أننا لا نرسل الـ KI ولا الـ CKI هنا
                    packet = {
                        "owner_id": OWNER_ID,
                        "payload": {
                            "iv": iv_hex,
                            "data": ct_hex
                        }
                    }
                    fog_sock.sendall((json.dumps(packet) + "\n").encode())
                    print(f"✅ [TO FOG] Encrypted Packet Sent: {ct_hex[:20]}...")

            except (socket.error, ConnectionRefusedError):
                print("⚠ Waiting for IoT Node (Cooja)...")
                time.sleep(2)
                
    except Exception as e:
        print(f"❌ [FATAL ERROR]: {e}")

if __name__ == "__main__":
    run_data_owner()