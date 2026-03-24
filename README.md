# WeChat Official Account Auto — Open Source Safe Pack

这是从私有项目中抽出的脱敏开源版。核心入口是给 Agent 使用的 `SKILL.md`，并保留了它引用的主要脚本；真实账号、密钥和运行数据已全部移除或模板化。

## 包含内容

- `SKILL.md`：给 Agent 读取的主说明书，定义完整工作流和脚本调用顺序
- `scripts/`：`SKILL.md` 中引用的主要脚本，已做脱敏保留
- `config.yml`：脱敏后的示例配置
