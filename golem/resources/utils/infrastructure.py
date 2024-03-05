from dataclasses import dataclass
from typing import Dict

from golem.payload import defaults


@dataclass
class InfrastructureProps:
    memory_gib: float
    """golem.inf.mem.gib"""
    storage_gib: float
    """golem.inf.storage.gib"""
    cpu_threads: int
    """golem.inf.cpu.threads"""

    @classmethod
    def from_properties(cls, properties: Dict) -> "InfrastructureProps":
        return cls(
            memory_gib=properties.get(defaults.PROP_INF_MEM, 0.0),
            storage_gib=properties.get(defaults.PROP_INF_STORAGE, 0.0),
            cpu_threads=properties.get(defaults.PROP_INF_CPU_THREADS, 0),
        )
