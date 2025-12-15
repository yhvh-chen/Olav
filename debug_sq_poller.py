import pandas as pd
import os
import glob

def check_sq_poller():
    base_path = "data/suzieq-parquet/sqPoller/sqvers=3.0/namespace=default/hostname=192.168.100.101"
    if not os.path.exists(base_path):
        print(f"Path not found: {base_path}")
        return

    files = glob.glob(os.path.join(base_path, "*.parquet"))
    if not files:
        print("No parquet files found.")
        return

    # Find latest interfaces file
    if_files = []
    for file in files:
        try:
            df = pd.read_parquet(file)
            if 'service' in df.columns and (df['service'] == 'interfaces').any():
                if_files.append((file, os.path.getmtime(file)))
        except:
            pass
            
    if not if_files:
        print("No interfaces files found.")
        return

    latest_if = max(if_files, key=lambda x: x[1])[0]
    print(f"Reading latest Interfaces file: {latest_if}")
    
    df = pd.read_parquet(latest_if)
    print(df.to_string())

if __name__ == "__main__":
    check_sq_poller()
