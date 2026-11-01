"""Developer diagnostic: detect bundled PE imports absent from bundled exports."""
from pathlib import Path
from collections import deque
import pefile

root = Path(__file__).resolve().parents[1] / "dist" / "v1.2" / "VideoDuplicateFinder" / "_internal"
files = {p.name.lower(): p for p in root.rglob("*") if p.suffix.lower() in (".dll", ".pyd")}
pending = deque(["qtwidgets.pyd"])
visited = set()
exports = {}
while pending:
    name = pending.popleft()
    if name in visited or name not in files:
        continue
    visited.add(name)
    pe = pefile.PE(str(files[name]), fast_load=True, max_symbol_exports=100000)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        dependency = entry.dll.decode().lower()
        if dependency not in files:
            continue
        pending.append(dependency)
        if dependency not in exports:
            other = pefile.PE(str(files[dependency]), fast_load=True, max_symbol_exports=100000)
            other.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
            exports[dependency] = {s.name for s in getattr(getattr(other, "DIRECTORY_ENTRY_EXPORT", None), "symbols", [])}
            other.close()
        missing = [i.name.decode() for i in entry.imports if i.name and i.name not in exports[dependency]]
        if missing:
            print(f"{name} -> {dependency}: {missing[:20]}")
    pe.close()
print(f"PE files inspected: {len(visited)} archivos PE")
