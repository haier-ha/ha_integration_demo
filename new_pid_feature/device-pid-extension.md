# 设备 PID 扩展

本文档说明如何在本集成中按设备 PID 扩展实体行为。所有扩展实现都放在
`custom_components/haier_home/extend/` 目录中，每个扩展文件**自包含**：
目标 PID（单个或列表）+ Entity 子类 + 自注册装饰器。新增或调整某个 PID
的行为时，只需在该目录下增删文件，**永远不需要修改任何现有文件**。

> 适用范围：截至当前版本，集成实现的 HA 平台为 `climate`（空调）与 `scene`
> （场景），其中**只有 `climate` 平台接入了本文所述的 PID 扩展机制**；`scene`
> 平台的实体（`scene.py` 的 `HaierScene`）直接继承 HA 基类，不经过注册表。
> 下文示例统一以 `climate` 为例。

## 两个正交的扩展维度

扩展设备支持时，先分清两个**互相独立**的维度，别把它们混为一谈：

| 维度 | 回答的问题 | 由谁负责 | 改哪里 |
|------|-----------|---------|--------|
| **品类准入** | 这是什么*类*设备（由 appTypeCode 判定），要不要为它建 climate 实体？ | `const.py` 的 `DEVICE_TYPE_MAP` + `climate.async_setup_entry` 的品类判定 | 改常量映射 / 平台入口判定 |
| **PID → 实体类** | 已知要建 climate 实体，这个*具体型号*的行为差异怎么覆写？ | `entity.py` 的三张注册表（`@register` / `@register_platform`） | 增删 `extend/*.py` |

- `DEVICE_TYPE_MAP`：`appTypeCode`（如 `A177`）→ 内部品类码（如 `"AC"`）；未知
  `appTypeCode` 解析为 `"UNKNOWN"`。
- **准入闸门**：`device.py` 的 `create_device_from_api_record` 只放行已知品类的
  设备（`device_type` 不是 `"UNKNOWN"`），未知设备直接跳过，不会建任何实体。
- **平台判定**：`climate.async_setup_entry` 遍历已放行的设备，对品类码为 `"AC"`
  的设备建 climate 实体（`device.device_type == "AC"`）。

> ⚠️ PID 层级**不能替代**品类准入层。PID 注册表只在"已经确定要为这台设备建
> climate 实体"之后，才选择具体的实体子类；它无法回答"这台设备该不该建 climate
> 实体"。所以扩展设备时**不要**去掉 `DEVICE_TYPE_MAP` 或平台入口的品类判定。

### 扩展决策流程（先品类准入，不满足再 PID）

```
① 扩展同品类的新型号（最常见，例：新增一款空调）
   → 只在 DEVICE_TYPE_MAP 增加一行  appTypeCode -> "AC"
   → 若该型号 operationMode/windSpeed 枚举落在平台默认映射内，到此即可跑通
   → 不需要写 extend/ 文件

② 该型号与平台默认行为不一致（枚举码不同 / 要暴露额外属性）
   → 在 ① 的基础上，按下文 PID 扩展机制在 extend/ 下加覆写类
```

一句话：**先加 `DEVICE_TYPE_MAP`，只有当平台默认行为不满足该型号时，才进一步加
PID 扩展。**

## 核心思想

设备差异在 **Entity 层**处理。集成采用三级实体继承（详见 `README.md`）：

- **Level 1 `HaierDeviceEntity`**（`entity.py`）：所有设备共享逻辑——coordinator
  绑定、可用性、`get_value` / `send_command`，以及对 `valueRange` 的通用读写工具。
  它同时是**注册中心**，持有三张注册表并提供 `register` / `register_platform` /
  `create`。
- **Level 2 平台基类**（如 `climate.py` 的 `HaierClimateEntity`）：混入 HA 平台
  基类（`ClimateEntity`），提供该平台的默认实现，并用 `@register_platform("climate")`
  注册为整个平台的兜底类。
- **Level 3 PID 扩展**（`extend/*.py`）：按具体 PID 覆写差异，用
  `@HaierDeviceEntity.register(...)` 自注册。

平台入口通过 `HaierDeviceEntity.create()` 按 `(PID, 平台)` 自动选择正确的类。

## 自动发现机制

`extend/__init__.py` 的 `load_extensions()` 会遍历导入 `extend/` 下所有 `.py`
文件（`__init__.py` 除外），从而触发每个模块顶部的 `@register` 装饰器完成注册。
集成在启动时调用它一次（幂等），因此**新增扩展文件即生效**：不需要注册清单，
也不需要修改 `extend/__init__.py` 或任何平台入口。

## 注册与查找机制

`HaierDeviceEntity` 维护三张类级注册表：

| 注册表 | 键 | 写入方式 |
|--------|----|---------|
| `_specific_registry` | `(pid, platform)` | `@register("pid_x", platform)`（单个 PID，`str`） |
| `_generic_registry` | `(pid, platform)` | `@register([...], platform)`（PID 列表，`list`） |
| `_platform_registry` | `platform` | `@register_platform(platform)`（平台兜底） |

`register()` 根据第一个参数是 `str` 还是 `list` 决定写入前两张表中的哪一张。
平台入口用 `create()` 按固定优先级查表，选出最终实体类（省略类型标注与 docstring
的摘录，完整实现见 `entity.py`）：

```python
@classmethod
def create(cls, coordinator, device, description, platform):
    key = (device.pid, platform)
    entity_cls = (
        cls._specific_registry.get(key)  # 1. 单个 PID 精确匹配
        or cls._generic_registry.get(key)  # 2. PID 列表（共享组）
        or cls._platform_registry.get(platform)  # 3. 平台级默认（Level 2）
        or cls  # 4. HaierDeviceEntity 兜底
    )
    return entity_cls(coordinator, device, description)
```

**关键规则**：`_specific_registry`（单个 PID）优先于 `_generic_registry`（PID 列表），
且与 import 顺序无关。这意味着某个 PID 可以从共享组中「脱离」而无需修改共享组。

查表用的 `device.pid` 来自设备列表接口的 `pid` 字段，形如 `PID_AACPBR000`；
`@register` 里填的必须是同一形态的值。

平台侧的调用示例（见 `climate.py` 的 `async_setup_entry`）：

```python
entities.append(HaierDeviceEntity.create(coordinator, device, description=None, platform="climate"))
```

## 无需扩展的 PID

如果某个 PID 与平台级默认行为（Level 2，如 `HaierClimateEntity`）完全一致，
**无需创建任何扩展文件**。`create()` 会在前两级查表落空后，命中
`_platform_registry`，自动使用平台基类。

> 性能：三张注册表都是 `dict`，`dict.get()` 为 O(1)，即使上千 PID 也无性能影响。

## 场景一：单个 PID 特有扩展

发现某个 PID 与默认行为不一致时，新建一个文件单独处理。用 `@register("pid_x", ...)`
注册到 `_specific_registry`，只覆写与默认不同的部分：

```python
# extend/pid_x.py
from ..climate import HaierClimateEntity
from ..entity import HaierDeviceEntity


@HaierDeviceEntity.register("pid_x", "climate")
class PidXClimateEntity(HaierClimateEntity):
    """pid_x 特有扩展：模式编号与默认映射不同，只需覆写 MODE_NAME_MAP。"""

    # 注意：键必须是字符串——hvac_mode / hvac_modes 通过
    # MODE_NAME_MAP.get(str(v)) 查表。整数键将永远匹配不到，
    # 覆写会静默失效。
    MODE_NAME_MAP = {
        "0": "auto",
        "1": "cool",
        "2": "heat",
        "3": "dry",
        "6": "fan_only",
    }
```

> ⚠️ **字符串键注意**：`climate.py` 中所有对 `MODE_NAME_MAP` / `FAN_MODE_MAP`
> 的查表都使用 `map.get(str(value))`。若在扩展里写成整数键（`0: "auto"`），
> 查找 `"0"` 永远不命中，覆写形同虚设且不会报错。

## 场景二：多 PID 共享扩展

发现多个 PID 有共性后，整合为一个扩展。用 `@register([...], ...)` 传入 PID 列表，
注册到 `_generic_registry`。PID 列表定义在文件顶部作为常量，**新增 PID 只改这个
列表**：

```python
# extend/common_ab.py
from ..climate import HaierClimateEntity
from ..entity import HaierDeviceEntity

# PID 列表（新增 PID 只改这里）
PIDS_COMMON_AB = ["pid_common_a", "pid_common_b"]


@HaierDeviceEntity.register(PIDS_COMMON_AB, "climate")
class CommonABClimateEntity(HaierClimateEntity):
    """A/B 组共有的 Climate 扩展：模式映射与平台默认不同。"""

    # 键必须是字符串（同上）。
    MODE_NAME_MAP = {
        "0": "auto",
        "1": "cool",
        "2": "heat",
        "3": "dry",
        "6": "fan_only",
    }
```

## 场景三：暴露平台默认未覆盖的属性

前两个场景改的是**已有能力的映射**；第三个场景是把数字模型里平台默认没用到的
**属性**暴露到前端。做法仍是场景一 / 场景二的写法，区别只在于覆写的是能力位与
读写方法，而不是映射表。

新属性必须落在 `climate` 已有的能力位上（`preset_mode` / `swing_mode` /
`hvac_mode` 等），选哪一个由语义决定。下面以静眠为例（假设 `pid1` / `pid2` /
`pid3` 三个 PID 支持该属性）：

| name | 中文名 | 类型 | 权限 | 取值 |
|------|--------|------|------|------|
| `silentSleepStatus` | 静眠 | 布尔 | 可读 / 组可写 | `true` 开、`false` 关（默认 `false`） |

静眠对应 HA 的标准预设 `PRESET_SLEEP`，因此映射到 `preset_mode`。用标准键的额外
好处是**前端自带本地化文案与图标**，无需改 `translations/*.json` 与 `icons.json`
（自定义 `fan_mode` 键则必须补翻译）。

```python
# extend/common_silent_sleep.py
from homeassistant.components.climate import (
    PRESET_NONE,
    PRESET_SLEEP,
    ClimateEntityFeature,
)

from ..climate import HaierClimateEntity
from ..entity import HaierDeviceEntity

# PID 列表（新增 PID 只改这里）
PIDS_COMMON_SILENT_SLEEP = ["pid1", "pid2", "pid3"]

# 数字模型属性名。布尔 LIST（"true"/"false"）。
ATTR_SILENT_SLEEP = "silentSleepStatus"


@HaierDeviceEntity.register(PIDS_COMMON_SILENT_SLEEP, "climate")
class CommonSilentSleepClimateEntity(HaierClimateEntity):
    """把静眠暴露为 preset_mode，其余行为全部继承平台默认。"""

    # ClimateEntity.preset_modes 读取该属性；PRESET_NONE 是必须的「关」成员。
    _attr_preset_modes = [PRESET_NONE, PRESET_SLEEP]

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """能力位由数字模型决定：属性不可写就不暴露 PRESET_MODE。"""
        features = super().supported_features
        if self.is_writable(ATTR_SILENT_SLEEP):
            features |= ClimateEntityFeature.PRESET_MODE
        return features

    @property
    def preset_mode(self) -> str | None:
        """未上报值返回 None（HA 显示未知），而不是误报成「静眠关闭」。"""
        value = self.get_bool_value(ATTR_SILENT_SLEEP)
        if value is None:
            return None
        return PRESET_SLEEP if value else PRESET_NONE

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode not in (self.preset_modes or []):
            return
        await self.async_set_bool(ATTR_SILENT_SLEEP, preset_mode == PRESET_SLEEP)
```

这一写法里有四个可复用到其它属性的约定：

- **能力位由数字模型决定，不要硬编码**。`supported_features` 先取
  `super()`（保留 `TURN_ON` / `TURN_OFF` / 温度 / 风速），再在
  `is_writable(...)` 为真时才追加。同一 PID 组里若某台机器没有该属性或只报
  只读，就不会暴露一个按下去必然失败的控件。
- **读写走 Level 1 基类的工具**。`get_bool_value` 同时兼容 `"true"/"false"` 与
  `"1"/"0"`；`async_set_bool` 会照该属性 enum 声明的 token 风格下发，所以扩展里
  不要写死 `"true"`。
- **未上报值返回 `None`**，交给 HA 显示未知。

一个边界：`preset_mode` 是单选，一台设备只能用它承载一个这样的开关。若同一 PID
还要暴露多个布尔属性（自清洁、电辅热……），先与维护者确认承载方式，不要把多个语义
硬塞进预设列表。

落地时的顺序：确认这些 PID 的数字模型里该属性的 `writable` 与
`valueRange.dataList` 与上表一致 → 写扩展文件 → 补一个测试（注册表能按 PID 解析
到子类、属性各取值下的读、下发命令内容、属性缺失/只读时不暴露能力位）→ 重载集成，
在空调卡片上验证可读可写。

## 演进过程

扩展体系的设计目标是让「特殊 → 共性 → 再特殊」的演进都能只靠增删 `extend/`
下的文件完成：

```
阶段1: 发现 pid_a 问题
       → 新建 pid_a.py，register("pid_a", ...)                 → _specific_registry

阶段2: 发现 pid_b 也有类似问题
       → 新建 pid_b.py，register("pid_b", ...)                 → _specific_registry

阶段3: 发现 a/b 共性，合并
       → 新建 common_ab.py，register(["pid_a", "pid_b"], ...)  → _generic_registry
       → 删除 pid_a.py / pid_b.py（或去掉其 register）
       → 注意：若不删旧文件，specific 优先级高于 generic，旧扩展仍会生效

阶段4: c/d/e 整合为另一组
       → 新建 common_cde.py，register(["pid_c", "pid_d", "pid_e"], ...)

阶段5: pid_a 需要脱离 ab 组，单独处理
       → 新建 pid_a.py，register("pid_a", ...)                 → _specific_registry
       → specific 优先于 generic，无需改 common_ab.py
```

**核心保证**：`_specific_registry`（单个 PID）优先于 `_generic_registry`（PID 列表），
与 import 顺序无关。PID 可以随时从共享组中「脱离」而不必修改共享组本身。

## 可覆写的能力

Level 3 扩展是标准的 Python 子类，可以覆写 Level 2 平台基类暴露的任意属性与方法。
以 climate 为例，常见覆写点包括：

- `MODE_NAME_MAP`：原始 `operationMode` 码 → HA `HVACMode` 名（键必须为 `str`）。
- `FAN_MODE_MAP`：原始 `windSpeed` 码 → HA `fan_mode` 键（键必须为 `str`）。
- 各类 `@property`（如 `current_temperature`、`supported_features`、`preset_mode`）
  与 `async_set_*` 方法。

Level 1 `HaierDeviceEntity` 提供的通用工具可直接复用，避免在扩展里重复造轮子：

- `get_value(name)` / `send_command(**kwargs)`
- 数值范围：`get_number_value` / `get_number_min` / `get_number_max` /
  `get_number_step` / `to_command_value`
- 枚举：`get_enum_options` / `get_enum_items`
- 布尔：`get_bool_value` / `async_set_bool`
- 能力判断：`is_writable(name)` / `get_attribute(name)`

> 设计约定：像 `MODE_NAME_MAP` 这类带 HVAC 领域语义、且随 PID 变化的映射，
> 刻意放在 climate 平台/扩展类上，而不是集成级基类 `HaierDeviceEntity` 上——
> 因为其它平台并不共享这些语义。这正是 Level 3 的覆写点。

## 准入粒度与能力不匹配

本节说明当前准入机制的**粒度边界**，以及遇到不匹配型号时的**运行时行为**。理解
这一节能避免把「静默降级」误当成「已支持」。

### 准入粒度：appTypeCode 闸门放行整个品类的所有 PID

准入判定只发生在**品类层**（`create_device_from_api_record` 只看 `device_type`
是否为已知品类，`climate.async_setup_entry` 只看品类码是否为 `"AC"`），**没有任何
按 PID 的准入校验**：

```
设备记录 → appTypeCode → DEVICE_TYPE_MAP → 内部品类码
         → 已知品类则放行（该品类下的每个 PID 都会建实体）
```

因此，**在 `DEVICE_TYPE_MAP` 里加一个 `appTypeCode`，等于一次性放行该品类下的
所有 PID**。没有命中 PID 扩展的设备会落到平台默认类（`HaierClimateEntity`），
其全部能力都从**该设备自己的 digital model** 动态读取。

> 关键结论：一个 `appTypeCode` 通常对应多个 PID。批量放行后，只要某个 PID 的
> digital model 与平台默认类的假设（属性名、枚举码）不一致，就会出现下一小节
> 描述的**静默降级**——它不会阻止实体被创建，也不会报错。

### 能力不匹配时的行为：静默降级，不报错

平台默认类是**能力驱动**的：读不到的属性返回 `None`、认不出的枚举码被跳过，
全程没有断言或异常。所以一个「格式对、但字段/枚举对不上」的 PID **不会抛错、
不会崩溃**，而是按下表降级：

| 不匹配场景 | 运行时行为 | 是否有信号 |
|-----------|-----------|-----------|
| 缺 `targetTemperature` / `windSpeed`（或只读） | `supported_features` 不暴露该控件（`is_writable` 门控） | 无（控件直接消失） |
| `operationMode` 上报值不在 `MODE_NAME_MAP` | `hvac_mode` 返回 `None`，前端显示「未知」 | 无 |
| `operationMode` 枚举含未映射码 | `hvac_modes` **静默丢弃**该模式 | 无 |
| 完全缺 `operationMode` enum 属性 | `hvac_modes` 退回「把 `MODE_NAME_MAP` 全部值当可用模式」——**可能暴露设备并不支持的模式** | 无 |
| `windSpeed` 含未映射码 | 用 enum 的 `desc` 兜底，再不行给 `speed_<code>` | 无（但 UI 会显示原始文案/裸键） |
| 拿不到 `targetTemperature` 范围 | `min_temp` / `max_temp` 返回 `-1`（假值，非异常） | 无（UI 出现异常范围） |
| 用户切到设备不支持的模式/风速 | 命令解析不到原始码 → **只打 WARNING，不下发** | 有（WARNING 日志） |
| 上报值超出自身声明范围 | `get_number_value` 忽略该值 | 有（DEBUG 日志） |
| WS 单条数据畸形 | `device.async_on_message` 跳过该条 | 有（WARNING 日志） |

**能自动察觉的信号只有日志，且大多只在用户交互时才触发：**

- `Could not resolve operation mode ... for device`（切到不支持的模式时）
- `Could not resolve fan mode ... for device`（选了解析不到的风速时）
- `Ignoring out-of-range value for ...`（DEBUG，需开启）
- `Failed to update attribute from item`（WS 数据畸形）

**完全无信号的盲区**（最需要人工核对）：

- 读侧的静默丢弃：`hvac_modes` 丢模式、`fan_modes` 用 desc 兜底都不打日志。
- `hvac_modes` 的 else 分支：缺 `operationMode` enum 时凭默认假设暴露一批模式。
- 扩展里把映射表键写成**整数**（`{0: "auto"}`）：查表走 `.get(str(v))` 永不命中，
  覆写形同虚设且不报错（详见〈可覆写的能力〉的字符串键警告）。

因此，接入一个新 `appTypeCode` 后，**建议对其下每个 PID 人工核对一遍 digital
model**：`operationMode` / `windSpeed` 的枚举码是否都在 `MODE_NAME_MAP` /
`FAN_MODE_MAP` 内、关键属性（`onOffStatus` / `targetTemperature` /
`indoorTemperature`）是否齐全，而不能只看「实体创建成功、卡片能打开」就判定已支持。

## 新增扩展的检查清单

1. 在 `extend/` 下新建一个文件，文件名语义化并与注册方式对应：单 PID 用
   `pid_<pid>.py`（写入 `_specific_registry`），PID 列表用 `common_<共性>.py`
   （写入 `_generic_registry`）——共性可以是分组代号（`common_ab.py`）也可以是
   具体能力（`common_silent_sleep.py`）。类名与文件名保持一致
   （`CommonSilentSleepClimateEntity`）。
2. 从 `..entity` 导入 `HaierDeviceEntity`，从对应平台模块（如 `..climate`）导入
   Level 2 基类。
3. 用 `@HaierDeviceEntity.register("pid", "platform")`（单个）或
   `@HaierDeviceEntity.register([...], "platform")`（多个）装饰你的子类；PID 列表
   提到文件顶部作为常量。
4. 只覆写与默认不同的部分；映射表的键务必是 `str`。
5. 若暴露的是平台默认未覆盖的属性：先核对数字模型里的 `writable` 与
   `valueRange`，用 `is_writable()` 做能力门控，读写走 Level 1 工具，未上报值返回
   `None`。
6. **无需**修改 `extend/__init__.py` 或任何平台入口——自动发现会处理其余部分。
