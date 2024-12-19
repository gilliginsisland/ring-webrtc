from typing import Any
import json
from pathlib import Path


class TokenManager:
    def __init__(self, token_file: Path) -> None:
        self._token_file = token_file
        self._token = json.loads(token_file.read_text(encoding="utf-8"))

    @property
    def token(self) -> dict[str, Any]:
        return self._token

    def update_token(self, token: dict[str, Any]):
        self._token = token
        self._token_file.write_text(json.dumps(self._token), encoding="utf-8")
