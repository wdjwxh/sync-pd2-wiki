# Wiki Sync Tool

一个用于同步和跟踪 MediaWiki 网站变更的 Python 工具。该工具可以自动获取 wiki 页面的最新更改，生成易于阅读的 diff 文件，并保存页面的完整内容以供离线查阅。

## 功能特点

- 🔄 自动同步 MediaWiki 网站的最新更改
- 📝 生成带语法高亮的 HTML diff 文件，清晰展示变更内容
- 💾 保存页面完整内容供离线查阅
- ⏰ 支持增量同步，只获取上次同步后的新变更
- 🔍 支持按时间点或特定页面进行同步
- 📁 自动组织输出文件到时间戳目录

## 安装

1. 确保你已经安装了 Python 3.6+
2. 克隆此仓库：
   ```bash
   git clone <repository-url>
   cd wiki-sync-tool
   ```
3. 安装依赖：
   ```bash
   pip install requests python-dotenv
   ```

## 配置

创建一个 `.env` 文件并配置你的 MediaWiki API 地址：

```env
WIKI_API_URL=https://your-wiki-site.com/api.php
```

或者复制提供的示例配置文件：

```bash
cp .env.example .env
```

然后编辑 `.env` 文件中的 `WIKI_API_URL` 值。

## 使用方法

### 基本全量同步

同步自上次运行以来的所有更改：

```bash
python sync.py --run
```

首次运行时，会同步过去 24 小时内的更改。

### 指定时间起点同步

从指定时间开始同步：

```bash
python sync.py --since 2025-11-28T00:00:00Z --run
```

### 同步特定页面

只同步特定页面的最新更改：

```bash
python sync.py --title "Main Page" --run
```

### 同步特定页面并更新时间戳

同步特定页面并在完成后更新全局时间戳：

```bash
python sync.py --title "Main Page" --update-timestamp --run
```

### 查看帮助

```bash
python sync.py --help
```

## 输出文件

每次运行都会在 `wiki_sync_output` 目录下创建一个以时间戳命名的子目录，包含生成的文件：

- `页面标题-时间戳-revid.diff.html` - 页面变更的 HTML diff 文件
- `页面标题-时间戳-revid.full.txt` - 页面的完整内容

### Diff 文件示例

Diff 文件展示了页面的变更内容，具有以下特性：

- 绿色背景表示新增内容
- 红色背景表示删除内容
- 左侧彩色竖线标识变更类型
- +/- 标记清晰显示变更位置
- 删除内容带有删除线效果

![Diff 示例截图](example-diff.png)

## 技术细节

### Diff 标记说明

工具会对 MediaWiki 的原生 diff 输出进行处理：

- 将 `<ins>` 和 `<del>` 标签转换为标准的 `<span>` 标签
- 将 `data-marker` 属性转换为实际的 +/- 符号
- 应用自定义 CSS 样式增强视觉效果

### 目录组织

```
wiki_sync_output/
├── 20251203_152702/
│   ├── Main_Page-20251203_152645-12345.diff.html
│   ├── Main_Page-20251203_152645-12345.full.txt
│   ├── Another_Page-20251203_152650-12346.diff.html
│   └── Another_Page-20251203_152650-12346.full.txt
└── 20251203_153127/
    └── ...
```

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request。