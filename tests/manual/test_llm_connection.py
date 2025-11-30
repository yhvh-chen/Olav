"""Test LLM connection with OpenRouter API."""

import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_llm_connection():
    """Test basic LLM connection."""
    try:
        from olav.core.llm import LLMFactory
        from olav.core.settings import settings
        from config.settings import LLMConfig
        
        logger.info("\n" + "=" * 80)
        logger.info("🧪 测试 LLM 连接 (OpenRouter API)")
        logger.info("=" * 80)
        
        # Show configuration
        logger.info(f"\n📋 配置信息:")
        logger.info(f"  Provider: {settings.llm_provider}")
        logger.info(f"  Model: {settings.llm_model_name}")
        logger.info(f"  Base URL: {LLMConfig.BASE_URL}")
        logger.info(f"  API Key: {settings.llm_api_key[:20]}...{settings.llm_api_key[-10:]}")
        logger.info(f"  API Key 长度: {len(settings.llm_api_key)}")
        
        # Create model
        logger.info(f"\n🔧 创建 LLM 实例...")
        model = LLMFactory.get_chat_model()
        logger.info(f"✓ 模型创建成功")
        logger.info(f"  类型: {type(model).__name__}")
        logger.info(f"  模型名称: {model.model_name}")
        
        # Test simple invocation
        logger.info(f"\n📞 测试简单调用...")
        from langchain_core.messages import HumanMessage
        
        response = model.invoke([
            HumanMessage(content="请用一句话回复：你是谁？")
        ])
        
        logger.info(f"✓ 调用成功")
        logger.info(f"  响应: {response.content}")
        logger.info(f"  Token 使用: {response.response_metadata.get('token_usage', {})}")
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ LLM 连接测试通过！")
        logger.info("=" * 80)
        
        return True
        
    except Exception as e:
        logger.error(f"\n❌ LLM 连接失败: {e}", exc_info=True)
        logger.info("\n💡 排查步骤:")
        logger.info("  1. 检查 .env 文件中的 LLM_API_KEY")
        logger.info("  2. 验证 OpenRouter API Key 有效性")
        logger.info("  3. 检查网络连接到 https://openrouter.ai")
        logger.info("  4. 验证模型名称: deepseek/deepseek-chat-v3.1")
        return False


if __name__ == "__main__":
    success = test_llm_connection()
    sys.exit(0 if success else 1)
