# 质量日报自动归档工具 📋

每天处理3张质量日报报表图片，自动识别标题、提取日期、分类归档。

## 功能

- **双引擎**：默认 MinerU（高精度），自动回退 Qwen3-VL（快速）
- **自动识别**标题格式如 `2026年05月16日一期中控质量报表`
- **自动分类**归档到对应目录（一期中控 / MHP中控 / 1.5期黑粉线钻控）
- **低成本**：MinerU每天1000页免费额度，Qwen回退仅¥1/年

## 快速开始

### 1. 配置密钥

复制 `.env.template` 为 `.env`，填写你的 API 密钥：

```env
MINERU_TOKEN=你的MinerU_Token
SILICONFLOW_API_KEY=你的SiliconFlow_API_Key
```

### 2. 安装依赖

```bash
pip install pillow requests
```

### 3. 运行

```bash
# 处理3张图片
python quality_report_archiver.py 图片1.png 图片2.png 图片3.png

# 或处理目录下所有图片
python quality_report_archiver.py --dir D:\质量日报\

# 切换为Qwen引擎（更快）
python quality_report_archiver.py --mode qwen 图片1.png 图片2.png
```

### Windows 一键运行

直接拖拽图片到 `质量日报归档.bat` 上即可。

## 目录结构

```
质量日报归档/
├── 一期中控质量报表/
│   └── 2026-05-16_一期中控.png
├── MHP中控质量报表/
│   └── 2026-05-25_MHP中控.png
└── 1.5期黑粉线钻控质量报表/
    └── 2026-05-25_1.5期黑粉线钻控.png
```

## 引擎对比

| 特性 | MinerU（默认） | Qwen3-VL-8B |
|------|---------------|-------------|
| 标题识别 | ✅ 准确 | ✅ 准确 |
| 表格数据提取 | ✅ 完整（含合并单元格） | ❌ 幻觉 |
| 速度 | ~10秒/张 | ~2秒/张 |
| 费用 | 1000页/天免费 | ¥1/年 |
