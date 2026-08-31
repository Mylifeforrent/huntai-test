# 组件清单模板

组件清单是设计和代码之间的契约。组件状态、Token 和代码 API 应使用同一组名称，参考 [组件规范](../04-design-system/components.md)。

## 空白模板

| 组件 | 用途 | 变体/尺寸 | 状态 | 数据契约 | 键盘行为 | 响应式 | 内容限制 | 无障碍 | 实现归属 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |  |

## 已填示例

| 组件 | 用途 | 变体/尺寸 | 状态 | 数据契约 | 键盘行为 | 响应式 | 内容限制 | 无障碍 | 实现归属 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `OrderTable` | 比较和选择订单 | dense/default | loading/ready/empty/error | `Order[]`, selectedIds | 表头排序、行聚焦、空格选择 | 手机转摘要列表 | 客户名可换行，金额右对齐 | 表头、选中数、状态文本 | 前端基础组件 |
| `FilterBar` | 缩小结果范围 | inline/drawer | dirty/loading/error | query、status、dateRange | Tab 进入，Enter 提交，Esc 关闭 | 手机转筛选抽屉 | 标签可换行 | label 与错误关联 | 页面模式 |
| `ApprovalDialog` | 确认危险动作 | approve/reject | idle/submitting/success/error | ids、reason、result | 打开聚焦首控件，关闭回触发点 | 手机底部抽屉 | 明确数量和影响 | `role=dialog`、焦点管理 | 业务组件 |
| `StatusBadge` | 表达订单状态 | status | default/disabled | status enum | 非交互，不抢焦点 | 尺寸不变 | 文本不只靠颜色 | 状态文本 | 设计系统 |

实现前先检查是否已有 [页面模式](../04-design-system/patterns.md)，避免为同一行为新增同义组件。
