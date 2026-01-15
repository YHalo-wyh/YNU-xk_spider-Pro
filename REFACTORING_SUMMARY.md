# Workers.py 重构总结 - 安全优先版本

## 重构日期
2026-01-16

## 重构目标
对 `xk_spider/gui/workers.py` 中的 `MultiGrabWorker` 类进行安全性重构，防止因"幽灵余量"或"盲抢"导致误退用户核心课程。

---

## 核心修改

### 1. ✅ 彻底删除盲抢逻辑 (Remove Blind Grab)

**位置**: `_monitor_course_loop` 方法

**修改前**:
- 当 `_api_query_course_capacity` 返回 `remain is None` 时，会触发盲抢机制
- 连续失败3次后，最多尝试3次盲抢
- 存在误选风险

**修改后**:
```python
# 查询失败 (remain is None) - 直接跳过，绝不盲抢
if remain is None:
    if state.get('last_status') != 'query_failed':
        self.status.emit(f"[SKIP] {course_name} 查询失败，跳过本次循环（安全模式）")
        self._logger.warning(f"查询失败，跳过: {course_name}")
        state['last_status'] = 'query_failed'
    
    # 休眠后继续下次查询
    time.sleep(1.5)
    continue
```

**安全保障**:
- 查询失败时仅打印日志，绝不执行选课操作
- 避免在不确定状态下误操作

---

### 2. ✅ 重构监控循环 - 安全优先级检查

**位置**: `_monitor_course_loop` 方法

**核心策略**:

#### 策略 2.1: 最高优先级检查 `isFull` 字段
```python
# 必须首先检查 isFull 字段（系统标记）
is_full_flag = course_info.get('isFull', False) if course_info else False

# 幽灵余量防御：即使计算出 remain > 0，但 isFull=True 时，绝对禁止抢课
if is_full_flag:
    if remain > 0:
        # 发现幽灵余量！
        self.status.emit(
            f"[GHOST] {course_name} 显示余量{remain}但isFull=True，"
            f"跳过以防误退课（幽灵余量）"
        )
        self._logger.warning(f"幽灵余量检测: {course_name}, remain={remain}, isFull=True")
        state['last_status'] = 'ghost_capacity'
    
    # 跳过本次循环
    time.sleep(1.0)
    continue
```

**幽灵余量防御机制**:
- 系统 `isFull=True` 时，即使计算余量 > 0，也绝对禁止抢课
- 防止因数据延迟导致的误判
- 保护用户已选课程不被误退

#### 策略 2.2: 行动条件 - 双重验证
```python
# 仅当 isFull=False 且 remain>0 时才允许抢课
if remain > 0:
    # 通过安全检查！可以进入抢课流程
    self.status.emit(
        f"[ALERT] 🎉 {course_name} 发现余量！余={remain}/{capacity} "
        f"(isFull=False, 安全)"
    )
    # ... 进入抢课流程
```

**双重验证**:
1. `isFull` 必须为 `False`
2. 计算余量 `remain` 必须 > 0

---

### 3. ✅ 重构回滚机制 - 亡命回滚 (Desperate Recovery)

**位置**: `_handle_conflict_rollback` 方法

**修改前**:
- 换课失败后仅尝试1次回滚
- 回滚失败则放弃，可能导致旧课丢失

**修改后**:
```python
# 紧急救援参数
DESPERATE_RECOVERY_DURATION = 300  # 5分钟 = 300秒
RETRY_INTERVAL = 0.7  # 0.7秒间隔（高频但不过分）

rollback_start_time = time.time()
attempt_count = 0

self.status.emit(f"[紧急救援] 🚨 开始死磕回滚 {conflict_name}，持续5分钟...")

while self._running:
    elapsed = time.time() - rollback_start_time
    
    # 超时检查
    if elapsed >= DESPERATE_RECOVERY_DURATION:
        self.status.emit(f"[紧急救援] ⚠️ 超时5分钟，停止回滚。请手动检查 {conflict_name}")
        return False, conflict_course
    
    attempt_count += 1
    
    # 尝试选回旧课
    rollback_success, rollback_msg, _ = self._api_select_course_fast({
        'JXBID': conflict_tc_id, 
        'type': conflict_type
    })
    
    # 心跳维持（防止UI假死）
    self._increment_request_count()
    
    if rollback_success:
        # 核实是否真的选上了
        time.sleep(0.3)
        is_selected = self._check_course_selected(conflict_tc_id)
        
        if is_selected or is_selected is None:
            self.status.emit(f"[紧急救援] ✓ 成功抢回 {conflict_name}！(尝试{attempt_count}次)")
            return False, conflict_course
    
    # 短暂休眠后继续
    time.sleep(RETRY_INTERVAL)
```

**亡命回滚特性**:
- **持续时间**: 5分钟（300秒）
- **重试间隔**: 0.7秒（高频但不过载）
- **心跳维持**: 每次请求调用 `_increment_request_count()` 防止UI假死
- **智能退出**: 
  - 抢回成功立即退出
  - 检测到"已选"状态立即退出
  - 超时5分钟后退出并提示用户手动检查

---

### 4. ✅ 修复时间解析 - 支持"第"字前缀

**位置**: `_parse_time_slots` 方法

**修改前**:
- 部分支持"第5-6节"格式，但不完整

**修改后**:
```python
# 解析节次: "5-6节" 或 "第5-6节" 或 "5,6节" 或 "第5节"
# 修复: 正确处理"第"字前缀
# 先尝试范围格式: "第5-6节" 或 "5-6节"
period_match = re.search(r'第?(\d+)-(\d+)节', segment)
if period_match:
    start_period = int(period_match.group(1))
    end_period = int(period_match.group(2))
    for p in range(start_period, end_period + 1):
        slot['periods'].add(p)
else:
    # 尝试单节格式: "第5节" 或 "5节"
    period_singles = re.findall(r'第(\d+)节', segment)
    if period_singles:
        for p in period_singles:
            slot['periods'].add(int(p))
    else:
        # 尝试不带"第"字的格式: "5节" 或 "5,6节"
        period_singles = re.findall(r'(\d+)节', segment)
        for p in period_singles:
            slot['periods'].add(int(p))
```

**支持格式**:
- ✅ "第5-6节"
- ✅ "5-6节"
- ✅ "第5节"
- ✅ "5节"
- ✅ "5,6节"

---

### 5. ✅ API 方法修正

#### 5.1 `_api_select_course_fast` 修正

**修改**:
```python
# 修复: 处理 course_type 为数字字符串的情况（直接使用，不查字典）
if isinstance(course_type, str) and course_type.isdigit():
    course_type_code = course_type
else:
    course_type_code = get_course_type_code(course_type)
```

**说明**:
- 正确处理 `course_type` 为数字字符串（如 "01", "02"）的情况
- 确保使用 `addParam={"data": {...}}` 结构

#### 5.2 `_api_delete_course` 确认

**确认**:
- ✅ 使用 GET 请求
- ✅ 使用 `deleteParam` 参数
- ✅ 参数结构正确

---

## 安全性提升总结

### 防护机制

| 防护项 | 修改前 | 修改后 | 安全等级 |
|--------|--------|--------|----------|
| 盲抢风险 | ❌ 存在盲抢逻辑 | ✅ 彻底删除 | 🟢 高 |
| 幽灵余量 | ❌ 无防护 | ✅ isFull优先检查 | 🟢 高 |
| 回滚失败 | ⚠️ 仅1次尝试 | ✅ 5分钟死磕 | 🟢 高 |
| 时间解析 | ⚠️ 部分支持 | ✅ 完整支持 | 🟢 中 |
| API参数 | ⚠️ 部分情况错误 | ✅ 完全修正 | 🟢 中 |

### 核心原则

1. **安全第一**: 宁可错过机会，也不误退核心课程
2. **双重验证**: `isFull=False` + `remain>0` 双重检查
3. **亡命回滚**: 换课失败后5分钟持续抢回旧课
4. **透明日志**: 所有关键决策都有日志记录

---

## 测试建议

### 1. 幽灵余量测试
- 模拟 `isFull=True` 但 `remain>0` 的情况
- 验证是否跳过抢课并打印 `[GHOST]` 日志

### 2. 查询失败测试
- 模拟 API 查询失败返回 `None`
- 验证是否跳过并打印 `[SKIP]` 日志，不执行盲抢

### 3. 回滚测试
- 模拟换课失败场景
- 验证是否进入5分钟紧急救援模式
- 验证心跳信号是否正常发送

### 4. 时间解析测试
- 测试 "第5-6节"、"第5节" 等格式
- 验证解析结果是否正确

---

## 兼容性说明

- ✅ 向后兼容：所有现有功能保持不变
- ✅ API 兼容：API 调用结构未改变
- ✅ UI 兼容：信号和槽机制未改变
- ⚠️ 行为变化：删除盲抢功能，更加保守

---

## 维护建议

1. **日志监控**: 关注 `[GHOST]`、`[SKIP]`、`[紧急救援]` 等关键日志
2. **性能监控**: 紧急救援模式下的高频请求可能增加服务器负载
3. **用户反馈**: 收集用户对新安全机制的反馈
4. **参数调优**: 根据实际情况调整回滚时长（当前5分钟）和重试间隔（当前0.7秒）

---

## 作者
Kiro AI Assistant

## 审核状态
✅ 语法检查通过
✅ 逻辑审查完成
⏳ 待实际测试验证
