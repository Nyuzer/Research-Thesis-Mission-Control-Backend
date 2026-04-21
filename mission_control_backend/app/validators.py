import re
from fastapi import HTTPException

_MAP_ID_RE = re.compile(r"^(map_|gen_)[a-f0-9]{8}$")


def validate_map_id(map_id: str) -> str:
    if not _MAP_ID_RE.match(map_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid map_id format. Expected: map_[a-f0-9]{8} or gen_[a-f0-9]{8}",
        )
    return map_id
