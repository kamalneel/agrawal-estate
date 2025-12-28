#!/usr/bin/env python
import sys
print("Starting import test...")
sys.stdout.flush()

try:
    from app.main import app
    print("SUCCESS: Import successful")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()


