import traceback

text = "Hello world"

try:
    from deep_translator import GoogleTranslator, MyMemoryTranslator
    print("[✓] deep-translator imported successfully.")
except ImportError:
    print("[✗] ImportError: deep-translator is NOT installed in this environment.")
    print("    Fix: Run `pip install deep-translator`")
    exit(1)

# 1. Test Google Translator directly
print("\n--- Testing GoogleTranslator ---")
try:
    g_res = GoogleTranslator(source="en", target="zh-TW").translate(text)
    print(f"[✓] Google success: '{g_res}'")
except Exception as e:
    print(f"[✗] Google failed: {type(e).__name__}: {e}")
    traceback.print_exc()

# 2. Test MyMemory Translator directly
print("\n--- Testing MyMemoryTranslator ---")
try:
    # Note: MyMemory requires 2-letter ISO or specific pairs (en-GB / zh-TW)
    m_res = MyMemoryTranslator(source="en-GB", target="zh-TW").translate(text)
    print(f"[✓] MyMemory success: '{m_res}'")
except Exception as e:
    print(f"[✗] MyMemory failed: {type(e).__name__}: {e}")
    traceback.print_exc()
