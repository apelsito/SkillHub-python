"""Build the bundle.zip that the download endpoint streams.

Creates a deterministic zip (sorted paths, fixed mtime) so repeated
publishes of the same files produce bit-identical bundles — useful for
download integrity checks and the optional SHA-256-of-bundle column.
"""

from __future__ import annotations

import io
import zipfile

from skillhub_api.services.skills.package import ExtractedFile

_DETERMINISTIC_MTIME = (1980, 1, 1, 0, 0, 0)


def build_bundle(files: list[ExtractedFile]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(files, key=lambda x: x.path):
            info = zipfile.ZipInfo(f.path, date_time=_DETERMINISTIC_MTIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, f.data)
    return buf.getvalue()
