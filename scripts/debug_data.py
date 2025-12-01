
import asyncio
import os
import pandas as pd
import asyncpg
import json
from pathlib import Path

# Set env for postgres
os.environ["POSTGRES_URI"] = "postgresql://olav:OlavPG123!@localhost:55432/olav"

async def inspect_postgres():
    print("\n--- Inspecting Postgres Checkpoints ---")
    uri = os.environ["POSTGRES_URI"]
    try:
        conn = await asyncpg.connect(uri)
        
        # Check checkpoint_writes
        print("\nChecking checkpoint_writes table...")
        writes_count = await conn.fetchval("SELECT COUNT(*) FROM checkpoint_writes")
        print(f"Total writes: {writes_count}")
        
        if writes_count > 0:
            row = await conn.fetchrow("SELECT * FROM checkpoint_writes LIMIT 1")
            print("Sample write keys:", row.keys())
            print("Sample write channel:", row['channel'])
            # print("Sample write value:", row['value']) # Might be binary
        
        # Find a checkpoint with messages in channel_values
        print("\nSearching for checkpoint with messages...")
        query = """
            SELECT thread_id, checkpoint 
            FROM checkpoints 
            WHERE thread_id = 'api-test-session-001'
            ORDER BY checkpoint_id DESC
            LIMIT 1
        """
        row = await conn.fetchrow(query)
        if row:
            print(f"Found thread with messages: {row['thread_id']}")
            cp = json.loads(row['checkpoint'])
            cv = cp.get('channel_values', {})
            print("channel_values keys:", cv.keys())
            if 'messages' in cv:
                print(f"Message count: {len(cv['messages'])}")
                print("First message sample:", str(cv['messages'][0])[:100])
        else:
            print("No checkpoints found for api-test-session-001")
            
        await conn.close()
    except Exception as e:
        print(f"Postgres inspection failed: {e}")

def inspect_parquet():
    print("\n--- Inspecting Parquet Inventory ---")
    path = Path("data/suzieq-parquet/coalesced/device")
    if not path.exists():
        path = Path("data/suzieq-parquet/device")
    
    if not path.exists():
        print(f"Path not found: {path}")
        return

    try:
        df = pd.read_parquet(path)
        if 'bootupTimestamp' in df.columns:
            print("\nBootupTimestamp values (head):", df['bootupTimestamp'].head().tolist())
            print("BootupTimestamp dtype:", df['bootupTimestamp'].dtype)
            
    except Exception as e:
        print(f"Parquet inspection failed: {e}")

if __name__ == "__main__":
    inspect_parquet()
    asyncio.run(inspect_postgres())
