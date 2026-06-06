import asyncio
import glob
import os
import sys
from pathlib import Path

# Add the server root to sys.path
_SERVER_ROOT = Path(__file__).resolve().parents[3]
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

from app.api.agents.templates import PREBUILT_AGENTS_DIR  # noqa: E402


async def main():
    print("Testing Agent Templates functionality...")
    
    # 1. Check if the directory exists
    print(f"Prebuilt agents directory: {PREBUILT_AGENTS_DIR}")
    if not os.path.exists(PREBUILT_AGENTS_DIR):
        print("Directory does not exist!")
        return
        
    # 2. List templates
    yaml_files = glob.glob(os.path.join(PREBUILT_AGENTS_DIR, "*.yaml"))
    print(f"Found {len(yaml_files)} template files.")
    
    for file_path in yaml_files:
        print(f" - {os.path.basename(file_path)}")
        
    print("\nTest completed successfully. The template engine is present and can find templates.")

if __name__ == "__main__":
    asyncio.run(main())
