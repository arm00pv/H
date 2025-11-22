from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseProvider(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    def list_files(self) -> List[Dict[str, Any]]:
        """
        Returns a list of file metadata.
        Each item should have:
        - filename: str
        - size: int
        - content_type: str (optional)
        - external_id: str (unique id in the cloud)
        """
        pass

    @abstractmethod
    def download_file(self, external_id: str):
        """
        Returns a generator or stream for the file content.
        """
        pass
