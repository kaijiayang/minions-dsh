# minions-dsh

**云端大模型负责编排，本地小模型负责执行——云端 API 费用大幅下降。**

`minions-dsh` 是一个 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 插件（以及其背后的 Python 协议库），构建于斯坦福 [HazyResearch](https://hazyresearch.stanford.edu/) 的 [Minions](https://arxiv.org/abs/2502.15964) 分层多模型协作协议之上。

它要解决的问题是：**长上下文 / 大批量的推理任务在云端非常昂贵。** 与其把每一份文档都发给前沿大模型，`minions-dsh` 让**云端大模型（Supervisor）**负责任务拆分与最终综合，而**本地部署的小模型（Worker）**通过 **LM Studio、Ollama、vLLM、llama.cpp** 等平台提供的 **OpenAI 兼容 API**，在您自己的硬件上阅读长上下文并执行子任务。

```
         ┌────────────────────────────────────────────────────┐
         │              DeepSeek Harness (Agent)               │
         │                                                      │
         │   Agent ──调用──► minions_run 工具（TS 插件）          │
         │                              │  拉起子进程             │
         └──────────────────────────────┼───────────────────────┘
                                        ▼
                          Python 桥接脚本 (minions_bridge.py)
                                        │
         ┌──────────────────────────────┴───────────────────────┐
         ▼                                                      ▼
   云端 Supervisor                                      本地 Worker
   (DeepSeek / OpenAI / ...)                     (LM Studio / Ollama / vLLM
   负责拆分任务与综合答案                          在本地阅读长上下文、执行子任务
   → 只有压缩后的子任务结果                        按 token 计费为 0
     会离开您的机器)
```

- **论文**：[Minions: Cost-efficient Collaboration Between On-device and Cloud Language Models](https://arxiv.org/pdf/2502.15964)
- **上游项目**：[HazyResearch/minions](https://github.com/HazyResearch/minions)（MIT）
- **许可证**：MIT（本项目与上游库均为 MIT）

---

## 目录

- [特性](#特性)
- [工作原理](#工作原理)
- [快速开始](#快速开始)
- [DeepSeek Harness 插件](#deepseek-harness-插件)
- [本地平台支持](#本地平台支持)
- [配置文件](#配置文件)
- [命令行](#命令行)
- [项目结构](#项目结构)
- [文档](#文档)
- [开发](#开发)
- [安全](#安全)
- [许可证](#许可证)

## 特性

- 🧠 **分层多模型协作** — Minions 协议：云端 Supervisor 将任务拆分为子任务，本地 Worker 基于长上下文执行子任务，Supervisor 多轮迭代直至综合出最终答案。
- 💸 **显著降本** — 长上下文始终不离开本地，只有压缩后的子任务结果上云，常见场景下云端 token 消耗可降低约 90%。
- 🖥️ **一个客户端适配所有本地服务器** — 统一的 OpenAI 兼容客户端 `OpenAICompatClient`，内置 **LM Studio / Ollama / vLLM / llama.cpp** 等平台预设。
- 📄 **规范配置文件** — 统一的 `minions.yaml`（附 JSON Schema），支持 `${ENV_VAR}` 展开与 `api_key_env` 密钥间接引用，杜绝硬编码密钥。
- 🔌 **DeepSeek Harness 插件** — 注册 `minions_run` 工具，任何 Harness Agent 都可以在运行时把长上下文任务委托给本地/云端模型对。
- 🧪 **可测试的桥接契约** — 严格的 stdin JSON 入 / stdout JSON 出，提供离线自检、单元测试与 Node 冒烟测试。

## 工作原理

协议按轮次运行：

1. **Supervisor（云端）** 把主任务拆分为 N 个子任务（`JobManifest`）。
2. **Worker（本地）** 阅读上下文分块并执行每个子任务，返回结构化结果 `{explanation, citation, answer}`（兼容被 markdown 代码围栏包裹的 JSON）。
3. **Supervisor（云端）** 评估结果：信息不足则继续下发子任务（进入下一轮，上限 `max_rounds`），否则综合生成**最终答案**。

两个角色均可替换。默认配置：

| 角色 | 默认 | 常见选择 |
|------|------|----------|
| Supervisor（远程） | `deepseek-chat` | DeepSeek、OpenAI、Anthropic |
| Worker（本地） | LM Studio 上的 `qwen3.8-27b` | 任意 GGUF / vLLM 托管的模型 |

## 快速开始

### 1. 安装

需要 **Python 3.10+**（Harness 插件另需 **Node.js 18+**）。

```bash
git clone https://github.com/kaijiayang/minions-dsh.git
cd minions-dsh
pip install -e .          # 安装 minions 协议库与桥接依赖
```

### 2. 启动本地模型服务

任选其一（它们都提供 OpenAI 兼容 API，本项目原生支持）：

- **LM Studio** — 加载模型（如 `qwen3.8-27b`），打开 *Local Server* 标签页，点击 **Start Server** → `http://127.0.0.1:1234/v1`。
- **Ollama** — `ollama serve`（OpenAI 兼容端点 `http://127.0.0.1:11434/v1`）。
- **vLLM** — `vllm serve Qwen/Qwen3-8B --api-key EMPTY` → `http://127.0.0.1:8000/v1`。
- **llama.cpp** — `llama-server -m <model>.gguf` → `http://127.0.0.1:8080/v1`。

详见 [docs/LOCAL_MODEL_SERVERS.md](docs/LOCAL_MODEL_SERVERS.md)。

### 3. 配置

```bash
cp examples/configs/minions.lmstudio.yaml minions.yaml   # 或直接用仓库根的 minions.yaml
export DEEPSEEK_API_KEY=sk-...                            # 云端 API Key 放入环境变量
```

### 4. 运行

**通过 Python 桥接（无需 Harness）：**

```bash
echo '{"call_params":{"task":"总结关键结论","context":["长文档内容..."],"doc_metadata":"研究报告"}}' \
  | python dsh-plugin/python/minions_bridge.py --config minions.yaml
```

**作为 Python 库：**

```python
from minions.clients.openai_compat import OpenAICompatClient
from minions.clients.openai import OpenAIClient
from minions.minions import Minions

local = OpenAICompatClient(model_name="qwen3.8-27b", platform="lmstudio")
remote = OpenAIClient(model_name="deepseek-chat", api_key="sk-...",
                      base_url="https://api.deepseek.com", local=False)

minions = Minions(local_client=local, remote_client=remote, max_rounds=3)
result = minions(task="总结关键结论", doc_metadata="研究报告",
                 context=["长文档内容..."])
print(result["final_answer"])
```

**先校验配置：**

```bash
python dsh-plugin/python/minions_bridge.py --validate-config minions.yaml
```

## DeepSeek Harness 插件

`dsh-plugin/` 目录是一个可安装的 Harness **工具插件**，注册 `minions_run` 工具：

```bash
cd dsh-plugin
npm install
npm run build
# 在仓库根目录：
dsh web --patch ./dsh-plugin/cordis.yml     # 然后打开 http://127.0.0.1:3080
```

启动前请编辑 `dsh-plugin/cordis.yml`：

- 将插件 `name` 替换为 `dsh-plugin/lib/index.js` 的**绝对路径**（Windows 上使用 `file:///` 形式）；
- 推荐设置 `configFile` 为 `minions.yaml` 的绝对路径，插件将完全从该文件读取配置；
- 切勿提交 API Key：在 shell 中导出即可（桥接子进程会继承环境变量）。

详见 [docs/DSH_PLUGIN.md](docs/DSH_PLUGIN.md)。

### `minions_run` 工具参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task` | string | ✅ | 给云端 Supervisor 的主任务 |
| `context` | string[] | ✅ | 长上下文 / 文档分块 |
| `doc_metadata` | string | — | 上下文类型提示（如 "Medical Report"） |
| `max_rounds` | integer | — | 最大协作轮数（默认 3） |
| `protocol` | `minions` \| `minion` | — | 并行分解 vs 单轮对话 |
| `local_model` | string | — | 本地模型 id |
| `local_platform` | enum | — | `lmstudio` \| `ollama` \| `vllm` \| `llamacpp` \| `generic` \| `auto` |
| `local_base_url` | string | — | 覆盖本地 OpenAI 兼容端点 |
| `remote_model` | string | — | 云端模型 id |
| `remote_client_type` | enum | — | `deepseek` \| `openai` \| `anthropic` \| `openai_compat` |

## 本地平台支持

所有本地平台都通过**同一套 OpenAI 兼容 API** 访问，无需厂商 SDK：

| 平台 | 默认端点 | API Key | 备注 |
|------|----------|---------|------|
| **LM Studio** | `http://127.0.0.1:1234/v1` | 任意占位 | 图形界面，"Local Server" 标签页 |
| **Ollama** | `http://127.0.0.1:11434/v1` | `ollama` | 原生或 OpenAI 兼容 |
| **vLLM** | `http://127.0.0.1:8000/v1` | `EMPTY` | 生产级、高吞吐 |
| **llama.cpp** | `http://127.0.0.1:8080/v1` | 任意占位 | `llama-server` |
| **generic** | 必填 | 任意 | 任意 OpenAI 兼容服务器 |

在 `minions.yaml` 中设置 `local.platform`，或在工具调用中传入 `local_platform`。显式 `base_url` 永远优先于平台默认值。

## 配置文件

仓库根目录的 `minions.yaml` 是唯一权威配置（Schema：`config.schema.json`）：

```yaml
version: 1

remote:                        # 云端 Supervisor
  provider: deepseek           # deepseek | openai | anthropic | openai_compat
  model: deepseek-chat
  base_url: https://api.deepseek.com/v1
  api_key_env: DEEPSEEK_API_KEY   # 从该环境变量读取密钥

local:                         # 本地 Worker（OpenAI 兼容）
  platform: lmstudio           # lmstudio | ollama | vllm | llamacpp | generic | auto
  model: qwen3.8-27b
  base_url: http://127.0.0.1:1234/v1
  api_key: lm-studio           # 大多数本地服务器接受任意占位

protocol:
  type: minions                # minions | minion
  max_rounds: 3
  log_dir: minion_logs

plugin:                        # DeepSeek Harness 插件选项（可选）
  bridge_python: python
  timeout_ms: 300000
```

规则：

- **密钥** — 使用 `api_key_env: <VAR>` 或 `${VAR}` 插值，切勿提交真实密钥；
- **查找顺序** — `MINIONS_CONFIG` 环境变量 → 当前目录 `minions.yaml` → 仓库根 `minions.yaml`；
- **校验** — `python dsh-plugin/python/minions_bridge.py --validate-config minions.yaml`。

完整参考：[docs/CONFIGURATION.md](docs/CONFIGURATION.md)。

## 命令行

```bash
# 离线自检
python dsh-plugin/python/minions_bridge.py --self-test

# 校验配置并打印解析后的桥接负载
python dsh-plugin/python/minions_bridge.py --validate-config minions.yaml

# 使用配置文件执行一次任务（call params 从 stdin 读取）
echo '{"call_params":{"task":"...","context":["..."]}}' \
  | python dsh-plugin/python/minions_bridge.py --config minions.yaml

# 完整 JSON 负载（向后兼容）
echo '{"local_client":{...},"remote_client":{...},"protocol":{...},"call_params":{...}}' \
  | python dsh-plugin/python/minions_bridge.py
```

## 项目结构

```
minions-dsh/
├── minions/                     # Python 协议库
│   ├── minions.py               #   Minions 协议（Supervisor ↔ Worker 多轮）
│   ├── minion.py                #   Minion 单轮对话协议
│   ├── config.py                #   ★ 规范配置文件加载/校验
│   └── clients/
│       ├── openai_compat.py     #   ★ 统一的 OpenAI 兼容本地客户端
│       ├── openai.py            #   OpenAI/DeepSeek 云端客户端
│       ├── ollama.py            #   Ollama 原生客户端
│       └── ...                  #   其他上游客户端
├── dsh-plugin/                  # DeepSeek Harness 插件
│   ├── src/                     #   TypeScript：index.ts / bridge.ts / minions-tool.ts
│   ├── python/minions_bridge.py #   ★ JSON-over-stdio 桥接脚本
│   └── cordis.yml               #   Harness 本地覆盖层（模板）
├── minions.yaml                 # ★ 权威配置文件
├── config.schema.json           # ★ minions.yaml 的 JSON Schema
├── examples/configs/            #   现成配置（LM Studio / Ollama / vLLM）
├── docs/                        #   架构 / 配置 / 本地服务 / 插件 / 开发 / 排障
├── tests/                       #   Python 单元测试
└── pyproject.toml               #   打包配置（setuptools）
```

## 文档

| 文档 | 内容 |
|------|------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统设计、数据流、插件 ↔ 桥接契约 |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | `minions.yaml` 完整参考、环境变量、JSON Schema |
| [docs/LOCAL_MODEL_SERVERS.md](docs/LOCAL_MODEL_SERVERS.md) | LM Studio / Ollama / vLLM / llama.cpp 部署指南 |
| [docs/DSH_PLUGIN.md](docs/DSH_PLUGIN.md) | Harness 插件安装与配置 |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 构建、测试、参与贡献 |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | 常见错误与解决办法 |

## 开发

```bash
pip install -e ".[dev]"

# Python 测试
python -m pytest tests/

# 桥接自检
python dsh-plugin/python/minions_bridge.py --self-test

# TypeScript 插件
cd dsh-plugin && npm install && npm run build && npm run smoke
```

## 安全

- 切勿提交 API Key — 使用 `api_key_env` / `${VAR}` 与环境变量；
- 长上下文默认不出本地，只有子任务摘要会上云；
- 漏洞请私信报告 — 见 [SECURITY.md](SECURITY.md)。

## 许可证

[MIT](LICENSE) — 本项目与上游 [HazyResearch/minions](https://github.com/HazyResearch/minions) 库均为 MIT 许可。完整文本与署名见 [LICENSE](LICENSE)。
