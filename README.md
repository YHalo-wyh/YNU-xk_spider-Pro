# YNU选课助手 Pro

> Forked from [starwingChen/YNU-xk_spider](https://github.com/starwingChen/YNU-xk_spider)

云南大学选课辅助工具，支持课程监控、自动抢课、智能换课、微信推送等功能。

## 功能特性

- **纯 API 模式** - 无需浏览器，轻量高效
- **验证码自动识别** - 全程无需手动操作
- **课程浏览** - 多板块、搜索、筛选
- **多课程并发监控** - 独立线程，互不阻塞
- **智能换课** - 检测时间冲突，退旧选新
- **安全优先** - 幽灵余量防御、亡命回滚，保护已选课程
- **微信推送** - 余量提醒 + 抢课成功通知（Server酱）
- **Session 自动恢复** - 登录过期自动重登

## 快速开始

### 下载

从 [Releases](https://github.com/YHalo-wyh/YNU-xk_spider-Pro/releases) 下载最新版本。

### 使用

1. 输入学号密码，点击登录
2. 选择课程类型，浏览或搜索课程
3. 点击「加入待抢」添加到监控列表
4. 点击「开始监控」，程序自动检测余量并抢课

## 微信推送（Server酱）

1. 访问 https://sct.ftqq.com/ 获取 SendKey
2. 在程序中勾选「微信通知」并填入 SendKey

## 从源码运行

```bash
git clone https://github.com/YHalo-wyh/YNU-xk_spider-Pro.git
cd YNU-xk_spider-Pro
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run_gui.py
```

## 免责声明

本工具仅供学习交流，使用产生的后果由用户自行承担。请遵守学校规定，合理使用。

## 更新日志

### v1.5.0 (2026.01.17)
- 新增：增强版健康检查系统，4层检测机制
- 新增：智能自动恢复，检测到卡死后自动诊断和修复
- 新增：实时监控状态报告和预警
- 新增：体育课程显示项目名称
- 修复：3小时卡死问题（Socket句柄泄漏 + GIL死锁）
- 修复：登录后闪退问题
- 修复：长时间运行后刷新课程列表卡死
- 修复：心跳机制异常处理
- 修复：登录状态检测超时处理
- 优化：使用 Session 上下文管理器，确保连接正确释放
- 优化：移除 terminate() 暴力终止线程
- 优化：心跳信号发送频率
- 优化：日志框性能，超过 500 行自动清理
- 优化：课程获取失败处理

### v1.3.0 (2026.01.16)
- 新增：每次查询显示课程余量状态
- 新增：定期检测登录状态（每60秒）
- 优化：日志输出更清晰

### v1.2.0 (2026.01.16)
- 纯 API 架构重构
- 多课程并发监控
- 智能换课功能
- 安全优先：删除盲抢、幽灵余量防御、亡命回滚
- Server酱微信通知
- Session 过期自动重登

### v1.0.0-beta (2026.01.12)
- 初始版本

## 作者

- 当前维护: [YHalo-wyh](https://github.com/YHalo-wyh)
- 原项目: [starwingChen/YNU-xk_spider](https://github.com/starwingChen/YNU-xk_spider)

## 特别致谢

感谢 [starwingChen](https://github.com/starwingChen) 的原项目提供了基础框架和灵感。

## License

[MIT License](LICENSE)

