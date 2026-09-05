# maijia-business-analyses-smedc

这是面向麦家经营诊断、周报和月报的 Enterprise Hub 结构化数据 reporting skill。

本仓库是受原 [`maijia-business-analyse`](https://github.com/YinXiaoyu-1998/maijia-business-analyse) skill 启发的 Enterprise Hub-backed 派生设计。当前未检测到 upstream source 暴露 license metadata，因此本仓库不声明继承 upstream license。后续实现将在本仓库内独立完成，并采用本仓库自己的 MIT 许可，见 [LICENSE](LICENSE)。

本 skill 使用 `enterprise-hub-mcp-launcher@0.2.6`，并通过用户已认证的 Enterprise Hub MCP tools 获取结构化 dataset registry、coverage 和 query 结果。

## 范围

支持范围：

- 基于 Enterprise Hub 结构化数据生成经营诊断、周会报表和月会报表；
- 使用 `business`、`dishes`、`dish_catalog` 三个 canonical dataset；
- 在可选数据缺失或 coverage 不完整时生成诚实的 partial report；
- 本地校验已保存的 MCP response envelope，并生成确定性的 HTML report artifact。

明确不包含：

- 美团浏览器导出或下载流程；
- 直接 HTTP、token、密码、数据库或服务配置读取；
- 以本地 CSV/XLSX 作为报表源数据的兼容路径；
- 月利润或利润率流程；
- 真实客户数据、凭据或未发布 launcher 版本 pin。

## Agent Workflow

1. 安装或更新 `enterprise-hub-mcp-launcher@0.2.6`，并通过官方 launcher 支持的流程完成登录。
2. 将 `list_structured_datasets` envelope 保存为 `registry_response.json`。
3. 对 `business`、`dishes`、`dish_catalog` 依次调用 `describe_structured_dataset_coverage`，保存为 `coverage_business.json`、`coverage_dishes.json`、`coverage_dish_catalog.json`。
4. 使用 `python3 scripts/build_query_plan.py` 生成 `diagnosis`、`weekly` 或 `monthly` 的 query manifest。
5. 对 manifest 中每个 job 调用 `query_structured_dataset`。如果返回 `nextCursor` 非空，继续分页调用直到 `nextCursor` 为 `null`；多页结果按请求顺序保存为数组，路径使用 `jobs[].outputFile`，通常位于 `query-results/`。
6. 运行 `python3 scripts/assemble_query_bundle.py`，再运行对应 renderer runner：
   - diagnosis：`python3 scripts/run_business_report.py`
   - weekly：`python3 scripts/run_weekly_report.py`
   - monthly：`python3 scripts/run_monthly_report.py`
7. 保留 registry、coverage、manifest、raw query responses、bundle、facts 和 HTML report 作为 provenance；只清理不影响审计的 scratch 文件。

coverage 缺口或可选 job 失败应生成带 notice 的 partial report，不应补造事实或归因为服务故障。

## 当前合同文件

- `config/maijia.json` 定义 schema version `1`、canonical datasets、麦家门店分组、语义字段映射、报表模块和查询限制。
- `tests/fixtures/registry_response.json` 是合成的 `list_structured_datasets` 响应 envelope。
- `tests/fixtures/coverage_business.json`、`tests/fixtures/coverage_dishes.json`、`tests/fixtures/coverage_dish_catalog.json` 是合成的 `describe_structured_dataset_coverage` 响应 envelope。

所有 fixture 中的公司、文档、导入批次和门店名称均为合成数据，只供后续 query-plan 与 bundle-validation 测试使用，不代表生产数据。

## 数据访问边界

使用本 skill 的 agent 应通过用户已认证的 Enterprise Hub MCP launcher 会话调用：

- `list_structured_datasets`
- `describe_structured_dataset_coverage`
- `query_structured_dataset`

本仓库脚本只负责校验保存下来的 MCP envelope，并在本地生成事实表和报告产物。脚本不得自行认证、启动 launcher、直连 Enterprise Hub HTTP API，或读取服务内部数据。

## Development

运行时报表脚本只使用 Python standard library。测试套件仅为了校验 `agents/openai.yaml` 使用 PyYAML；安装 dev dependencies：

```bash
python3 -m pip install -r requirements-dev.txt
```

运行仓库检查：

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_query_plan.py --help
python3 scripts/assemble_query_bundle.py --help
python3 scripts/run_business_report.py --help
python3 scripts/run_weekly_report.py --help
python3 scripts/run_monthly_report.py --help
```
