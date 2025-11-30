"""Direct CLI tool test - bypass Agent framework"""

import asyncio
import logging
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from olav.core.settings import settings as env_settings
from olav.tools.nornir_tool import cli_tool

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


async def test_cli_tool_direct():
    """直接测试 CLI 工具，不使用 Agent 框架"""
    
    logger.info("\n" + "=" * 80)
    logger.info("🧪 直接测试 CLI Tool")
    logger.info("=" * 80)
    
    try:
        # 测试设备
        device = "R1"
        command = "show ip interface brief"
        
        logger.info(f"\n📞 执行命令...")
        logger.info(f"  设备: {device}")
        logger.info(f"  命令: {command}")
        
        # 直接调用全局 cli_tool 实例
        result = await cli_tool.ainvoke(
            {
                "device": device,
                "command": command
            }
        )
        
        logger.info("\n" + "=" * 80)
        logger.info("📊 执行结果")
        logger.info("=" * 80)
        
        logger.info(f"\n成功: {result.get('success', False)}")
        
        if result.get('success'):
            output = result.get('output', [])
            parsed = result.get('parsed', False)
            
            logger.info(f"解析: {parsed}")
            logger.info(f"接口数量: {len(output) if isinstance(output, list) else 'N/A'}")
            
            if isinstance(output, list) and len(output) > 0:
                logger.info(f"\n接口列表 (前 5 个):")
                for idx, intf in enumerate(output[:5], 1):
                    logger.info(f"  {idx}. {intf}")
            else:
                logger.info(f"\n输出:")
                logger.info(str(output)[:500])
        else:
            error = result.get('error', 'Unknown error')
            logger.error(f"错误: {error}")
        
        logger.info("\n✅ CLI Tool 测试完成!")
        return result.get('success', False)
        
    except Exception as e:
        logger.error(f"\n❌ 测试失败: {e}", exc_info=True)
        return False


async def main():
    logger.info("\n" + "=" * 80)
    logger.info("🚀 OLAV CLI Tool 直接测试")
    logger.info("=" * 80)
    
    logger.info("\n📋 环境检查:")
    logger.info(f"  NetBox URL: {env_settings.netbox_url}")
    logger.info(f"  Device User: {env_settings.device_username}")
    
    success = await test_cli_tool_direct()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    # Windows 需要 SelectorEventLoop
    import platform
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
