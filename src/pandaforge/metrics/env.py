"""
Captura de ambiente para reprodutibilidade -- so stdlib (platform,
os, ctypes). Sem GPU nem quantizacao aqui porque o backend atual
(llama-swap) nao expoe isso via API; fica como campo manual se algum
dia precisar.
"""
from __future__ import annotations

import ctypes
import os
import platform
import sys
from dataclasses import dataclass, asdict
from typing import Any


def _total_ram_bytes_windows() -> int | None:
    """RAM total via WinAPI GlobalMemoryStatusEx -- sem psutil."""
    if platform.system() != "Windows":
        return None
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return int(stat.ullTotalPhys)
    except Exception:
        return None


@dataclass
class Environment:
    os_name: str
    os_version: str
    python_version: str
    cpu_name: str
    logical_cpus: int | None
    total_ram_gb: float | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def capture_environment() -> Environment:
    ram_bytes = _total_ram_bytes_windows()
    return Environment(
        os_name=platform.system(),
        os_version=platform.version(),
        python_version=sys.version.split()[0],
        cpu_name=platform.processor() or platform.machine(),
        logical_cpus=os.cpu_count(),
        total_ram_gb=round(ram_bytes / (1024 ** 3), 1) if ram_bytes else None,
    )
