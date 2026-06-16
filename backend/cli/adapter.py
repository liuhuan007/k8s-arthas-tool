from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RiskLevel(Enum):
    READ = "read"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class StructuredResult:
    ok: bool
    command: str
    data: Any = None
    raw_output: str = ""
    health: Optional[Dict] = None
    error: Optional[str] = None
    error_detail: Optional[Dict] = None
    metadata: Dict = field(default_factory=dict)


class CLIAdapter(ABC):
    """CLI 统一抽象接口"""

    @abstractmethod
    def execute(self, command: str, params: Dict[str, Any]) -> StructuredResult:
        """执行命令，返回结构化结果"""

    @abstractmethod
    def get_commands(self) -> List[Dict]:
        """获取可用命令列表（含元数据）"""

    @abstractmethod
    def health_check(self, target: str = "", params: Dict = None) -> Dict:
        """检查目标健康状态"""

    @abstractmethod
    def dry_run(self, command: str, params: Dict[str, Any]) -> Dict:
        """Dry-run 预览"""
