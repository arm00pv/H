import mimetypes
import os

class Classifier:
    def __init__(self):
        self.categories = {
            'document': ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.md'],
            'table': ['.xls', '.xlsx', '.csv', '.tsv', '.ods'],
            'code': ['.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.h', '.json', '.xml', '.sh', '.sql'],
            'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.tiff'],
            'video': ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm']
        }

    def classify(self, filename: str, content_type: str = None) -> str:
        """
        Classify a file based on its extension and optionally its content type.
        Returns one of: 'Document', 'Table', 'Code', 'Image', 'Video', or 'Other'.
        """
        _, ext = os.path.splitext(filename)
        ext = ext.lower()

        # Check by extension
        for category, extensions in self.categories.items():
            if ext in extensions:
                return category.capitalize()

        # Fallback to MIME type if provided
        if content_type:
            if content_type.startswith('image/'):
                return 'Image'
            if content_type.startswith('video/'):
                return 'Video'
            if content_type.startswith('text/'):
                # Could be code or document, hard to say for sure without extension,
                # but let's check against common code mime types if we were thorough,
                # for now, default to 'Document' for generic text
                return 'Document'
            if 'spreadsheet' in content_type or 'excel' in content_type or 'csv' in content_type:
                return 'Table'
            if 'pdf' in content_type or 'word' in content_type:
                return 'Document'

        return 'Other'
