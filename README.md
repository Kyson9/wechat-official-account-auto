# WeChat Official Account Auto — Open Source Safe Pack

这是从私有项目中抽出的脱敏开源版。核心入口是给 Agent 使用的 `SKILL.md`，并保留了它引用的主要脚本；真实账号、密钥和运行数据已全部移除或模板化。

## 包含内容

- `SKILL.md`：给 Agent 读取的主说明书，定义完整工作流和脚本调用顺序
- `scripts/`：`SKILL.md` 中引用的主要脚本，已做脱敏保留
- `scripts/markdown_to_wechat_html.py`：把 Markdown 转成适合公众号排版的 HTML
- `scripts/prepare_article_images.py`：解析 Markdown 中的本地图片并注入到 HTML
- `scripts/svg_to_jpeg.py`：把 SVG 资源转成 JPEG
- `scripts/preview_fallback.py`：生成本地手机视图预览 HTML
- `scripts/lib/common.py`：最小公共库
- `config.yml`：脱敏后的示例配置

## 明确不包含

- 真实公众号 `AppID`、`AppSecret`、预览微信号
- 草稿箱、新增草稿、更新草稿、发布、轮询等直连微信接口脚本
- 数据库、日志、缓存、临时文件、历史草稿、生成产物
- 项目中的私有运行文档与业务数据

## 适用场景

- 本地把 Markdown 转成公众号风格 HTML
- 在 Markdown 中引用本地图片并注入到 HTML
- 生成本地预览文件进行排版检查
- 作为你自己内容工作流的基础模块继续扩展

## 快速开始

### 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. 准备目录

```bash
mkdir -p data/tmp
```

### 3. 把 Markdown 转成 HTML

```bash
echo '{"markdown":"# 标题\n\n正文"}' | python3 scripts/markdown_to_wechat_html.py
```

### 4. 注入本地图片

```bash
echo '{
  "draft_markdown":"# 标题\n\n![](assets/example.jpg)",
  "wechat_html":"<h1>标题</h1>",
  "content_dir":"./examples"
}' | python3 scripts/prepare_article_images.py
```

### 5. 生成本地预览

```bash
echo '{"wechat_html":"<h1>标题</h1><p>正文</p>","title":"示例文章"}' | python3 scripts/preview_fallback.py
```

## 配置说明

当前 `config.yml` 只保留开源版需要的最小配置：

- `database.path`：本地 SQLite 路径
- `paths.temp_dir`：临时文件目录
- `logging.level`：日志级别
- `logging.log_file`：日志文件，留空则只输出终端

## 开源裁剪原则

这个目录是从原项目中人工筛出的安全子集，裁剪原则如下：

- 只保留与排版和本地预览直接相关的通用脚本
- 删除全部密钥、账号信息和运行数据
- 删除所有直连微信发布链路的能力
- 删除项目特定的历史产物与内部文档
- 移除本地绝对路径依赖，改为通用命令解析

## 后续建议

如果你要正式开源到 GitHub，建议继续补上：

- LICENSE
- 更完整的示例输入输出
- CI 检查
- 英文版 README
- 将脚本重构为可安装 CLI 包
