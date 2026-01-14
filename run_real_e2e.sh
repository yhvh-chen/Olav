#!/bin/bash

echo "=================================================="
echo "  真实 E2E 测试：恢复示例数据并运行导入"
echo "=================================================="
echo ""

# 1. 从备份恢复示例数据
echo "【Step 1】从备份恢复数据"
echo "==========================================="

backup_sync="data/e2e_test_backups/sync_20260113_192506"
target_sync="data/sync/2026-01-13"

if [ -d "$backup_sync" ]; then
    echo "✅ 恢复同步数据..."
    mkdir -p data/sync
    cp -r "$backup_sync" "$target_sync"
    
    # 更新 latest 链接
    cd data/sync
    rm -f latest
    ln -s "2026-01-13" latest
    cd /home/yhvh/Olav
    
    echo "✅ 同步数据已恢复"
    
    # 显示数据统计
    echo ""
    echo "【数据统计】"
    if [ -d "$target_sync/raw" ]; then
        raw_count=$(find "$target_sync/raw" -type f | wc -l)
        echo "  Raw 文件数: $raw_count"
    fi
    
    if [ -d "$target_sync/parsed" ]; then
        parsed_count=$(find "$target_sync/parsed" -type f | wc -l)
        echo "  Parsed 文件数: $parsed_count"
    fi
else
    echo "❌ 找不到备份数据: $backup_sync"
    exit 1
fi

# 2. 运行导入器
echo ""
echo "【Step 2】运行 TopologyImporter"
echo "==========================================="

cd /home/yhvh/Olav

uv run python3 << 'PYTHON'
import sys
sys.path.insert(0, '/home/yhvh/Olav')

from src.olav.tools.topology_importer import TopologyImporter
from pathlib import Path

# 运行导入
print("📥 开始导入...")
db_path = Path("/home/yhvh/Olav/.olav/data/topology.db")
sync_dir = Path("/home/yhvh/Olav/data/sync/2026-01-13")

importer = TopologyImporter(str(db_path))
importer.import_from_parsed_json(str(sync_dir))
importer.commit()
importer.close()

print("✅ 导入完成")
PYTHON

# 3. 验证结果
echo ""
echo "【Step 3】验证结果"
echo "==========================================="

uv run python3 << 'PYTHON'
import duckdb
from pathlib import Path

db_path = Path("/home/yhvh/Olav/.olav/data/topology.db")
conn = duckdb.connect(str(db_path))

print("\n【数据库统计】")
result = conn.execute("""
    SELECT COUNT(*) as total,
           COUNT(DISTINCT local_device) as devices,
           COUNT(DISTINCT protocol) as protocols
    FROM topology_links
""").fetchall()

if result:
    total, devices, protocols = result[0]
    print(f"  📊 总链接数: {total}")
    print(f"  🔗 设备数: {devices}")
    print(f"  📡 协议数: {protocols}")
    
    if total > 0:
        print("\n【按设备分布】")
        links = conn.execute("""
            SELECT local_device, COUNT(*) as count
            FROM topology_links
            GROUP BY local_device
            ORDER BY count DESC
        """).fetchall()
        
        for device, count in links:
            print(f"  {device}: {count} 条")
        
        print("\n【样本数据】")
        samples = conn.execute("""
            SELECT local_device, remote_device, local_port, remote_port, protocol
            FROM topology_links
            LIMIT 5
        """).fetchall()
        
        for local, remote, lport, rport, proto in samples:
            print(f"  {local} → {remote} | {lport} → {rport} | {proto}")

conn.close()
PYTHON

echo ""
echo "=================================================="
echo "  ✅ 真实 E2E 测试完成"
echo "=================================================="

