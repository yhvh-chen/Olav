"""Test Nornir + NetBox integration - List devices and execute show version."""

import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s"
)
logger = logging.getLogger(__name__)


def test_netbox_devices():
    """List all devices from NetBox via Nornir."""
    try:
        from olav.core.settings import settings
        
        logger.info("\n" + "=" * 80)
        logger.info("🔍 NetBox 设备清单测试")
        logger.info("=" * 80)
        
        # Check configuration
        logger.info(f"\n📋 NetBox 配置:")
        logger.info(f"  URL: {settings.netbox_url}")
        logger.info(f"  Token: {settings.netbox_token[:20] if settings.netbox_token else 'NOT SET'}...")
        
        if not settings.netbox_url or not settings.netbox_token:
            logger.error("❌ NetBox URL 或 Token 未配置")
            logger.info("💡 请检查 .env 文件中的 NETBOX_URL 和 NETBOX_TOKEN")
            return False
        
        # Initialize Nornir with NetBox inventory
        logger.info(f"\n🔧 初始化 Nornir (NetBox Inventory)...")
        from nornir import InitNornir
        from nornir_netbox.plugins.inventory import NBInventory
        
        nr = InitNornir(
            inventory={
                "plugin": "NBInventory",
                "options": {
                    "nb_url": settings.netbox_url,
                    "nb_token": settings.netbox_token,
                    "ssl_verify": False,
                    "filter_parameters": {
                        "tag": ["olav-managed"]
                    }
                }
            },
            runner={
                "plugin": "threaded",
                "options": {
                    "num_workers": 10
                }
            },
            logging={
                "enabled": False
            }
        )
        
        logger.info(f"✓ Nornir 初始化成功")
        
        # List all devices
        logger.info(f"\n📦 设备清单 (tag: olav-managed):")
        logger.info("-" * 80)
        
        if not nr.inventory.hosts:
            logger.warning("⚠️  未发现任何设备")
            logger.info("\n💡 请确认:")
            logger.info("  1. NetBox 中已添加设备")
            logger.info("  2. 设备已打上 'olav-managed' 标签")
            logger.info("  3. NetBox API 可访问: curl -H 'Authorization: Token xxx' http://localhost:8080/api/dcim/devices/")
            return False
        
        device_count = len(nr.inventory.hosts)
        logger.info(f"发现 {device_count} 台设备:\n")
        
        for idx, (hostname, host) in enumerate(nr.inventory.hosts.items(), 1):
            logger.info(f"  {idx}. {hostname}")
            logger.info(f"     - IP: {host.hostname if hasattr(host, 'hostname') else 'N/A'}")
            logger.info(f"     - Platform: {host.platform if hasattr(host, 'platform') else 'N/A'}")
            logger.info(f"     - Groups: {', '.join(host.groups) if host.groups else 'None'}")
            logger.info("")
        
        logger.info("=" * 80)
        logger.info(f"✅ 设备清单测试通过 ({device_count} 台设备)")
        logger.info("=" * 80)
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ 缺少依赖: {e}")
        logger.info("💡 安装 nornir-netbox: uv add nornir-netbox")
        return False
    except Exception as e:
        logger.error(f"❌ 设备清单获取失败: {e}", exc_info=True)
        logger.info("\n💡 排查步骤:")
        logger.info("  1. 确认 NetBox 容器运行: docker ps | grep netbox")
        logger.info("  2. 检查 NetBox API: curl http://localhost:8080/api/")
        logger.info("  3. 验证 Token: 登录 NetBox UI → Admin → API Tokens")
        logger.info("  4. 检查设备标签: dcim/devices/ 中的 tags 字段")
        return False


def test_show_version():
    """Execute 'show version' on all devices."""
    try:
        from olav.core.settings import settings
        from nornir import InitNornir
        from nornir_netmiko.tasks import netmiko_send_command
        
        logger.info("\n" + "=" * 80)
        logger.info("🚀 执行 'show version' 测试")
        logger.info("=" * 80)
        
        # Initialize Nornir
        logger.info(f"\n🔧 初始化 Nornir...")
        nr = InitNornir(
            inventory={
                "plugin": "NBInventory",
                "options": {
                    "nb_url": settings.netbox_url,
                    "nb_token": settings.netbox_token,
                    "ssl_verify": False,
                    "filter_parameters": {
                        "tag": ["olav-managed"]
                    }
                }
            },
            runner={
                "plugin": "threaded",
                "options": {
                    "num_workers": 5
                }
            },
            logging={
                "enabled": False
            }
        )
        
        if not nr.inventory.hosts:
            logger.warning("⚠️  没有设备可测试")
            return False
        
        logger.info(f"✓ 发现 {len(nr.inventory.hosts)} 台设备")
        
        # Set credentials from environment
        for host in nr.inventory.hosts.values():
            host.username = settings.device_username
            host.password = settings.device_password
        
        logger.info(f"✓ 已设置设备凭证 (username: {settings.device_username})")
        
        # Execute show version
        logger.info(f"\n📞 执行命令: show version")
        logger.info("-" * 80)
        
        result = nr.run(
            task=netmiko_send_command,
            command_string="show version"
        )
        
        # Display results
        success_count = 0
        fail_count = 0
        
        for hostname, multi_result in result.items():
            logger.info(f"\n🖥️  设备: {hostname}")
            logger.info("-" * 80)
            
            if multi_result.failed:
                fail_count += 1
                logger.error(f"❌ 执行失败")
                logger.error(f"   错误: {multi_result[0].exception if multi_result[0].exception else multi_result[0].result}")
            else:
                success_count += 1
                output = multi_result[0].result
                # Show first 500 chars
                preview = output[:500] if len(output) > 500 else output
                logger.info(f"✓ 执行成功")
                logger.info(f"\n输出预览 (前 500 字符):")
                logger.info(preview)
                if len(output) > 500:
                    logger.info(f"\n... (输出共 {len(output)} 字符)")
        
        logger.info("\n" + "=" * 80)
        logger.info("📊 执行结果统计")
        logger.info("=" * 80)
        logger.info(f"  成功: {success_count}/{len(result)} 台设备")
        logger.info(f"  失败: {fail_count}/{len(result)} 台设备")
        
        if success_count > 0:
            logger.info("\n✅ show version 测试通过")
            return True
        else:
            logger.error("\n❌ 所有设备执行失败")
            logger.info("\n💡 可能的原因:")
            logger.info("  1. 设备凭证错误 (检查 DEVICE_USERNAME/DEVICE_PASSWORD)")
            logger.info("  2. 设备 IP 不可达 (检查网络连接)")
            logger.info("  3. SSH 未启用 (检查设备 SSH 配置)")
            logger.info("  4. Platform 类型错误 (检查 NetBox 设备平台)")
            return False
        
    except ImportError as e:
        logger.error(f"❌ 缺少依赖: {e}")
        logger.info("💡 安装依赖:")
        logger.info("  uv add nornir")
        logger.info("  uv add nornir-netbox")
        logger.info("  uv add nornir-netmiko")
        return False
    except Exception as e:
        logger.error(f"❌ 命令执行失败: {e}", exc_info=True)
        return False


def main():
    """Run all tests."""
    logger.info("\n" + "=" * 80)
    logger.info("🧪 Nornir + NetBox + CLI 集成测试")
    logger.info("=" * 80)
    
    # Test 1: List devices
    test1_passed = test_netbox_devices()
    
    if not test1_passed:
        logger.error("\n❌ 设备清单测试失败，跳过 show version 测试")
        sys.exit(1)
    
    # Test 2: Execute show version
    test2_passed = test_show_version()
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("📊 测试总结")
    logger.info("=" * 80)
    logger.info(f"  设备清单: {'✅ PASS' if test1_passed else '❌ FAIL'}")
    logger.info(f"  Show Version: {'✅ PASS' if test2_passed else '❌ FAIL'}")
    
    if test1_passed and test2_passed:
        logger.info("\n🎉 所有测试通过！")
        sys.exit(0)
    else:
        logger.info("\n❌ 部分测试失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
