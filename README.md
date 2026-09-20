# ha_integration_demo

HA 集成扩展的 demo 集合。本仓库是对 **`ha_haier_home`** 仓库「按设备 PID 扩展实体
行为」机制的补充说明，配一份可直接照抄的可运行样例。目标是：开发者读完即可快速上手
扩展一个新 PID。

## 这个仓库有什么

```
new_pid_feature/
├── device-pid-extension.md                                  # ① 扩展原理与规范（必读）
├── custom_components/haier_home/extend/
│   └── common_silent_sleep.py                               # ② 一个真实扩展 demo（静眠模式）
└── tests/
    └── test_extend_common_silent_sleep.py                   # ③ 对应的单元测试
```

| # | 文件 | 作用 |
|---|------|------|
| ① | `device-pid-extension.md` | **扩展说明文档**。扩展任何设备前先读它，讲清了品类准入 vs. PID→实体类两个维度、三级实体继承、注册/自动发现机制、字符串键等坑点。 |
| ② | `common_silent_sleep.py` | 严格遵循 ① 的原则开发的**实战 demo**：把「静眠」(`silentSleepStatus`) 暴露为 climate 的 `preset_mode`，作用于 PID `PID_AACPBE000` / `PID_AB96AE000` / `PID_AB9611001`。对应文档〈场景三：暴露平台默认未覆盖的属性〉。 |
| ③ | `test_extend_common_silent_sleep.py` | ② 的测试：验证注册表能按 PID 解析到子类、各取值下的读、下发命令内容、属性缺失/只读时不暴露能力位。 |

## 核心思想（一句话版）

设备差异全部在 **Entity 层**处理，扩展文件**自包含**（目标 PID + Entity 子类 +
`@register` 自注册装饰器），放进 `extend/` 目录即被自动发现并生效——**永远不需要
修改任何现有文件**。完整原理见 [`device-pid-extension.md`](new_pid_feature/device-pid-extension.md)。

## 如何扩展一个新 PID（4 步）

1. **先判断要不要写扩展**：只是新增同品类型号，且其 `operationMode`/`windSpeed`
   枚举落在平台默认映射内 → 只在 `const.py` 的 `DEVICE_TYPE_MAP` 加一行即可，**不用
   写 `extend/` 文件**。只有当平台默认行为不满足该型号（枚举码不同 / 要暴露额外属性）
   时，才继续下面的步骤。
2. **在 `extend/` 下新建文件**，文件名语义化：单 PID 用 `pid_<pid>.py`（写入
   `_specific_registry`），多 PID 共享用 `common_<共性>.py`（写入 `_generic_registry`）。
3. **写一个 Level 2 平台基类（如 `HaierClimateEntity`）的子类**，用
   `@HaierDeviceEntity.register("pid", "climate")` 或 `@HaierDeviceEntity.register([...], "climate")`
   自注册，只覆写与默认不同的部分。参照 `common_silent_sleep.py` 照抄即可。
4. **补一个测试**，参照 `test_extend_common_silent_sleep.py`。

> 约定与坑点（详见文档）：映射表的键**必须是 `str`**（`{0: "auto"}` 会静默失效）；
> 能力位用 `is_writable()` 门控、不要硬编码；读写走 Level 1 基类工具
> （`get_bool_value` / `async_set_bool` 等）；未上报值返回 `None`。

## 如何让 demo 在 `ha_haier_home` 中生效

demo 目录结构与目标仓库一一对应，直接拷贝到位即可（自动发现机制会处理注册，
无需改 `extend/__init__.py` 或任何平台入口）：

```bash
# 1. 扩展实现 → 目标仓库的 extend/ 目录
cp new_pid_feature/custom_components/haier_home/extend/common_silent_sleep.py \
   <ha_haier_home>/custom_components/haier_home/extend/

# 2. 测试 → 目标仓库的 tests/ 目录
cp new_pid_feature/tests/test_extend_common_silent_sleep.py \
   <ha_haier_home>/tests/
```

拷贝后重载集成，在空调卡片上确认静眠开关可读可写；运行 `pytest tests/test_extend_common_silent_sleep.py` 验证。

> ⚠️ 测试文件放在**仓库根的 `tests/` 包**下，而非 `extend/` 下——它 `import`
> 了 `tests.mock_data`，也不参与 `extend/` 的自动发现（`load_extensions()` 只导入
> 真正的扩展模块）。放进 `extend/` 会破坏导入并污染自动发现。

## 落地前的自检

- 确认这几个 PID 的 digital model 里 `silentSleepStatus` 的 `writable` 与
  `valueRange.dataList`（`"true"`/`"false"`）与 demo 假设一致。已核对 `ha_haier_home/dumps`
  下的数字模型：`PID_AACPBE000`（A177 星悦挂机）、`PID_AB96AE000` / `PID_AB9611001`
  （A178 立式）**全部**带该属性，取值域一致。
- **注意 `writable` 是动态的**：dump 显示 `operationMode == "6"`（送风）时
  `silentSleepStatus.writable` 变为 `false`，切回其他模式恢复 `true`。demo 用
  `is_writable()` 门控 `PRESET_MODE`，因此能力位会随模式切换出现/消失。若不希望
  `supported_features` 抖动（前端卡片会闪），可改为恒定暴露能力位、在
  `async_set_preset_mode` 中对不可写状态抛 `HomeAssistantError`。
- 新增/调整 PID 时，只改扩展文件顶部的 `PIDS_COMMON_SILENT_SLEEP` 列表。
- 接入新 `appTypeCode` 后，逐个核对其下每个 PID 的枚举码与关键属性，避免文档所述
  的「静默降级」被误当成「已支持」。
