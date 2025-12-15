# 📍 OLAV 文件导航地图 (File Navigation Map)

## 🎯 按用途快速找到文件 (Find Files by Purpose)

### 🚀 我想初始化OLAV系统 (I want to initialize OLAV)

**如果你是第一次使用:**
1. 📖 先读: `QUICKSTART.md` (新手指南)
2. 📋 再查: `QUICK_REFERENCE.md` (快速参考)
3. 🔧 然后运行: `setup.ps1` (Windows) 或 `setup.sh` (Linux/macOS)

**如果你的系统已损坏:**
1. 🧹 先清理: `cleanup_and_reset.ps1` (Windows) 或 `cleanup_and_reset.sh` (Linux)
2. 📋 再读: `CLEANUP_AND_RESET_PLAN.md` (详细步骤)
3. 🔧 然后重新初始化: `setup.ps1` 或 `setup.sh`

---

### 🔍 我需要故障排除 (I need to troubleshoot)

**容器问题?**
- 📄 查看: `CLEANUP_AND_RESET_PLAN.md` → "故障排除指南" 部分

**命令不工作?**
- 📄 查看: `QUICK_REFERENCE.md` → "常见问题速解" 部分

**想了解系统是如何工作的?**
- 📄 查看: `DEPLOYMENT_SUMMARY.md` → "4个代码修复" 部分
- 📄 查看: `.github/copilot-instructions.md` → 完整架构说明

**需要快速命令参考?**
- 📄 查看: `QUICK_REFERENCE.md` → "核心命令速查表" 部分

---

### 📚 我想学习OLAV架构 (I want to learn OLAV architecture)

**基础概念:**
1. 📖 `.github/copilot-instructions.md` - 完整架构文档
2. 📄 `docs/ARCHITECTURE_EVALUATION.md` - 架构评估
3. 📄 `docs/API_USAGE.md` - API参考

**设计模式:**
- 📄 `.github/copilot-instructions.md` → "关键模式" 部分
- 📄 `docs/ARCHITECTURE_EVALUATION.md` → 模式分析

**最佳实践:**
- 📄 `.github/copilot-instructions.md` → "常见坑" 部分
- 📄 `.github/copilot-instructions.md` → "Python最佳实践" 部分

---

### 🔧 我想修改代码 (I want to modify code)

**代码在哪里:**
- `src/olav/` - 所有源代码
- `scripts/` - 工具和脚本
- `config/` - 配置文件

**最近的修复:**
1. `scripts/setup-wizard.sh` - Auto CSV detection
2. `scripts/setup-wizard.ps1` - Remove broken --csv
3. `src/olav/cli/commands.py` - --csv parameter
4. `src/olav/etl/init_all.py` - Device import integration

**修改指南:**
- 📄 `.github/copilot-instructions.md` → "代码质量标准" 部分
- 📄 `.github/copilot-instructions.md` → "依赖注入" 部分

---

### 📊 我想看项目进度 (I want to see project progress)

**完成报告:**
- 📄 `PROJECT_COMPLETION_REPORT.md` - 最全面的完成报告

**部署总结:**
- 📄 `DEPLOYMENT_SUMMARY.md` - 4个修复的详细说明

**变更日志:**
- 📄 `CHANGELOG.md` - 历史版本变更

---

## 📂 完整文件树 (Complete File Tree)

```
Olav/
│
├── 🚀 初始化相关 (Initialization)
│   ├── setup.ps1                    ← Windows快速启动
│   ├── setup.sh                     ← Linux快速启动
│   └── scripts/
│       ├── setup-wizard.ps1         ← 原始PowerShell脚本
│       └── setup-wizard.sh          ← 原始Bash脚本
│
├── 🧹 清理相关 (Cleanup)
│   ├── cleanup_and_reset.ps1        ← Windows清理脚本
│   ├── cleanup_and_reset.sh         ← Linux清理脚本
│   └── CLEANUP_AND_RESET_PLAN.md    ← 清理详细步骤
│
├── 📋 文档相关 (Documentation)
│   ├── README.md                    ← 主文档（保留）
│   ├── QUICKSTART.md                ← 快速开始
│   ├── QUICK_REFERENCE.md           ← 快速参考卡片 ⭐
│   ├── DEPLOYMENT_SUMMARY.md        ← 部署总结 ⭐
│   ├── PROJECT_COMPLETION_REPORT.md ← 完成报告 ⭐
│   └── docs/                        ← 其他文档
│       ├── ARCHITECTURE_EVALUATION.md
│       ├── API_USAGE.md
│       ├── 6份分析文档...
│       └── (34个markdown文件)
│
├── 🔧 源代码 (Source Code) 
│   └── src/olav/
│       ├── cli/commands.py          ← 修复3: --csv参数
│       ├── etl/init_all.py          ← 修复4: 设备导入
│       └── ...其他代码
│
├── ⚙️ 配置相关 (Configuration)
│   ├── config/
│   │   ├── inventory.csv            ← 测试设备CSV
│   │   ├── inventory.example.csv    ← CSV示例
│   │   ├── olav.yaml                ← OLAV配置
│   │   └── ...其他配置
│   ├── docker-compose.yml           ← Docker容器配置
│   ├── Dockerfile                   ← Docker镜像
│   ├── pyproject.toml               ← Python依赖
│   └── .github/copilot-instructions.md ← 架构和最佳实践
│
├── 📊 数据相关 (Data)
│   └── data/
│       ├── suzieq-parquet/          ← SuzieQ数据 (清理时删除)
│       ├── cache/                   ← 缓存 (清理时删除)
│       └── ...其他数据
│
└── 🧪 测试相关 (Testing)
    └── tests/
        ├── unit/
        └── e2e/
```

---

## 🎓 推荐阅读顺序 (Recommended Reading Order)

### 对于新手 (For Beginners)
```
1. README.md                          (2分钟)
2. QUICKSTART.md                      (10分钟)
3. QUICK_REFERENCE.md                 (5分钟)
4. 运行 setup.ps1 或 setup.sh         (15分钟)
```

### 对于开发者 (For Developers)
```
1. .github/copilot-instructions.md   (20分钟)
2. DEPLOYMENT_SUMMARY.md              (10分钟)
3. docs/API_USAGE.md                  (15分钟)
4. 查看源代码 src/olav/               (30分钟)
```

### 对于运维工程师 (For DevOps)
```
1. QUICK_REFERENCE.md                 (5分钟)
2. CLEANUP_AND_RESET_PLAN.md          (15分钟)
3. PROJECT_COMPLETION_REPORT.md       (10分钟)
4. docker-compose.yml                 (10分钟)
```

### 对于系统管理员 (For System Admins)
```
1. PROJECT_COMPLETION_REPORT.md       (10分钟)
2. DEPLOYMENT_SUMMARY.md              (15分钟)
3. CLEANUP_AND_RESET_PLAN.md          (20分钟)
4. 运行 cleanup_and_reset.ps1/sh      (30分钟)
5. 运行 setup.ps1 或 setup.sh         (20分钟)
```

---

## 🔑 关键文件索引 (Key Files Index)

| 文件 | 大小 | 优先级 | 用途 |
|------|------|--------|------|
| setup.ps1 | 40 KB | 🔴 高 | Windows初始化 |
| setup.sh | 26 KB | 🔴 高 | Linux初始化 |
| QUICK_REFERENCE.md | 7 KB | 🔴 高 | 快速参考 |
| CLEANUP_AND_RESET_PLAN.md | 9 KB | 🟡 中 | 清理指南 |
| DEPLOYMENT_SUMMARY.md | 11 KB | 🟡 中 | 修复说明 |
| PROJECT_COMPLETION_REPORT.md | 11 KB | 🟡 中 | 完成报告 |
| .github/copilot-instructions.md | 30 KB | 🟡 中 | 架构指南 |
| config/inventory.csv | 2 KB | 🔴 高 | 测试数据 |
| docker-compose.yml | 5 KB | 🔴 高 | 容器配置 |

---

## 🆘 快速救援 (Emergency Rescue)

### "我的系统崩溃了！" (My system is broken!)
```
1. 📄 打开: QUICK_REFERENCE.md
2. 🔍 找: "紧急求助" 部分
3. ⚡ 运行: docker system prune -a --volumes
4. 🚀 执行: .\cleanup_and_reset.ps1
5. ▶️ 运行: .\setup.ps1
```

### "我不知道该做什么！" (I don't know what to do!)
```
1. 📄 打开: QUICK_REFERENCE.md
2. 📋 查看: "5分钟快速部署" 部分
3. ▶️ 按步骤操作: 总共5个步骤
```

### "有错误信息但不知道怎么办！" (I have an error message!)
```
1. 📄 打开: CLEANUP_AND_RESET_PLAN.md
2. 🔍 找: "故障排除" 部分
3. 📖 找你的错误，按解决方案操作
```

---

## 📞 文件使用场景映射 (File Use Case Mapping)

### 场景1: 第一次安装OLAV
- [ ] 读: `QUICKSTART.md`
- [ ] 读: `QUICK_REFERENCE.md` 
- [ ] 运行: `setup.ps1` 或 `setup.sh`
- [ ] 验证: `docker ps`

### 场景2: 清理现有系统
- [ ] 读: `CLEANUP_AND_RESET_PLAN.md`
- [ ] 运行: `cleanup_and_reset.ps1` 或 `.sh`
- [ ] 验证: `docker ps` (应该没有容器)

### 场景3: 修改代码
- [ ] 读: `.github/copilot-instructions.md`
- [ ] 修改: `src/olav/` 中的代码
- [ ] 验证: `uv run pytest`
- [ ] 参考: `DEPLOYMENT_SUMMARY.md` 中的修复示例

### 场景4: 学习系统架构
- [ ] 读: `.github/copilot-instructions.md`
- [ ] 读: `DEPLOYMENT_SUMMARY.md`
- [ ] 读: `docs/ARCHITECTURE_EVALUATION.md`
- [ ] 查看: `docs/API_USAGE.md`

### 场景5: 故障排除
- [ ] 打开: `QUICK_REFERENCE.md`
- [ ] 查找: 你的错误类型
- [ ] 按解决方案操作
- [ ] 如果不行，看: `CLEANUP_AND_RESET_PLAN.md`

---

## 🌟 高价值文件 (High-Value Files)

### ⭐⭐⭐ 必读 (Must Read)
1. **QUICK_REFERENCE.md** - 5分钟掌握所有常用命令
2. **setup.ps1 / setup.sh** - 实际的初始化脚本
3. **CLEANUP_AND_RESET_PLAN.md** - 完整的清理和修复指南

### ⭐⭐ 强烈推荐 (Highly Recommended)
1. **.github/copilot-instructions.md** - 系统设计和最佳实践
2. **DEPLOYMENT_SUMMARY.md** - 所有修复的详细说明
3. **PROJECT_COMPLETION_REPORT.md** - 项目进度和成果

### ⭐ 参考 (For Reference)
1. **config/inventory.csv** - 测试数据格式
2. **docker-compose.yml** - 容器配置
3. **src/olav/cli/commands.py** - CLI实现

---

## 💡 导航小贴士 (Navigation Tips)

1. **使用Ctrl+F搜索** - 所有文档都支持快速搜索
2. **查看文件的目录** - 大文档开头都有目录
3. **看表格快速浏览** - 表格能快速了解概况
4. **按优先级阅读** - 先读标有🔴的文件

---

## 📊 文档完整性清单 (Documentation Completeness)

- [x] 快速开始指南 ✅ `QUICKSTART.md`
- [x] 快速参考卡片 ✅ `QUICK_REFERENCE.md`
- [x] 初始化脚本 ✅ `setup.ps1` + `setup.sh`
- [x] 清理脚本 ✅ `cleanup_and_reset.ps1` + `.sh`
- [x] 清理详细步骤 ✅ `CLEANUP_AND_RESET_PLAN.md`
- [x] 部署总结 ✅ `DEPLOYMENT_SUMMARY.md`
- [x] 完成报告 ✅ `PROJECT_COMPLETION_REPORT.md`
- [x] 架构指南 ✅ `.github/copilot-instructions.md`
- [x] API文档 ✅ `docs/API_USAGE.md`
- [x] 分析文档 ✅ `docs/` (6份)

---

**🎯 现在你已经知道要找什么文件了！选择上面的场景，开始阅读吧。**

**⚡ 最快路径**: `QUICK_REFERENCE.md` → `setup.ps1/sh` → `docker ps`（15分钟）

