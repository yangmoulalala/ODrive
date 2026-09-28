#!/usr/bin/env python3
"""Build the single-axis ODrive custom board without requiring tup.

The source and flag sets mirror Firmware/Tupfile.lua for the
v3.6-custom-24V target.  Outputs are written to Firmware/build/.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
OBJ = BUILD / "obj"


def find_tool(name: str) -> str:
    tool = shutil.which(name)
    if not tool:
        raise SystemExit(f"required tool not found on PATH: {name}")
    return tool


CC = find_tool("arm-none-eabi-gcc")
CXX = find_tool("arm-none-eabi-g++")
SIZE = find_tool("arm-none-eabi-size")
OBJCOPY = find_tool("arm-none-eabi-objcopy")


SOURCES = [
    # ODrive firmware package
    "syscalls.c",
    "MotorControl/utils.cpp",
    "MotorControl/arm_sin_f32.c",
    "MotorControl/arm_cos_f32.c",
    "MotorControl/low_level.cpp",
    "MotorControl/axis.cpp",
    "MotorControl/motor.cpp",
    "MotorControl/thermistor.cpp",
    "MotorControl/encoder.cpp",
    "MotorControl/endstop.cpp",
    "MotorControl/acim_estimator.cpp",
    "MotorControl/mechanical_brake.cpp",
    "MotorControl/controller.cpp",
    "MotorControl/foc.cpp",
    "MotorControl/open_loop_controller.cpp",
    "MotorControl/oscilloscope.cpp",
    "MotorControl/sensorless_estimator.cpp",
    "MotorControl/trapTraj.cpp",
    "MotorControl/pwm_input.cpp",
    "MotorControl/main.cpp",
    "Drivers/STM32/stm32_system.cpp",
    "Drivers/STM32/stm32_gpio.cpp",
    "Drivers/STM32/stm32_nvm.c",
    "Drivers/STM32/stm32_spi_arbiter.cpp",
    "communication/can/can_simple.cpp",
    "communication/can/odrive_can.cpp",
    "communication/communication.cpp",
    "communication/ascii_protocol.cpp",
    "communication/interface_uart.cpp",
    "communication/interface_usb.cpp",
    "communication/interface_i2c.cpp",
    "FreeRTOS-openocd.c",
    "autogen/version.c",
    # Fibre package, server-only configuration
    "fibre-cpp/fibre.cpp",
    "fibre-cpp/channel_discoverer.cpp",
    "fibre-cpp/legacy_protocol.cpp",
    # STM32F4 HAL package
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc_ex.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_can.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_cortex.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma_ex.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ex.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ramfunc.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_gpio.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_i2c.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_i2c_ex.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pcd.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pcd_ex.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr_ex.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc_ex.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_spi.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim_ex.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_uart.c",
    "ThirdParty/STM32F4xx_HAL_Driver/Src/stm32f4xx_ll_usb.c",
    # FreeRTOS package
    "ThirdParty/FreeRTOS/Source/croutine.c",
    "ThirdParty/FreeRTOS/Source/event_groups.c",
    "ThirdParty/FreeRTOS/Source/list.c",
    "ThirdParty/FreeRTOS/Source/queue.c",
    "ThirdParty/FreeRTOS/Source/stream_buffer.c",
    "ThirdParty/FreeRTOS/Source/tasks.c",
    "ThirdParty/FreeRTOS/Source/timers.c",
    "ThirdParty/FreeRTOS/Source/CMSIS_RTOS/cmsis_os.c",
    "ThirdParty/FreeRTOS/Source/portable/MemMang/heap_4.c",
    # USB device library
    "ThirdParty/STM32_USB_Device_Library/Core/Src/usbd_core.c",
    "ThirdParty/STM32_USB_Device_Library/Core/Src/usbd_ctlreq.c",
    "ThirdParty/STM32_USB_Device_Library/Core/Src/usbd_ioreq.c",
    "ThirdParty/STM32_USB_Device_Library/Class/CDC/Src/usbd_cdc.c",
    # Board package
    "Board/v3/startup_stm32f405xx.s",
    "ThirdParty/FreeRTOS/Source/portable/GCC/ARM_CM4F/port.c",
    "Drivers/DRV8301/drv8301.cpp",
    "Board/v3/board.cpp",
    "Board/v3/Src/stm32f4xx_hal_timebase_TIM.c",
    "Board/v3/Src/tim.c",
    "Board/v3/Src/dma.c",
    "Board/v3/Src/freertos.c",
    "Board/v3/Src/main.c",
    "Board/v3/Src/usbd_conf.c",
    "Board/v3/Src/spi.c",
    "Board/v3/Src/usart.c",
    "Board/v3/Src/usbd_cdc_if.c",
    "Board/v3/Src/adc.c",
    "Board/v3/Src/stm32f4xx_hal_msp.c",
    "Board/v3/Src/usbd_desc.c",
    "Board/v3/Src/stm32f4xx_it.c",
    "Board/v3/Src/usb_device.c",
    "Board/v3/Src/can.c",
    "Board/v3/Src/system_stm32f4xx.c",
    "Board/v3/Src/gpio.c",
    "Board/v3/Src/i2c.c",
]

INCLUDES = [
    ".",
    "MotorControl",
    "Drivers/DRV8301",
    "Board/v3/Inc",
    "ThirdParty/STM32F4xx_HAL_Driver/Inc",
    "ThirdParty/FreeRTOS/Source/include",
    "ThirdParty/FreeRTOS/Source/CMSIS_RTOS",
    "ThirdParty/FreeRTOS/Source/portable/GCC/ARM_CM4F",
    "ThirdParty/STM32_USB_Device_Library/Core/Inc",
    "ThirdParty/STM32_USB_Device_Library/Class/CDC/Inc",
    "ThirdParty/CMSIS/Include",
    "ThirdParty/CMSIS/Device/ST/STM32F4xx/Include",
    "fibre-cpp/include",
]

COMMON = [
    "-mthumb",
    "-mcpu=cortex-m4",
    "-mfpu=fpv4-sp-d16",
    "-mfloat-abi=hard",
    "-DSTM32F405xx",
    "-DUSE_HAL_DRIVER",
    "-DARM_MATH_CM4",
    "-DFPU_FPV4",
    "-DHW_VERSION_MAJOR=3",
    "-DHW_VERSION_MINOR=6",
    "-DHW_VERSION_VOLTAGE=24",
    "-DBOARD_CUSTOM",
    '-D__weak=__attribute__((weak))',
    '-D__packed=__attribute__((__packed__))',
    "-DFIBRE_ENABLE_SERVER=1",
    "-DFIBRE_ENABLE_CLIENT=0",
    "-DFIBRE_ENABLE_EVENT_LOOP=0",
    "-DFIBRE_ALLOW_HEAP=0",
    "-DFIBRE_MAX_LOG_VERBOSITY=0",
    "-DFIBRE_DEFAULT_LOG_VERBOSITY=2",
    "-DFIBRE_ENABLE_LIBUSB_BACKEND=0",
    "-DFIBRE_ENABLE_TCP_SERVER_BACKEND=0",
    "-DFIBRE_ENABLE_TCP_CLIENT_BACKEND=0",
    "-Wall",
    "-Wno-psabi",
    "-Wno-nonnull",
    "-Wdouble-promotion",
    "-Wfloat-conversion",
    "-fdata-sections",
    "-ffunction-sections",
    "-O2",
    "-g",
] + [f"-I{p}" for p in INCLUDES]

LDFLAGS = COMMON + [
    "-LThirdParty/CMSIS/Lib/GCC",
    "-TBoard/v3/STM32F405RGTx_FLASH.ld",
    "-larm_cortexM4lf_math",
    "-flto",
    "-lc",
    "-lm",
    "-lnosys",
    "-specs=nosys.specs",
    "-specs=nano.specs",
    "-u",
    "_printf_float",
    "-u",
    "_scanf_float",
    "-Wl,--cref",
    "-Wl,--gc-sections",
    "-Wl,--undefined=uxTopUsedPriority",
]


def object_path(src: str) -> Path:
    return OBJ / (src.replace("/", "_").replace(".", "_") + ".o")


def compile_one(src: str) -> tuple[str, int, str]:
    compiler = CC if Path(src).suffix.lower() == ".c" or Path(src).suffix.lower() == ".s" else CXX
    lang_flags = ["-std=c99"] if compiler == CC else ["-std=c++17", "-Wno-register"]
    cmd = [compiler, "-c", src, *lang_flags, *COMMON, "-o", str(object_path(src))]
    result = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return src, result.returncode, result.stdout


def generate_interfaces() -> None:
    autogen = ROOT / "autogen"
    autogen.mkdir(exist_ok=True)
    commands = [
        [sys.executable, "-B", str(ROOT.parent / "tools" / "odrive" / "version.py"), "--output", "autogen/version.c"],
        [sys.executable, "-B", "interface_generator_stub.py", "--definitions", "odrive-interface.yaml", "--template", "fibre-cpp/interfaces_template.j2", "--output", "autogen/interfaces.hpp"],
        [sys.executable, "-B", "interface_generator_stub.py", "--definitions", "odrive-interface.yaml", "--template", "fibre-cpp/function_stubs_template.j2", "--output", "autogen/function_stubs.hpp"],
        [sys.executable, "-B", "interface_generator_stub.py", "--definitions", "odrive-interface.yaml", "--generate-endpoints", "ODrive3", "--template", "fibre-cpp/endpoints_template.j2", "--output", "autogen/endpoints.hpp"],
        [sys.executable, "-B", "interface_generator_stub.py", "--definitions", "odrive-interface.yaml", "--template", "fibre-cpp/type_info_template.j2", "--output", "autogen/type_info.hpp"],
    ]
    for cmd in commands:
        subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-j", "--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    parser.add_argument("--no-generate", action="store_true")
    args = parser.parse_args()

    if not args.no_generate:
        generate_interfaces()

    OBJ.mkdir(parents=True, exist_ok=True)
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(compile_one, src): src for src in SOURCES}
        for future in concurrent.futures.as_completed(futures):
            src, rc, output = future.result()
            if rc:
                failures.append((src, output))
            else:
                print(f"CC {src}")

    if failures:
        for src, output in failures:
            print(f"\n===== {src} =====\n{output}", file=sys.stderr)
        return 1

    objs = [str(object_path(src)) for src in SOURCES]
    elf = BUILD / "ODriveFirmware.elf"
    mapfile = BUILD / "ODriveFirmware.map"
    link_cmd = [CXX, *objs, *LDFLAGS, f"-Wl,-Map={mapfile}", "-o", str(elf)]
    result = subprocess.run(link_cmd, cwd=ROOT)
    if result.returncode:
        return result.returncode

    subprocess.run([OBJCOPY, "-O", "ihex", str(elf), str(BUILD / "ODriveFirmware.hex")], cwd=ROOT, check=True)
    subprocess.run([OBJCOPY, "-O", "binary", "-S", str(elf), str(BUILD / "ODriveFirmware.bin")], cwd=ROOT, check=True)
    subprocess.run([SIZE, str(elf)], cwd=ROOT, check=True)
    print(f"Built {elf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
