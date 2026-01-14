#!/usr/bin/env python
"""
拓扑导入脚本 - 执行Parsed JSON导入
"""

import sys
sys.path.insert(0, '/home/yhvh/Olav/src')

from olav.tools.topology_importer import TopologyImporter

if __name__ == "__main__":
    # 初始化导入器
    importer = TopologyImporter(".olav/data/topology.db")
    
    sync_dir = "data/sync/2026-01-13"
    
    # 使用Parsed JSON进行导入
    stats = importer.import_from_parsed_json(sync_dir)
    
    # 提交更改
    importer.commit()
    importer.close()
    
    print("\n✅ 导入完成!")
