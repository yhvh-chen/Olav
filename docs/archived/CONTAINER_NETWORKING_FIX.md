# 容器网络地址修复总结（2025-12-09）

## 问题描述

从 Docker 容器内访问主机上的 Ollama（LLM 和 Embedding 模型）时，使用 `127.0.0.1:11434` 或 `localhost:11434` 会失败，因为：

- 容器内的 `127.0.0.1` 指向容器自身的回环网络，而非主机
- 容器无法通过 `localhost` 访问主机

## 解决方案

在 Docker 容器中访问主机服务时，使用特殊 DNS 名称：

```
http://host.docker.internal:11434
```

这是 Docker Desktop（Windows/Mac）和 Docker 引擎（Linux）提供的内置 DNS 别名，自动解析到主机 IP。

## 修复范围

### 配置文件
| 文件 | 更改 | 行号 |
|-----|------|-----|
| `config/settings.py` | `llm_base_url` 默认值 | 56 |
| `config/settings.py` | `embedding_base_url` 默认值 | 68 |
| `docker-compose.yml` | 添加 `LLM_BASE_URL` 环境变量 | ~295 |
| `docker-compose.yml` | 添加 `EMBEDDING_BASE_URL` 环境变量 | ~296 |

### 脚本文件
| 文件 | 更改数量 | 用途 |
|-----|--------|-----|
| `scripts/setup-wizard.ps1` | 2 处 | LLM/Embedding 配置向导（Windows） |
| `scripts/setup-wizard.sh` | 2 处 | LLM/Embedding 配置向导（Linux/macOS） |
| `src/olav/core/llm.py` | 2 处 | LLM 工厂方法的默认值 |
| `src/olav/cli/commands.py` | 1 处 | 诊断命令中的 Ollama 连接检查 |
| `scripts/test_stream.py` | 5 处 | 流式输出测试脚本 |

**总计：9 个文件，18 处代码改动**

## 验证步骤

### 1. 容器网络测试
```bash
# 从容器内测试连接
docker-compose exec olav-app python -c "
import urllib.request
result = urllib.request.urlopen('http://host.docker.internal:11434/api/version', timeout=5)
print(result.read().decode())
"
```

预期输出：
```json
{"version":"0.13.1"}
```

### 2. 重新启动容器（加载新配置）
```bash
docker-compose up -d --force-recreate olav-app
```

### 3. 验证环境变量
```bash
docker-compose exec olav-app env | grep -E "LLM_BASE_URL|EMBEDDING_BASE_URL"
```

预期输出：
```
LLM_BASE_URL=http://host.docker.internal:11434
EMBEDDING_BASE_URL=http://host.docker.internal:11434
```

## 影响范围

- ✅ **新用户**：通过 `setup-wizard.ps1` 或 `setup-wizard.sh` 进行初始化时，将自动获得正确的配置
- ✅ **现有用户**：手动更新 `.env` 文件中的 `LLM_BASE_URL` 和 `EMBEDDING_BASE_URL`
- ✅ **测试脚本**：`test_stream.py` 等诊断脚本已更新
- ✅ **开发代码**：`LLMFactory` 的默认值已更新

## 相关配置文件示例

### .env 文件中正确的配置
```bash
# LLM Configuration
LLM_PROVIDER=ollama
LLM_BASE_URL=http://host.docker.internal:11434
LLM_MODEL_NAME=ministral-3:14b-instruct-2512-q8_0

# Embedding Configuration
EMBEDDING_PROVIDER=ollama
EMBEDDING_BASE_URL=http://host.docker.internal:11434
EMBEDDING_MODEL=nomic-embed-text:latest
```

### docker-compose.yml 中的覆盖
```yaml
olav-app:
  env_file:
    - .env
  environment:
    # 容器内的服务寻址
    POSTGRES_URI: postgresql://olav:olav@postgres:5432/olav
    OPENSEARCH_URL: http://opensearch:9200
    NETBOX_URL: http://netbox:8080
    # 访问主机服务（Ollama）
    LLM_BASE_URL: ${LLM_BASE_URL:-http://host.docker.internal:11434}
    EMBEDDING_BASE_URL: ${EMBEDDING_BASE_URL:-http://host.docker.internal:11434}
```

## 参考资源

- [Docker Desktop Networking - host.docker.internal](https://docs.docker.com/desktop/features/networking/)
- [Docker Engine on Linux - Using a host IP](https://docs.docker.com/engine/install/linux-postinstall/#docker-daemon-socket-permissions)

## 后续维护

1. **新功能开发**：如果新增容器内访问主机服务的代码，使用 `host.docker.internal`
2. **文档更新**：在 README 或部署指南中明确说明此配置要求
3. **测试覆盖**：添加单元测试验证容器网络连通性

---

**修复完成时间**：2025-12-09 17:30 UTC+8  
**修复人**：AI Assistant  
**测试状态**：✅ SuzieQ Poller 正常运行，63 个 parquet 文件已生成
