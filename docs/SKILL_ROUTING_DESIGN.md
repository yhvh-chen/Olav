# OLAV Skill 路由优化设计

## 核心问题

**如何在不硬编码的情况下实现快速路由，同时保持 Skill 优先的设计？**

---

## 标准解决方案对比

### 方案 1: LangChain Tool Description (标准做法)

LangChain 的设计是**让 LLM 自己选择 Tool**，每个 Tool 有详细的 `description`：

```python
@tool
def quick_query(device: str, query: str) -> str:
    """Execute simple network queries (1-2 commands).
    
    Use this for:
    - Interface status checks (show interface, show ip interface brief)
    - Version information (show version)
    - Routing table queries (show ip route)
    - BGP/OSPF neighbor status
    
    Args:
        device: Device name (R1, R2, etc.)
        query: Natural language query
    """
```

**优点**: 
- 无需额外 Router
- LLM ReAct 循环自动选择
- Tool description 就是索引

**缺点**: 
- 每次都要 LLM 决策
- Tool 数量多时 token 消耗大
- 复杂流程难以表达 (Skill 是多 Tool 组合)

### 方案 2: Skill as Prompt (当前 OLAV)

OLAV 的设计是 **Skill = Markdown 指令**，比 Tool 更灵活：

```yaml
# .olav/skills/quick-query.md
---
id: quick-query
description: "Simple status query"
examples:
  - "R1 interface status"
---
# Quick Query
## Execution Strategy
1. Parse device aliases
2. Use search_capabilities
3. Execute 1-2 commands
```

**优点**:
- Skill 可以包含复杂执行策略
- 非代码人员可编辑
- 支持多 Tool 组合

**缺点**:
- 需要额外的 Skill Router (LLM 调用)
- 每次查询都要路由

---

## 最佳实践: Embedding + Skill 优先

### 核心思想

**不硬编码触发词，而是利用 Skill 自身的 `description` + `examples` 生成 embedding 索引**

```
启动时:
  遍历 Skills → 生成 embedding (description + examples)
  存入向量索引

查询时:
  用户查询 → embedding
  向量相似度搜索 → top-1 Skill
  如果相似度 > 0.8: 直接使用
  如果相似度 < 0.8: LLM Router 决策
```

### 设计优势

| 特性 | 硬编码触发词 | Embedding 索引 |
|------|-------------|----------------|
| 灵活性 | ❌ 需要手动维护 | ✅ 自动从 Skill 提取 |
| 准确性 | ⚠️ 关键词匹配有限 | ✅ 语义相似度 |
| 扩展性 | ❌ 每个 Skill 加词 | ✅ 加 Skill 自动索引 |
| 性能 | ✅ O(n) 字符串匹配 | ✅ O(1) 向量搜索 |

---

## 推荐实现

### Step 1: 增强 Skill Frontmatter

```yaml
# .olav/skills/quick-query.md
---
id: quick-query
intent: query
complexity: simple
description: "Simple status query that can be completed with 1-2 commands"
# 新增: semantic_hints - 用于生成 embedding 的语义提示
semantic_hints:
  - "查询设备接口状态"
  - "检查路由表"
  - "查看 BGP 邻居"
  - "show interface"
  - "show ip route"
examples:
  - "R1 interface status"
  - "Check R2 BGP neighbors"
enabled: true
---
```

### Step 2: Skill Embedding 索引

```python
# src/olav/core/skill_embedder.py

from functools import lru_cache
from sentence_transformers import SentenceTransformer
import numpy as np

class SkillEmbedder:
    """Skill Embedding 索引器 - 基于语义相似度的快速路由."""
    
    def __init__(self, skill_loader: SkillLoader):
        self.skill_loader = skill_loader
        # 使用轻量级本地模型 (50ms 推理)
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self._embeddings: dict[str, np.ndarray] = {}
        self._build_index()
    
    def _build_index(self):
        """启动时构建 embedding 索引."""
        skills = self.skill_loader.load_all()
        for skill_id, skill in skills.items():
            # 合并 description + examples + semantic_hints
            text = self._build_skill_text(skill)
            self._embeddings[skill_id] = self.model.encode(text)
    
    def _build_skill_text(self, skill: Skill) -> str:
        """从 Skill 构建用于 embedding 的文本."""
        parts = [
            skill.description,
            *skill.examples,
            *getattr(skill, 'semantic_hints', []),
        ]
        return " | ".join(parts)
    
    def find_skill(self, query: str, threshold: float = 0.75) -> tuple[str | None, float]:
        """基于语义相似度查找最匹配的 Skill.
        
        Returns:
            (skill_id, similarity_score) or (None, 0.0)
        """
        query_emb = self.model.encode(query)
        
        best_skill = None
        best_score = 0.0
        
        for skill_id, skill_emb in self._embeddings.items():
            # 余弦相似度
            score = np.dot(query_emb, skill_emb) / (
                np.linalg.norm(query_emb) * np.linalg.norm(skill_emb)
            )
            if score > best_score:
                best_score = score
                best_skill = skill_id
        
        if best_score >= threshold:
            return best_skill, best_score
        return None, best_score
```

### Step 3: 混合路由策略

```python
# src/olav/core/skill_router.py 修改

class SkillRouter:
    def __init__(self, llm, skill_loader: SkillLoader):
        self.llm = llm
        self.skill_loader = skill_loader
        self.embedder = SkillEmbedder(skill_loader)  # 新增
    
    def route(self, user_query: str) -> dict[str, Any]:
        """混合路由: Embedding 优先 + LLM 降级."""
        
        # 1. 快速路由: Embedding 相似度 (~50ms)
        skill_id, score = self.embedder.find_skill(user_query, threshold=0.78)
        
        if skill_id and score >= 0.78:
            return {
                "selected_skill": self.skill_loader.get_skill(skill_id),
                "confidence": score,
                "reason": f"Embedding match (score={score:.2f})",
                "route_method": "embedding",  # 标记路由方法
                "fallback": False,
            }
        
        # 2. 降级路由: LLM 决策 (~5-8s)
        return self._llm_route(user_query)
```

---

## 与 Tool Description 的对比

| 维度 | Tool Description | Skill Embedding |
|------|------------------|-----------------|
| 索引来源 | Tool 代码中的 docstring | Skill YAML frontmatter |
| 谁决定 | LLM 每次决策 | 本地模型预匹配 + LLM 降级 |
| 性能 | ~5-8s (LLM) | ~50ms (本地) + 5-8s (降级) |
| 可编辑性 | 需要改代码 | 改 Markdown 即可 |
| 语义理解 | LLM 强 | 本地模型中等，LLM 降级补充 |

---

## 推荐模型

### 本地 Embedding 模型 (无需 API)

| 模型 | 大小 | 中文支持 | 推理时间 |
|------|------|----------|----------|
| `paraphrase-multilingual-MiniLM-L12-v2` | 420MB | ✅ | ~50ms |
| `text2vec-base-chinese` | 400MB | ✅✅ | ~50ms |
| `bge-small-zh-v1.5` | 100MB | ✅✅✅ | ~20ms |

推荐: **`bge-small-zh-v1.5`** (轻量 + 中文优化)

---

## 总结

**最佳实践 = Skill Embedding + LLM 降级**

1. **不硬编码** - embedding 自动从 Skill 的 description/examples 生成
2. **Skill 优先** - Skill 仍是核心抽象，只是增加了索引层
3. **性能优化** - 70%+ 查询 ~50ms 路由，复杂查询 LLM 降级
4. **易于扩展** - 加新 Skill 只需写 Markdown，自动索引

是否需要我实现这个方案？
