from typing import List, Dict, Any
from .base import BaseProvider
import random

class MockProvider(BaseProvider):
    def list_files(self) -> List[Dict[str, Any]]:
        # Simulate some files
        return [
            {
                "filename": "mock_report.pdf",
                "size": 1024 * 500,
                "content_type": "application/pdf",
                "external_id": "mock_1"
            },
            {
                "filename": "vacation.jpg",
                "size": 1024 * 2000,
                "content_type": "image/jpeg",
                "external_id": "mock_2"
            },
            {
                "filename": "data.csv",
                "size": 1024 * 50,
                "content_type": "text/csv",
                "external_id": "mock_3"
            }
        ]

    def download_file(self, external_id: str):
        # Return dummy content
        if external_id == "mock_1":
            yield b"%PDF-1.4 ... mock content ..."
        elif external_id == "mock_2":
            yield b"fake image data"
        else:
            yield b"id,name\n1,Test"
