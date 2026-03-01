# RAG爬虫模块使用说明

## 功能概述

本模块实现了自动爬取智能合约漏洞数据的功能，支持从多个数据源获取漏洞案例，并自动标准化、验证和入库。

## 支持的数据源

1. **GitHub** - 搜索GitHub上的智能合约漏洞相关仓库
2. **NVD CVE** - 从NVD数据库获取CVE漏洞信息
3. **DeFiHackLabs** - 从DeFiHackLabs仓库获取真实攻击案例
4. **Ethernaut** - 从OpenZeppelin的Ethernaut平台获取学习案例
5. **Rekt News** - 从Rekt News获取DeFi黑客攻击新闻
6. **审计报告** - 从Code4rena等平台获取安全审计报告

## 使用方法

### 1. 立即爬取数据

```bash
# 使用默认参数爬取
python -m rag_engine.crawler fetch

# 自定义爬取数量
python -m rag_engine.crawler fetch --max-github 30 --max-cve 20 --max-defihack 20

# 使用GitHub Token（提高API限制）
python -m rag_engine.crawler fetch --token YOUR_GITHUB_TOKEN

# 爬取后不重建索引
python -m rag_engine.crawler fetch --no-index
```

### 2. 验证数据格式

```bash
# 验证所有数据文件
python -m rag_engine.crawler.validator

# 验证单个文件
python -m rag_engine.crawler.validator --file 001_etherstore_reentrancy.json

# 验证并自动修复
python -m rag_engine.crawler.validator --fix
```

### 3. 查看爬虫状态

```bash
python -m rag_engine.crawler status
```

### 4. 启动定时调度

```bash
# 每天凌晨2点自动爬取
python -m rag_engine.crawler schedule

# 自定义时间（每天10:30）
python -m rag_engine.crawler schedule --hour 10 --minute 30

# 立即执行一次
python -m rag_engine.crawler schedule --now
```

### 5. 运行完整测试

```bash
python -m rag_engine.crawler.test_crawler
```

## 数据格式

所有爬取的数据都会被标准化为以下格式：

```json
{
  "id": "唯一标识符",
  "slug": "URL友好的标识",
  "vuln_type": "漏洞类型（如SWC-107-Reentrancy）",
  "protocol_name": "协议名称",
  "attack_date": "攻击日期（YYYY-MM-DD）",
  "tags": ["标签1", "标签2"],
  "attack_primitives": ["攻击原语1"],
  "aliases": ["别名1"],
  "description": "漏洞描述",
  "poc_template": "PoC代码模板"
}
```

### 必需字段

- `id`: 唯一标识符
- `vuln_type`: 漏洞类型
- `protocol_name`: 协议名称
- `attack_date`: 攻击日期
- `description`: 漏洞描述
- `poc_template`: PoC代码模板

### 可选字段

- `slug`: URL友好的标识
- `tags`: 标签列表
- `attack_primitives`: 攻击原语列表
- `aliases`: 别名列表

## 数据验证

数据验证器会检查：

1. **必需字段存在性** - 确保所有必需字段都存在
2. **字段类型正确性** - 确保字段类型符合要求
3. **数据格式正确性** - 确保日期格式、字符串格式等正确
4. **与indexer兼容性** - 确保数据可以被indexer正确加载和索引

## 增量管理和去重机制

爬虫实现了完善的增量更新和去重机制：

### 去重策略

1. **文件级去重**：通过检查数据目录中已存在的JSON文件，避免重复保存
2. **ID级去重**：记录每个数据源已爬取的ID列表，避免重复处理相同数据
3. **状态记录**：维护每个数据源的爬取状态，包括已爬取的ID列表

### 工作流程

1. **首次爬取**：
   - 从API获取数据（如GitHub搜索、CVE查询等）
   - 提取每条记录的ID
   - 检查ID是否已存在（文件或已爬取列表）
   - 只保存新数据，并记录ID到已爬取列表

2. **后续爬取**：
   - 加载已爬取的ID列表
   - 从API获取数据时，跳过已爬取的ID
   - 只处理新数据，避免重复请求和保存

### 示例

假设今天爬取了GitHub的1-30号数据：
- 这些数据的ID会被记录到`crawler_state.json`中
- 明天再次执行时：
  - 会先加载已爬取的ID列表
  - 从API获取数据时，如果遇到1-30号的ID，会直接跳过
  - 只处理31号及以后的新数据
  - **不会重新请求1-30号的数据**

### 状态文件

爬取状态保存在 `rag_engine/crawler_state.json`，包含：
- 每个数据源的上次爬取时间
- 已爬取的ID列表（最近1000个）
- 爬取统计信息

### 注意事项

- 已爬取ID列表限制为最近1000个，避免文件过大
- 如果删除了数据文件，需要手动清理状态文件中的ID记录
- 状态文件损坏时，会重新开始爬取（但文件级去重仍然有效）

## 注意事项

1. **API限制**: 
   - GitHub API有速率限制，建议使用Token
   - NVD API可能需要API Key
   - 某些数据源可能使用备用数据

2. **网络连接**: 
   - 确保网络连接正常
   - 某些API可能需要代理

3. **数据质量**:
   - 爬取的数据会自动标准化
   - 建议定期运行验证器检查数据质量
   - 可以使用`--fix`参数自动修复常见问题

4. **索引重建**:
   - 爬取新数据后建议重建索引
   - 运行: `python -m rag_engine.build_index`

## 故障排除

### 问题：爬取失败

1. 检查网络连接
2. 检查API Token是否有效
3. 查看错误日志
4. 某些数据源可能暂时不可用，会使用备用数据

### 问题：数据格式错误

1. 运行验证器检查: `python -m rag_engine.crawler.validator`
2. 使用自动修复: `python -m rag_engine.crawler.validator --fix`
3. 手动检查并修复JSON文件

### 问题：索引构建失败

1. 确保所有数据文件格式正确
2. 检查数据目录路径
3. 查看详细错误信息

## 开发扩展

### 添加新的数据源

1. 在`fetchers.py`中创建新的Fetcher类，继承`BaseFetcher`
2. 实现`fetch()`方法
3. 在`cli.py`中添加爬取逻辑
4. 更新`__init__.py`导出新类

### 自定义数据标准化

在`normalizer.py`中修改`DataNormalizer`类，添加自定义标准化逻辑。

## 示例

### 完整工作流程

```bash
# 1. 爬取数据
python -m rag_engine.crawler fetch --max-github 10 --max-cve 5

# 2. 验证数据
python -m rag_engine.crawler.validator

# 3. 重建索引
python -m rag_engine.build_index

# 4. 查看状态
python -m rag_engine.crawler status
```

## 去重机制详解

### 问题：会不会重复爬取相同数据？

**答案：不会！** 爬虫实现了多层去重机制：

1. **文件级去重**：检查数据目录，已存在的文件不会重复保存
2. **ID级去重**：记录已爬取的ID，下次执行时直接跳过
3. **状态持久化**：爬取状态保存在`crawler_state.json`中

### 工作示例

假设今天执行：
```bash
python -m rag_engine.crawler fetch --max-github 30
```

- 爬取了GitHub的30条数据（ID: github_1 到 github_30）
- 这些ID被记录到状态文件中

明天再次执行相同命令：
```bash
python -m rag_engine.crawler fetch --max-github 30
```

- 系统会先加载已爬取的ID列表（github_1 到 github_30）
- 从API获取数据时，如果遇到这些ID，会直接跳过
- **不会重新请求这30条数据的API**
- 只会处理新的数据（如github_31, github_32等）

### 验证去重机制

运行测试脚本验证：
```bash
python -m rag_engine.crawler.test_deduplication
```

这个脚本会：
1. 执行第一次爬取
2. 执行第二次相同参数的爬取
3. 验证第二次是否跳过了已爬取的数据

### 注意事项

- **API请求层面**：某些数据源（如GitHub搜索）在获取数据前无法知道具体ID，所以API请求仍会发出，但处理时会跳过已爬取的记录
- **ID列表限制**：已爬取ID列表限制为最近1000个，避免状态文件过大
- **手动清理**：如果删除了数据文件，状态文件中的ID记录不会自动清理，但文件级去重仍然有效

## 相关文件

- `fetchers.py` - 数据源获取器
- `normalizer.py` - 数据标准化器
- `validator.py` - 数据验证器
- `cli.py` - 命令行接口
- `incremental_manager.py` - 增量管理器（包含去重逻辑）
- `scheduler.py` - 定时调度器
- `test_deduplication.py` - 去重机制测试脚本

