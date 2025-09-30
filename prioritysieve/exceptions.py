from __future__ import annotations

from pathlib import Path


class DefaultSettingsException(Exception):
    """Raised when the default settings are used and no note type is selected"""


class AnkiNoteTypeNotFound(Exception):
    """User tried to get Anki data that doesn't exist"""


class AnkiFieldNotFound(Exception):
    """User tried to get Anki data that doesn't exist"""


class CardQueueEmptyException(Exception):
    """The new card queue has no more cards"""


class CancelledOperationException(Exception):
    """Raised when the user clicked 'x' on the recalc pop-up dialog"""


class EmptyFileSelectionException(Exception):
    """No file(s) selected"""


class MorphemizerNotFoundException(Exception):
    """Selected Morphemizer(s) not found on the system"""

    def __init__(self, morphemizer_name: str):
        self.morphemizer_name = morphemizer_name


class PriorityFileNotFoundException(Exception):
    """Selected priority files not found"""

    def __init__(self, path: str):
        self.path = path


class InvalidBinsException(Exception):
    """Invalid indexes used to construct Bins"""

    def __init__(self, min_index: int, max_index: int):
        self.min_index = min_index
        self.max_index = max_index


class PriorityFileMalformedException(Exception):
    """Selected priority file is malformed in some way"""

    def __init__(self, path: Path | str, reason: str):
        self.path: str = str(path) if isinstance(path, Path) else path
        self.reason: str = reason


class KnownMorphsFileMalformedException(Exception):
    """Found known morphs file is malformed in some way"""

    def __init__(self, path: Path):
        self.path: str = path.name


class UnicodeException(Exception):
    """File does not have UTF-8 encoding"""

    def __init__(self, path: Path):
        self.path: str = str(path)
