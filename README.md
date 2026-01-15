# YNU选课助手 Pro

> Forked from [starwingChen/YNU-xk_spider](https://github.com/starwingChen/YNU-xk_spider)

云南大学选课辅助工具，支持课程监控、自动抢课、智能换课、微信推送等功能。

## ✨ 功能特性

- 🔐 **纯 API 模式** - 无需浏览器，轻量高效
- 🤖 **自动 OCR 识别** - 验证码自动识别，全程无需手动操作
- 📚 **课程浏览** - 支持多板块、搜索、筛选
- 🎯 **多课程并发监控** - 每门课程独立线程，互不阻塞
- 🔄 **智能换课** - 自动检测时间冲突，退旧选新一气呵成
- 🎲 **盲抢机制** - 查询失败时自动尝试盲抢
- 📱 **微信推送** - 余课提醒 + 抢课成功通知（Server酱）
- 🔁 **Session 自动恢复** - 登录过期自动重登，监控不中断
- 🎨 **现代化ui界面** - Catppuccin Mocha 暗色主题

## 🚀 快速开始

### 下载安装

从 [Releases](https://github.com/YHalo-wyh/YNU-xk_spider/releases) 下载最新版本：
- `YNU选课助手Pro_Setup.exe` - 安装版（推荐）

### 使用说明

1. **登录**
   - 输入学号和密码
   - 点击「🚀 一键登录」按钮
   - 登录过程全自动，验证码错误自动重试

2. **选课监控**
   - 登录成功后，选择课程类型浏览课程
   - 使用搜索框快速定位目标课程
   - 点击课程卡片上的「🎯 加入待抢」按钮
   - 可添加多门课程到待抢列表

3. **开始抢课**
   - 确认待抢列表中的课程
   - 设置并发数（建议 3-10）
   - 点击「▶ 开始监控」按钮
   - 程序会自动轮询监控，发现余量立即抢课
   - 抢课成功会弹窗提示并自动从列表移除

## 📱 微信推送配置（Server酱）

使用 [Server酱](https://sct.ftqq.com/) 实现微信推送：

1. 访问 https://sct.ftqq.com/
2. 微信扫码登录，获取 SendKey
3. 在程序左侧勾选「📱 微信通知 (Server酱)」
4. 填入 SendKey

推送内容：
- **发现余量** - 监控到课程有空位时推送
- **抢课成功** - 成功选上课程时推送（包括正常抢课、盲抢、换课）

## 💻 开发者

如需从源码运行：

```bash
# 克隆仓库
git clone https://github.com/YHalo-wyh/YNU-xk_spider.git
cd YNU-xk_spider

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 运行程序
python run_gui.py
```

### 打包

```bash
python build.py
```

需要安装 [NSIS](https://nsis.sourceforge.io/) 用于生成安装包。

## ⚠️ 免责声明

1. 本工具仅供学习交流使用，请勿用于商业用途
2. 使用本工具产生的一切后果由用户自行承担
3. 本工具不保证抢课成功率，选课结果以学校系统为准
4. 请遵守学校相关规定，合理使用本工具
5. 作者不对因使用本工具导致的任何问题负责

**使用本工具即表示您已阅读并同意以上声明**

## 📝 更新日志

### v1.2.0 (2026.01.16)
- ✨全新纯检 API 架构，无需浏览器
- 🎨 Catppuccin Mocha 暗色主题
- ⚡ 多课程并发监控（独立线程）
- 🔄 智能换课功能（自动退旧选新）
- 🎲 盲抢机制
- 🔁 Session 过期自动重登
- 📋 帮助菜单与关于对话框

### v1.0.0-beta (2026.01.12)
- ✨ 初始版本
- 🔐 全自动登录（验证码自动识别）
- 🎯 多课程同时监控
- 📱 微信推送功能

## 👨‍💻 作者

- **当前维护**: [YHalo-wyh](https://github.com/YHalo-wyh)
- **原项目**: [starwingChen/YNU-xk_spider](https://github.com/starwingChen/YNU-xk_spider)

## 📄 License

[MIT License](LICENSE) © 2026 YHalo-wyh
