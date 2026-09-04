# maijia-business-analyses-smedc

这是面向麦家经营周报和月报的 Enterprise Hub 结构化数据 reporting skill 脚手架。

本仓库是原 [`maijia-business-analyse`](https://github.com/YinXiaoyu-1998/maijia-business-analyse) skill 的 Enterprise Hub 派生版本。原 skill 以本地美团 POS 导出文件为输入；本派生版本改为通过已登录的 Enterprise Hub MCP 工具读取权限范围内的结构化数据。本脚手架采用 MIT 许可，见 [LICENSE](LICENSE)。

在支持结构化覆盖查询的 Enterprise Hub MCP launcher 发布并完成独立校验前，不应发布本仓库，也不应把它作为公开 reporting skill 安装使用。

## 范围

计划支持：

- 基于 Enterprise Hub 结构化数据生成麦家周报和月报；
- 使用 `business`、`dishes`、`dish_catalog` 三个 dataset 支撑经营诊断模块；
- 在可选数据缺失时生成诚实的 partial report；
- 本地校验已保存的 MCP 响应 envelope，并生成确定性的事实表和报告产物。

明确不包含：

- 美团浏览器导出或下载流程；
- 直接 HTTP、token、密码、数据库或服务配置读取；
- 以本地 CSV/XLSX 作为报表源数据的兼容路径；
- 月利润或利润率流程；
- 真实客户数据、凭据或未发布 launcher 版本 pin。

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
