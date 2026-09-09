"""System / hardware info helpers for /info and Hub core_rpc server_info."""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from typing import Any

import psutil

_cpu_name_cache: str | None = None
_cpu_max_freq_cache: float | None = None
_cpu_percent_primed = False
_host_id_cache: str | None = None
_gpu_cache: list[dict[str, Any]] | None = None
_machine_uuid_cache: str | None = None

try:
    psutil.cpu_percent(interval=None)
    _cpu_percent_primed = True
except Exception:
    pass


def get_cpu_name():
    global _cpu_name_cache
    if _cpu_name_cache is not None:
        return _cpu_name_cache
    _cpu_name_cache = _read_cpu_name()
    return _cpu_name_cache


def _read_cpu_name():
    if sys.platform.startswith("win"):
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "Get-WmiObject -Class Win32_Processor | Select-Object -ExpandProperty Name",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().splitlines()[0].strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        try:
            result = subprocess.run(
                ["wmic", "cpu", "get", "name", "/format:value"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if line.startswith("Name="):
                        cpu_name = line.split("=", 1)[1].strip()
                        if cpu_name:
                            return cpu_name
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        return platform.processor() or "Unknown CPU"

    if sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return platform.processor() or "Unknown CPU"

    return platform.processor() or "Unknown CPU"


def get_cpu_max_freq():
    """获取CPU最大频率（GHz）。"""
    global _cpu_max_freq_cache
    if _cpu_max_freq_cache is not None:
        return _cpu_max_freq_cache
    _cpu_max_freq_cache = _read_cpu_max_freq()
    return _cpu_max_freq_cache


def _sample_cpu_percent():
    """非阻塞 CPU 使用率：首次调用只做基准采样，之后用差值。"""
    global _cpu_percent_primed
    usage = psutil.cpu_percent(interval=None)
    if not _cpu_percent_primed:
        _cpu_percent_primed = True
        return max(0.0, float(usage or 0.0))
    return max(0.0, float(usage or 0.0))


def _read_cpu_max_freq():
    if sys.platform.startswith("win"):
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "Get-WmiObject -Class Win32_Processor | Select-Object -ExpandProperty MaxClockSpeed",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                max_freq_mhz = float(result.stdout.strip().splitlines()[0].strip())
                return max_freq_mhz / 1000
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, Exception):
            pass

        try:
            result = subprocess.run(
                ["wmic", "cpu", "get", "MaxClockSpeed", "/format:value"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if line.startswith("MaxClockSpeed="):
                        freq_str = line.split("=", 1)[1].strip()
                        if freq_str and freq_str.isdigit():
                            return int(freq_str) / 1000
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, Exception):
            pass

        cpu_freq = psutil.cpu_freq()
        if cpu_freq and cpu_freq.max:
            return cpu_freq.max / 1000

    elif sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "cpu MHz" in line:
                        freq_mhz = float(line.split(":", 1)[1].strip())
                        return freq_mhz / 1000

            try:
                with open(
                    "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq",
                    "r",
                    encoding="utf-8",
                ) as f:
                    max_freq_khz = int(f.read().strip())
                    return max_freq_khz / 1000000
            except FileNotFoundError:
                pass
        except Exception:
            pass

    cpu_freq = psutil.cpu_freq()
    if cpu_freq and cpu_freq.max:
        return cpu_freq.max / 1000
    return None


def get_os_info():
    """获取操作系统信息。"""
    if sys.platform.startswith("linux"):
        try:
            with open("/etc/os-release", "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                os_info = {}
                for line in lines:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        os_info[key] = value.strip('"')

                if "PRETTY_NAME" in os_info:
                    return os_info["PRETTY_NAME"]
                if "NAME" in os_info and "VERSION" in os_info:
                    return f"{os_info['NAME']} {os_info['VERSION']}"
                return f"Linux {platform.release()}"
        except FileNotFoundError:
            return f"Linux {platform.release()}"
    return f"{platform.system()} {platform.release()} {platform.version()}"


def _read_machine_uuid() -> str:
    global _machine_uuid_cache
    if _machine_uuid_cache is not None:
        return _machine_uuid_cache

    value = ""
    if sys.platform.startswith("win"):
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "(Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                value = result.stdout.strip().splitlines()[0].strip()
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    value = f.read().strip()
                    if value:
                        break
            except Exception:
                continue

    _machine_uuid_cache = value or "unknown-machine"
    return _machine_uuid_cache


def get_host_id(cpu_model: str | None = None, mem_total_gb: float | None = None) -> str:
    """Stable fingerprint for the physical host (same across MC instances)."""
    global _host_id_cache
    if _host_id_cache is not None:
        return _host_id_cache

    if cpu_model is None:
        cpu_model = get_cpu_name()
    if mem_total_gb is None:
        mem_total_gb = round(psutil.virtual_memory().total / (1024**3), 0)

    raw = "|".join(
        [
            platform.node() or "",
            _read_machine_uuid(),
            str(cpu_model or ""),
            str(int(mem_total_gb or 0)),
        ]
    )
    _host_id_cache = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return _host_id_cache


def get_gpu_list() -> list[dict[str, Any]]:
    """Detect GPUs; returns empty list when unavailable."""
    global _gpu_cache
    if _gpu_cache is not None:
        return list(_gpu_cache)

    gpus: list[dict[str, Any]] = []
    if sys.platform.startswith("win"):
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-Command",
                    "Get-CimInstance Win32_VideoController | "
                    "Select-Object -ExpandProperty Name",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    name = line.strip()
                    if name and name.lower() not in ("name",):
                        gpus.append({"name": name})
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if not parts or not parts[0]:
                        continue
                    entry: dict[str, Any] = {"name": parts[0]}
                    if len(parts) > 1:
                        try:
                            entry["memory_mb"] = float(parts[1])
                        except ValueError:
                            pass
                    gpus.append(entry)
        except Exception:
            pass

        if not gpus:
            try:
                result = subprocess.run(
                    ["lspci"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        low = line.lower()
                        if "vga compatible controller" in low or "3d controller" in low:
                            name = line.split(":", 2)[-1].strip() if ":" in line else line.strip()
                            if name:
                                gpus.append({"name": name})
            except Exception:
                pass

    # Deduplicate identical names
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in gpus:
        name = str(item.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        unique.append(item)

    _gpu_cache = unique
    return list(unique)


def get_system_info():
    os_info = get_os_info()
    cpu_model = get_cpu_name()
    cpu_max_freq = get_cpu_max_freq()
    cpu_freq = psutil.cpu_freq()
    cpu_usage = max(0, _sample_cpu_percent())
    mem = psutil.virtual_memory()
    mem_total = mem.total / (1024**3)
    mem_used = mem.used / (1024**3)
    mem_percent = mem.percent

    print(f"操作系统: {os_info}")
    if cpu_max_freq:
        print(f"CPU型号: {cpu_model} @{cpu_max_freq:.2f} GHz")
    else:
        print(f"CPU型号: {cpu_model}")
    print(
        f"CPU核心数: {psutil.cpu_count(logical=False)} 物理核心 / "
        f"{psutil.cpu_count(logical=True)} 逻辑核心"
    )
    if cpu_freq and cpu_freq.current:
        print(f"CPU频率: {cpu_freq.current / 1000:.2f} GHz")
    else:
        print("CPU频率: 未知")
    print(f"CPU使用率: {cpu_usage:.2f} %")
    print(f"内存总量: {mem_total:.2f} GB")
    print(f"内存已用: {mem_used:.2f} GB")
    print(f"内存使用率: {mem_percent:.2f} %")
    disk_partitions = psutil.disk_partitions()
    print("\n硬盘信息:")
    processed_devices = set()
    for partition in disk_partitions:
        if partition.device in processed_devices or partition.fstype in [
            "tmpfs",
            "devtmpfs",
            "sysfs",
            "proc",
            "cgroup",
            "cgroup2",
        ]:
            continue
        try:
            partition_usage = psutil.disk_usage(partition.mountpoint)
            disk_total = partition_usage.total / (1024**3)
            disk_used = partition_usage.used / (1024**3)
            disk_free = partition_usage.free / (1024**3)
            disk_percent = (disk_used / disk_total) * 100
            print(f"  {partition.device} 挂载点:{partition.mountpoint} ({partition.fstype})")
            print(f"    总容量: {disk_total:.2f} GB")
            print(f"    已使用: {disk_used:.2f} GB ({disk_percent:.1f}%)")
            print(f"    可用空间: {disk_free:.2f} GB")
            processed_devices.add(partition.device)
        except PermissionError:
            print(f"  {partition.device} - 无法访问")


def get_system_info_dict():
    """
    获取系统信息并返回字典格式。

    Returns:
        dict: 包含系统信息的字典（含 host_id / hostname / gpu）。
    """
    os_info = get_os_info()
    cpu_model = get_cpu_name()
    cpu_max_freq = get_cpu_max_freq()
    cpu_freq = psutil.cpu_freq()
    cpu_usage = max(0, _sample_cpu_percent())
    mem = psutil.virtual_memory()
    mem_total_gb = round(mem.total / (1024**3), 2)

    disk_info = []
    disk_partitions = psutil.disk_partitions()
    processed_devices = set()

    for partition in disk_partitions:
        if partition.device in processed_devices or partition.fstype in [
            "tmpfs",
            "devtmpfs",
            "sysfs",
            "proc",
            "cgroup",
            "cgroup2",
        ]:
            continue
        try:
            partition_usage = psutil.disk_usage(partition.mountpoint)
            disk_info.append(
                {
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total_gb": round(partition_usage.total / (1024**3), 2),
                    "used_gb": round(partition_usage.used / (1024**3), 2),
                    "free_gb": round(partition_usage.free / (1024**3), 2),
                    "percent": round(
                        (partition_usage.used / partition_usage.total) * 100, 1
                    ),
                }
            )
            processed_devices.add(partition.device)
        except PermissionError:
            disk_info.append({"device": partition.device, "error": "无法访问"})

    hostname = platform.node() or "unknown"
    return {
        "os": os_info,
        "hostname": hostname,
        "host_id": get_host_id(cpu_model, mem_total_gb),
        "cpu": {
            "model": cpu_model,
            "max_freq_ghz": cpu_max_freq,
            "current_freq_ghz": (
                cpu_freq.current / 1000 if cpu_freq and cpu_freq.current else None
            ),
            "usage_percent": cpu_usage,
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
        },
        "memory": {
            "total_gb": mem_total_gb,
            "used_gb": round(mem.used / (1024**3), 2),
            "percent": mem.percent,
        },
        "gpus": get_gpu_list(),
        "disks": disk_info,
    }


def build_server_info_payload(plugin: Any) -> dict[str, Any]:
    """Build structured server + system info for Hub aggregation.

    Args:
        plugin: ArcQQSyncAstrbot plugin instance.

    Returns:
        Dict with game fields under top-level keys and ``system`` hardware block.
    """
    from .time_utils import TimeUtils

    online_count = len(plugin.server.online_players)
    max_players = plugin.server.max_players
    server_name = plugin.server_name
    version = plugin.server.version
    minecraft_version = plugin.server.minecraft_version
    start_time = plugin.server.start_time
    total_bindings = len(plugin.data_manager.binding_data)

    time_info = TimeUtils.get_current_time_info()
    uptime_info = TimeUtils.calculate_uptime(start_time)
    system_info = get_system_info_dict()

    return {
        "ok": True,
        "server_name": server_name,
        "endstone_version": str(version),
        "minecraft_version": str(minecraft_version),
        "start_time": TimeUtils.format_datetime(start_time),
        "current_time": time_info["formatted_time"],
        "time_source": time_info["source"],
        "uptime_str": uptime_info["uptime_str"],
        "online_players": online_count,
        "max_players": max_players,
        "total_bindings": total_bindings,
        "system": system_info,
    }


def format_server_info_text(payload: dict[str, Any]) -> str:
    """Format a single-server info payload as QQ-facing text.

    Args:
        payload: Output of ``build_server_info_payload``.

    Returns:
        Multi-line reply text.
    """
    system_info = payload.get("system") or {}
    reply = "ℹ️ 服务器信息:\n"
    reply += f"• 服务器名称: {payload.get('server_name') or '?'}\n"
    reply += f"• Endstone版本: {payload.get('endstone_version') or '?'}\n"
    reply += f"• Minecraft版本: {payload.get('minecraft_version') or '?'}\n"
    reply += f"• 启动时间: {payload.get('start_time') or '?'}\n"
    reply += (
        f"• 当前时间: {payload.get('current_time') or '?'} "
        f"({payload.get('time_source') or '服务器时间'})\n"
    )
    reply += f"• 运行时长: {payload.get('uptime_str') or '?'}\n"
    reply += (
        f"• 在线玩家: {payload.get('online_players', 0)}/"
        f"{payload.get('max_players', '?')}\n"
    )
    reply += f"• 总绑定数: {payload.get('total_bindings', 0)}\n"

    reply += "\n🖥️ 系统信息:\n"
    reply += f"• 主机名: {system_info.get('hostname') or '?'}\n"
    reply += f"• 操作系统: {system_info.get('os') or '?'}\n"

    cpu_info = system_info.get("cpu") or {}
    model = str(cpu_info.get("model") or "未知")
    cpu_model = model[:50] + "..." if len(model) > 50 else model
    reply += f"• CPU型号: {cpu_model}\n"

    if cpu_info.get("max_freq_ghz"):
        reply += f"• CPU主频: {float(cpu_info['max_freq_ghz']):.2f}GHz"
        if cpu_info.get("current_freq_ghz"):
            reply += f" (当前: {float(cpu_info['current_freq_ghz']):.2f}GHz)"
        reply += "\n"

    phys = cpu_info.get("physical_cores") or "?"
    logic = cpu_info.get("logical_cores") or "?"
    reply += f"• CPU核心: {phys}核{logic}线程\n"
    reply += f"• CPU使用率: {float(cpu_info.get('usage_percent') or 0):.1f}%\n"

    mem_info = system_info.get("memory") or {}
    reply += (
        f"• 内存: {float(mem_info.get('used_gb') or 0):.1f}GB / "
        f"{float(mem_info.get('total_gb') or 0):.1f}GB "
        f"({float(mem_info.get('percent') or 0):.1f}%)\n"
    )

    gpus = system_info.get("gpus") or []
    if gpus:
        for idx, gpu in enumerate(gpus, start=1):
            name = str(gpu.get("name") or "未知")
            label = f"GPU{idx}" if len(gpus) > 1 else "GPU"
            mem_mb = gpu.get("memory_mb")
            if mem_mb is not None:
                reply += f"• {label}: {name} ({float(mem_mb):.0f}MB)\n"
            else:
                reply += f"• {label}: {name}\n"
    else:
        reply += "• GPU: 未检测到\n"

    for disk in system_info.get("disks") or []:
        if "error" in disk:
            continue
        reply += (
            f"• 硬盘({disk.get('device')}): "
            f"{float(disk.get('used_gb') or 0):.1f}GB / "
            f"{float(disk.get('total_gb') or 0):.1f}GB "
            f"({float(disk.get('percent') or 0):.1f}%)\n"
        )

    reply += "\n• ARC QQ Sync: 运行中 ✅"
    return reply


def print_system_info():
    """打印格式化的系统信息（原来的 get_system_info 函数）。"""
    get_system_info()


def main():
    """主函数，打印系统信息。"""
    get_system_info()


if __name__ == "__main__":
    main()
