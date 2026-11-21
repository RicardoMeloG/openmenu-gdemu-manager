import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .cdi import CDIError, inspect_cdi

IP_BIN_MAGIC = b"SEGA SEGAKATANA"
IP_BIN_HEADER_SIZE = 0x100
IP_BIN_SEARCH_LIMIT = 8 * 1024 * 1024
IP_BIN_MAX_CANDIDATES = 32
MEDIA_NAME_SUFFIXES = {".cdi", ".gdi", ".iso", ".bin"}
PREFERRED_MEDIA_NAME_SUFFIXES = {".cdi", ".gdi"}
GENERIC_NAME_TOKENS = {
    "boot",
    "data",
    "disc",
    "disk",
    "game",
    "track",
}


@dataclass(frozen=True)
class NameResolution:
    name: str
    source: str
    confidence: str
    internal_name: str = ""
    media_filename: str = ""


def parse_openmenu_ini(path: Path) -> dict[int, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    return parse_openmenu_text(text)


def parse_openmenu_text(text: str) -> dict[int, dict[str, str]]:
    items: dict[int, dict[str, str]] = {}
    for line in text.splitlines():
        match = re.match(r"^(\d+)\.(\w+)=(.*)$", line.strip())
        if not match:
            continue
        slot, key, value = match.groups()
        items.setdefault(int(slot), {})[key] = value
    return items


def parse_openmenu_from_track(track_path: Path) -> dict[int, dict[str, str]]:
    track_path = Path(track_path)
    if not track_path.exists():
        return {}
    try:
        data = track_path.read_bytes()
    except OSError:
        return {}
    start = data.find(b"[OPENMENU]")
    if start == -1:
        return {}
    end = data.find(b"\x00" * 64, start)
    if end == -1:
        end = min(len(data), start + 64 * 1024)
    text = data[start:end].decode("latin-1", errors="replace")
    return parse_openmenu_text(text)


def find_openmenu_track(root: Path) -> Path:
    slot1 = Path(root) / "01"
    preferred = slot1 / "track05.iso"
    if preferred.exists():
        return preferred
    gdi = slot1 / "disc.gdi"
    if gdi.exists():
        declared = _declared_data_tracks(gdi)
        for name in reversed(declared):
            candidate = slot1 / name
            if candidate.exists():
                return candidate
    return preferred


def read_disc_product_id(folder: Path | None) -> str:
    return _read_first_disc_header_field(folder, _read_ip_bin_product)


def read_disc_product_id_from_image(path: Path | None) -> str:
    if path is None:
        return ""
    return _read_ip_bin_product(Path(path))


def read_disc_internal_name(folder: Path | None) -> str:
    return _read_first_disc_header_field(folder, _read_ip_bin_internal_name)


def read_disc_internal_name_from_image(path: Path | None) -> str:
    if path is None:
        return ""
    return _read_ip_bin_internal_name(Path(path))


def resolve_game_display_name(folder: Path, menu_name: str = "", slot: int = 0) -> NameResolution:
    folder = Path(folder)
    folder_name = folder.name
    name_txt = read_name_txt(folder)
    if is_descriptive_game_name(name_txt):
        return NameResolution(name_txt, "name_txt", "high", read_disc_internal_name(folder), "")

    if is_descriptive_game_name(menu_name):
        return NameResolution(menu_name.strip(), "openmenu", "high", read_disc_internal_name(folder), "")

    internal_name = read_disc_internal_name(folder)
    media_name = read_descriptive_media_filename(folder)
    if media_name:
        return NameResolution(media_name, "media_filename", "medium", internal_name, media_name)

    if is_descriptive_game_name(internal_name):
        return NameResolution(internal_name, "internal_name", "medium", internal_name, "")

    fallback = folder_name or (f"{slot:03d}" if slot else "")
    return NameResolution(fallback, "folder", "low", internal_name, "")


def read_descriptive_media_filename(folder: Path | None) -> str:
    if folder is None:
        return ""
    folder = Path(folder)
    if not folder.exists():
        return ""
    candidates = _media_name_candidates(folder, PREFERRED_MEDIA_NAME_SUFFIXES)
    candidates.extend(_media_name_candidates(folder, MEDIA_NAME_SUFFIXES - PREFERRED_MEDIA_NAME_SUFFIXES))
    for candidate in candidates:
        stem = _clean_media_stem(candidate.stem)
        if is_descriptive_game_name(stem):
            return stem
    return ""


def _read_first_disc_header_field(folder: Path | None, reader) -> str:
    if folder is None:
        return ""
    folder = Path(folder)
    if not folder.exists():
        return ""
    candidates: list[Path] = []
    gdi = folder / "disc.gdi"
    if gdi.exists():
        candidates.extend(_gdi_data_tracks(folder, gdi))
    candidates.extend(sorted(folder.glob("*.iso")))
    candidates.extend(sorted(folder.glob("*.bin")))
    candidates.extend(sorted(folder.glob("*.cdi")))
    for candidate in candidates:
        value = reader(candidate)
        if value:
            return value
    return ""


def _media_name_candidates(folder: Path, suffixes: set[str]) -> list[Path]:
    try:
        paths = [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in suffixes]
    except OSError:
        return []
    return sorted(paths, key=lambda path: (path.suffix.lower() not in PREFERRED_MEDIA_NAME_SUFFIXES, path.name.lower()))


def _clean_media_stem(stem: str) -> str:
    text = stem.replace("_", " ").replace(".", " ").strip()
    return " ".join(text.split())


def is_descriptive_game_name(value: str | None) -> bool:
    text = " ".join((value or "").strip().split())
    if not text:
        return False
    if text.isdigit():
        return False
    normalized = re.sub(r"[^a-z0-9]+", "", text.lower())
    if not normalized:
        return False
    if normalized in GENERIC_NAME_TOKENS:
        return False
    if re.fullmatch(r"track\d{1,2}", normalized):
        return False
    if re.fullmatch(r"disc\d{0,2}", normalized) or re.fullmatch(r"disk\d{0,2}", normalized):
        return False
    return True


def is_synthetic_slot_serial(serial: str | None) -> bool:
    return bool(re.fullmatch(r"SLOT\d{1,3}", (serial or "").strip().upper()))


def is_plausible_product_id(serial: str | None) -> bool:
    """False for empty values and for bytes a menu got from a misread header."""
    text = (serial or "").strip()
    return bool(text) and all(0x20 <= ord(char) <= 0x7E for char in text) and any(char.isalnum() for char in text)


def menu_product_id_for_slot(slot: int, raw_product_id: str, disc_product_id: str = "") -> str:
    raw_product_id = (raw_product_id or "").strip()
    disc_product_id = (disc_product_id or "").strip()
    if is_synthetic_slot_serial(raw_product_id) or not is_plausible_product_id(raw_product_id):
        return disc_product_id or f"SLOT{slot:03d}"
    return raw_product_id


def artwork_serial_candidates(slot: int, raw_product_id: str, menu_product_id: str, disc_product_id: str = "") -> list[str]:
    candidates: list[str] = []
    for serial in (
        raw_product_id,
        menu_product_id,
        f"SLOT{slot:03d}" if is_synthetic_slot_serial(raw_product_id) or not is_plausible_product_id(raw_product_id) else "",
        disc_product_id,
    ):
        normalized = _normalize_serial(serial)
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return candidates


def _declared_data_tracks(gdi_path: Path) -> list[str]:
    try:
        lines = gdi_path.read_text(encoding="ascii", errors="replace").splitlines()
    except OSError:
        return []
    tracks: list[str] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 5 and parts[3] == "2048" and parts[4].lower().endswith((".iso", ".bin")):
            tracks.append(parts[4])
    return tracks


def _gdi_data_tracks(folder: Path, gdi_path: Path) -> list[Path]:
    return [folder / name for name in _declared_data_tracks(gdi_path)]


def _ip_bin_field(header: bytes, start: int, end: int) -> str:
    """Printable ASCII field, or "" when the bytes cannot be a real IP.BIN value."""
    raw = header[start:end].rstrip(b"\x00 ")
    if not raw or any(byte < 0x20 or byte > 0x7E for byte in raw):
        return ""
    text = raw.decode("ascii").strip()
    return text if any(char.isalnum() for char in text) else ""


def _read_ip_bin_product(track_path: Path) -> str:
    for header in _ip_bin_headers(track_path):
        if len(header) >= 0x4A:
            value = _ip_bin_field(header, 0x40, 0x4A)
            if value:
                return value.replace("-", "")
    return ""


def _read_ip_bin_internal_name(track_path: Path) -> str:
    for header in _ip_bin_headers(track_path):
        if len(header) >= 0x100:
            value = _ip_bin_field(header, 0x80, 0x100)
            if value:
                return " ".join(value.split())
    return ""


def _ip_bin_headers(track_path: Path) -> tuple[bytes, ...]:
    track_path = Path(track_path)
    try:
        stat = track_path.stat()
    except OSError:
        return ()
    return _ip_bin_headers_cached(str(track_path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=512)
def _ip_bin_headers_cached(path: str, mtime_ns: int, file_size: int) -> tuple[bytes, ...]:
    """Candidate headers, most reliable first.

    The magic string also appears in unrelated data (a CDI's first session can
    hold one with null fields), so callers validate each field and fall back
    to the next candidate instead of trusting the first match.
    """
    del mtime_ns
    headers: list[bytes] = []
    try:
        with Path(path).open("rb") as handle:
            if path.lower().endswith(".cdi"):
                boot = _cdi_boot_header(Path(path), handle)
                if boot:
                    headers.append(boot)
            handle.seek(0)
            data = handle.read(min(max(IP_BIN_HEADER_SIZE, file_size), IP_BIN_SEARCH_LIMIT))
    except OSError:
        return tuple(headers)
    start = data.find(IP_BIN_MAGIC)
    while start >= 0 and len(headers) < IP_BIN_MAX_CANDIDATES:
        headers.append(data[start:start + IP_BIN_HEADER_SIZE])
        start = data.find(IP_BIN_MAGIC, start + 1)
    return tuple(headers)


def _cdi_boot_header(path: Path, handle) -> bytes:
    """A self-boot CDI keeps IP.BIN at the start of the last session's first data track."""
    try:
        inspection = inspect_cdi(path)
    except CDIError:
        return b""
    last_session = max(track.session for track in inspection.tracks)
    for track in inspection.tracks:
        if track.session == last_session and track.mode in (1, 2):
            pregap = track.indices[0] if track.indices else 0
            handle.seek(track.byte_offset + pregap * track.sector_size)
            data = handle.read(2 * track.sector_size)
            start = data.find(IP_BIN_MAGIC)
            return data[start:start + IP_BIN_HEADER_SIZE] if start >= 0 else b""
    return b""


def _normalize_serial(serial: str | None) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "", serial or "")
    return normalized[:10].upper()


def read_name_txt(folder: Path) -> str:
    name_path = folder / "name.txt"
    if not name_path.exists():
        return ""
    try:
        return name_path.read_text(encoding="utf-8-sig", errors="replace").strip().lstrip("\ufeff")
    except OSError:
        return ""


def detect_media_type(folder: Path) -> str:
    if (folder / "disc.gdi").exists():
        return "GDI"
    if (folder / "disc.cdi").exists():
        return "CDI"
    for path in folder.iterdir():
        if path.suffix.lower() == ".gdi":
            return "GDI"
        if path.suffix.lower() == ".cdi":
            return "CDI"
    return ""
