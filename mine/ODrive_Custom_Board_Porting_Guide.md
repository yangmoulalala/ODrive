# STM32F405 + DRV8301 自定义 ODrive 板移植与调试记录

## 1. 硬件概况

- MCU：STM32F405RGT6，LQFP-64
- 栅极驱动：DRV8301，HTSSOP-56
- 功率 MOSFET：CSD18540Q5B
- 电机：单轴关节电机
- 减速比：未知，不写入固件；需通过电机侧与负载侧编码器计数差实测
- 电机侧编码器：AS5047P-ATSM U6，PA2/GPIO3，负责 FOC 换相
- 负载侧编码器：外接 AS5047P-ATSM，PA3/GPIO4，用于输出轴闭环
- 电机温度传感器：KTY84-130，PC5/TEMP_MOTOR，10 kΩ 上拉
- 母线电压：24 V 标称
- 板级最大相电流目标：10 A
- 通信：UART4 和 CAN，无板载 USB D+/D-
- 制动：当前没有制动电阻斩波功率级

## 2. 关键 MCU 引脚映射

| 功能 | STM32 引脚 | 说明 |
|---|---|---|
| PWM AH/BH/CH | PA8/PA9/PA10 | TIM1 CH1/CH2/CH3 |
| PWM AL/BL/CL | PB13/PB14/PB15 | TIM1 CH1N/CH2N/CH3N |
| B 相电流 | PC0 | ADC 通道 10 |
| C 相电流 | PC1 | ADC 通道 11 |
| VBUS 采样 | PA6 | 分压比 11:1 |
| DRV8301 nCS | PC13 | SPI3 软件片选 |
| DRV8301 EN_GATE | PB12 | 高电平使能 |
| DRV8301 nFAULT | PD2 | 低电平故障 |
| SPI3 SCK/MISO/MOSI | PC10/PC11/PC12 | DRV8301 与 AS5047P 共用 |
| 电机侧 AS5047P nCS | PA2 | 逻辑 GPIO3 |
| 负载侧 AS5047P nCS | PA3 | 逻辑 GPIO4 |
| 电机温度 KTY84-130 | PC5 | ADC 通道 15 |
| UART RX/TX | PA1/PA0 | UART4，115200 8N1 |
| CAN RX/TX | PB8/PB9 | CAN1 |
| SWDIO/SWCLK | PA13/PA14 | DAPLink 调试口 |

## 3. 功率级与电流采样

- 三个半桥：A/B/C
- A 相下桥直接到 GND
- B/C 相下桥各有一个采样电阻
- A 相电流由 B、C 相重构：

```text
Ia = -Ib - Ic
```

最终采样电阻：

```text
R4 = R5 = 1 mΩ
```

固件参数：

```text
SHUNT_RESISTANCE = 1000e-6f
requested_current_range = 120 A
DRV8301 gain = 10 V/V
current_lim = 10 A
current_lim_margin = 2 A
```

## 4. 自定义板固件目标

板级编译目标：

```text
v3.6-custom-24V
```

配置文件：

```text
Firmware/tup.config

CONFIG_BOARD_VERSION=v3.6-custom-24V
CONFIG_DEBUG=false
CONFIG_DOCTEST=false
CONFIG_USE_LTO=false
```

本地构建脚本：

```text
Firmware/build_custom.py
```

编译命令：

```powershell
cd D:\\RM\\program\\ODrive\\Firmware
python -B build_custom.py -j 8
```

如果接口文件已经生成，可以加快速度：

```powershell
python -B build_custom.py --no-generate -j 8
```

输出文件：

```text
Firmware/build/ODriveFirmware.elf
Firmware/build/ODriveFirmware.hex
Firmware/build/ODriveFirmware.bin
```

## 5. DAPLink 烧录与调试

接口配置：

```text
interface/cmsis-dap.cfg
target/stm32f4x.cfg
```

烧录命令：

```powershell
openocd -f interface/cmsis-dap.cfg -f target/stm32f4x.cfg -c "adapter speed 500" -c "program Firmware/build/ODriveFirmware.elf verify reset exit"
```

只探测目标：

```powershell
openocd -f interface/cmsis-dap.cfg -f target/stm32f4x.cfg -c "adapter speed 500" -c "init" -c "targets" -c "flash probe 0" -c "shutdown"
```

开启 GDB Server：

```powershell
openocd -f interface/cmsis-dap.cfg -f target/stm32f4x.cfg -c "adapter speed 500" -c "gdb_port 3333" -c "init"
```

调试结束后确认没有残留的 `openocd.exe`：

```powershell
Get-Process openocd -ErrorAction SilentlyContinue
```

必要时结束：

```powershell
Get-Process openocd -ErrorAction SilentlyContinue | Stop-Process -Force
```

如果 DAPLink 虚拟串口出现“端口被关闭”或完全无响应，拔插一次 DAPLink，然后重新打开 COM8。

## 6. 自定义固件实现

`BOARD_CUSTOM` 编译目标包含：

- 单轴 `AXIS_COUNT = 1`
- 1 mΩ 采样电阻和 10 V/V DRV8301 增益
- 电机侧 U6 作为 FOC 换相编码器
- 独立负载侧编码器对象 `axis0.load_encoder`
- 负载侧编码器接入 Controller 的位置/速度闭环
- PC5 上的 KTY84-130 温度限制
- PA2/PA3 在启动阶段先置高，避免 AS5047P 与 DRV8301 共用 MISO 时抢总线

注意：电机侧 U6 只负责 FOC 换相，负载侧编码器负责位置/速度控制。两者不能混用标定结果。

## 7. 事故原因与修复记录

### 7.1 采样电阻与固件参数不一致

最初采样电阻为 500 mΩ，后来改为 1 mΩ。采样电阻、DRV8301 放大倍数和固件参数不一致会导致：

- 相电流测量严重错误
- 相电阻和相电感校准失败
- `CURRENT_LIMIT_VIOLATION`
- `DRV_FAULT`
- 电机在校准或闭环过程中异常停机

最终统一为：

```text
采样电阻 = 1 mΩ
DRV8301 gain = 10 V/V
SHUNT_RESISTANCE = 1000e-6f
requested_current_range = 120 A
```

### 7.2 AS5047P 与 DRV8301 共用 MISO

AS5047P 和 DRV8301 共用：

```text
PC11 / SPI3_MISO
```

启动时必须先把编码器 nCS 拉高，再初始化 DRV8301。否则 AS5047P 可能占用 MISO，导致 DRV8301 SPI 回读失败。

最终处理：

- PA2 和 PA3 在启动时先配置为输出并置高
- 电机侧 U6 使用 PA2
- 负载侧 AS5047P 使用 PA3
- DRV8301 使用 PC13 作为 nCS

### 7.3 AS5047P 抗干扰

电机换相时曾出现：

```text
ABS_SPI_COM_FAIL
encoder.error = 0x80
axis.error = 0x100
```

处理措施：

- 给 AS5047P 的 3V3 增加去耦电容
- SPI 线远离三相功率走线
- AS5047P SPI 时钟降低到约 656 kHz
- 启动时确保编码器 nCS 为高

处理后电机侧编码器偏移校准通过。

### 7.4 DRV8301 OCP 与开关瞬态

MOSFET 为 CSD18540Q5B，导通电阻较低。DRV8301 的 VDS OCP 无法精确保护 10 A 级相电流，同时容易受到开关瞬态影响。

最终参数：

```text
OCP VDS = 1.043 V
PWM deadtime ≈ 238 ns
nFAULT 增加 4 个控制周期软件去抖
正常电流保护主要依靠软件 current_lim
```

### 7.5 没有制动电阻

原板没有制动斩波功率级。ODrive 默认回灌电流限制很严格，校准过程中曾出现：

```text
DC_BUS_OVER_REGEN_CURRENT
ODrive.error = 0x8
```

测试固件配置：

```text
enable_brake_resistor = false
dc_max_negative_current = -1.0 A
```

正式使用如果存在高速减速、下放负载或较大反电动势，应增加制动电阻和制动斩波电路。

### 7.6 极对数与电机侧编码器方向

最终通过编码器偏移校准扫描计算：

```text
8 个电周期
编码器计数变化 = 6167
P = 8 × 16384 / 6167 ≈ 21.25
```

最终参数：

```text
pole_pairs = 21
encoder.direction = -1
phase_offset = 196
phase_offset_float = 1.44740248
```

### 7.7 双 AS5047P 共用 SPI3 的 DMA 排队

电机侧 U6 与负载侧 AS5047P 共用 SPI3。若在同一控制周期连续排队两个 DMA
传输，第二个任务可能在前一个 TX DMA 尚未释放时启动失败；原仲裁器会把它永久
留在队列中，表现为 `axis0.load_encoder.shadow_count` 不更新，但 SPI 错误率仍为 0。

已在 `Stm32SpiArbiter` 中加入 `start_pending_` 和 `kick()` 重试机制，在随后
的采样周期重新启动未完成的 DMA 传输。修复后两只 AS5047P 可同时以控制环频率
工作。

### 7.8 负载侧编码器机械连接

负载侧 AS5047P 通信正常只能说明 SPI 配置和芯片供电正确，不能证明磁铁随输出轴
转动。实测手动转动输出轴时：

```text
axis0.encoder.shadow_count      变化约 +466318
axis0.load_encoder.shadow_count 始终为 0
axis0.load_encoder.error         0
axis0.load_encoder.is_ready      1
axis0.load_encoder.spi_error_rate 0
```

因此当前阻塞点是机械安装：AS5047P 的磁铁或转轴没有与输出轴同步。启用负载侧闭环前必须确认：

- AS5047P 磁铁固定在输出轴上；
- 磁铁与芯片同心且气隙符合数据手册；
- 转动输出轴时 `axis0.load_encoder.pos_abs` 或 `shadow_count` 明显变化。

### 7.9 上电后第一次直接开环

原开环路径没有连接 `motor_.torque_setpoint_src_`，上电后第一次直接进入
`AXIS_STATE_LOCKIN_SPIN` 可能报 `ERROR_UNKNOWN_TORQUE`。现已在
`run_lockin_spin()` 中连接到 `OpenLoopController::torque_setpoint_`，每周期写 0。

## 8. 最终固件参数

```text
Board target: v3.6-custom-24V
Axis count: 1
Shunt resistance: 1 mΩ
DRV8301 gain: 10 V/V
Requested current range: 120 A
Current limit: 10 A
Current limit margin: 2 A
Pole pairs: 21
Phase resistance: 0.0825 Ω
Phase inductance: 100 µH，估计值
Motor encoder: AS5047P / SPI ABS AMS / 16384 CPR
Motor encoder CS: PA2 / GPIO3
Motor encoder direction: -1
Phase offset: 196
Phase offset float: 1.44740248
Load encoder: AS5047P / SPI ABS AMS / 16384 CPR
Load encoder CS: PA3 / GPIO4
Load encoder direction: 1（机械安装完成后仍需核对方向）
SPI prescaler: 64
PWM deadtime: 40 clocks ≈ 238 ns
DRV OCP: 1.043 V
nFAULT debounce: 4 samples
DC max negative current: -1 A
Motor temperature sensor: KTY84-130，PC5，10 kΩ 上拉
```

## 9. 当前验证状态

```text
motor.error = 0
motor.is_calibrated = 1
axis.error = 0
encoder.error = 0
encoder.is_ready = 1
load_encoder.error = 0
load_encoder.is_ready = 1
load_encoder.spi_error_rate = 0
fet_thermistor.temperature ≈ 30...33 °C（室温环境）
phase_offset = 196
phase_offset_float = 1.44740248
```

注意：负载侧编码器闭环尚未完成验证。当前阻塞点是 7.8 节所述的机械连接，
不能把“SPI 通信成功”误认为“负载轴反馈有效”。

## 10. 常用控制与测量命令

### 10.1 低速闭环配置

```text
sc
w axis0.controller.config.control_mode 2
w axis0.controller.config.input_mode 2
w axis0.controller.config.vel_limit 0.05
w axis0.controller.config.vel_limit_tolerance 1.2
w axis0.controller.config.vel_ramp_rate 0.02
w axis0.motor.config.current_lim 1.0
w axis0.motor.config.current_lim_margin 0.5
w axis0.config.enable_watchdog 0
w axis0.requested_state 8
```

### 10.2 负载侧速度命令

接入负载侧编码器后，控制器速度单位变为输出轴 turn/s：

```text
v <axis> <output_turn_per_sec> <torque_feedforward>
```

第一次测试应使用很小的输出速度：

```text
v 0 0.01 0
```

停止：

```text
v 0 0 0
w axis0.requested_state 1
```

### 10.3 测量减速比

先读取两只编码器的线性计数：

```text
r axis0.encoder.shadow_count
r axis0.load_encoder.shadow_count
```

转动输出轴后再次读取：

```text
ratio = (motor_count_after - motor_count_before)
      / (load_count_after - load_count_before)
```

该比值是电机轴/输出轴机械减速比。不要把 20:1 或其他猜测值写进固件；
控制器只使用负载侧编码器的输出轴转数，电机侧 U6 仍只负责 FOC 换相。

### 10.4 温度读取

```text
r axis0.motor.fet_thermistor.temperature
r axis0.motor.fet_thermistor.config.enabled
```

### 10.5 编码器诊断

```text
r axis0.encoder.error
r axis0.encoder.is_ready
r axis0.encoder.pos_estimate
r axis0.load_encoder.error
r axis0.load_encoder.is_ready
r axis0.load_encoder.pos_abs
r axis0.load_encoder.pos_estimate
r axis0.load_encoder.shadow_count
r axis0.load_encoder.spi_error_rate
```

## 11. 注意事项

1. 更换电机、编码器磁铁、相线顺序、采样电阻后，必须重新校准。
2. `100 µH` 是估计值，不是精密 LCR 测量值。
3. 当前没有制动电阻，避免高速急减速和大惯量下放。
4. OCP 只保留短路级保护，运行电流由软件 `current_lim` 控制。
5. 正式运行建议启用 watchdog，并周期性发送控制命令。
6. 调试结束后确认没有残留的 `openocd.exe` 进程；DAPLink 虚拟串口异常时拔插一次。
7. UART 命令中的属性名必须使用普通下划线 `_`，不能包含反斜杠 `\`。
8. `mine/*.bin` 是本地固件备份，不提交到 GitHub。