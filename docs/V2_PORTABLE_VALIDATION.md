# V2 portable startup evidence

Local development build: `2.0.0.dev5`, Windows 11, Python 3.12.10,
PySide6 6.11.2, PyInstaller 6.22.3.

Build completed on 2026-10-09 after the CDI structural validator and read-only agent-query
corrections. The executable self-test exited with code 0 through native Windows
Qt at system DPI, using an isolated local destination, and reported:

```json
{
  "version": "2.0.0.dev5",
  "startup": true,
  "icons": true,
  "errors": [],
  "sd_scanned": false,
  "network_requested": false
}
```

Archive: `OpenMenuGDEMUManager-2.0.0-dev5-portable-windows.zip`

SHA256: `2B042924C6BD4067E7A220A5D114E7B40940A732FC51F5F2DC1560CB737905B5`

Executable SHA256: `1e7f5f8a6f388bd203b1e69184df430aeb6887c2c08b3f02b6eebc9f715b0ab7`

ZIP CRC integrity passed. The archived executable's SHA256 matches the built
executable. The archive contains no runtime data, virtual environment or local
prototype artifacts. Source startup also passed from the same environment.
The self-test uses an explicit local root and does not discover physical storage.
This package supersedes dev4 and includes supported CDI descriptor/track-bound
validation. The source installation also provides a read-only JSON CLI; this
GUI portable has no separate CLI executable and no MCP server. Older packages
remain historical local artifacts.

These are local packaging/startup checks, separate from the independent
reviewer's approval of the corrected code and dialog design. They do not certify
a clean Windows VM, payload integrity, unsupported CDI variants or Dreamcast
game boot. Those release gates remain pending; follow
[V2_EXTERNAL_ACCEPTANCE.md](V2_EXTERNAL_ACCEPTANCE.md). Public-provider search/download/decoding was checked
separately; private/credentialed provider checks remain pending.
See [provider evidence](V2_PROVIDER_VALIDATION.md),
[automated regression evidence](V2_VALIDATION.md) and
[independent audit](V2_INDEPENDENT_AUDIT.md).

## dev6 logging correction build (2026-10-10)

This local build supersedes dev5 with session-isolated rotating diagnostics,
early startup capture and V2 origin tracebacks. Source and portable self-tests
returned dev6/startup=true/icons=true/errors=[] using explicit local roots;
the portable used native Windows Qt at system DPI. Its windowed process produced
the expected version/platform/frozen/Qt session log without a console. Self-test
mode bypasses automatic scanning/update timers; this is local startup evidence,
not a packet capture or physical-storage test.

Archive: `OpenMenuGDEMUManager-2.0.0-dev6-portable-windows.zip`

SHA256: `afc6058306f1c3ccf7975445ba9f5e3c1e7da810aa969deb185beaf0556222bd`

Executable SHA256: `23362d7ddbed78a8048adf16502f5ac98cef1a345e6f8cff23f8c493950be1c6`

ZIP CRC passed (474 entries); archived executable matches the tested executable.
Packaged logger/startup/changed GUI adapters/workers/metadata match final source:
bytecode/constants/code attributes compared recursively, excluding build-dependent
filenames. No runtime data, logs, virtual environment or local-artifacts are bundled.
The previous portable and its local data were preserved before rebuilding.
No GitHub release or public binary upload was made.

Clean-Windows, private-provider and physical SD/Dreamcast gates remain pending.
The GUI portable has no separate agent CLI executable or MCP server.

## dev7 illustrated preparation and backup (2026-10-10)

Local native Windows build: 2.0.0.dev7, Python 3.12.10, PySide6 6.11.2,
PyInstaller 6.22.3. Source and portable self-tests both returned version dev7,
startup=true, icons=true, errors=[], sd_scanned=false and network_requested=false.
They used explicit synthetic/local destinations and isolated runtime/document
folders. This is startup evidence, not a network capture or hardware validation.

Archive: `OpenMenuGDEMUManager-2.0.0-dev7-portable-windows.zip`

SHA256: `0e8de2e99e6a07e981d0e1e595c6105b2edec27d82c90d41a49fad14682f21fd`

Executable SHA256: `5dd55bf7925a026809671e17fe93afc3739c3b2d91f4ebd38059f5744704a42b`

ZIP CRC passed (475 entries). Archived executable matches the tested executable;
packaged artwork, tokens and EN/ES catalogs match final source bytes. Twelve
changed application modules match final source code attributes/constants recursively,
excluding build-dependent filenames. No runtime data, local-artifacts or virtual
environment are bundled. The previous portable, including its data, was preserved
before building. No public binary upload or release was made.

This build replaces setup/backup presentation with shared native components and
an illustrative SVG, preserving original storage/copy/upgrade services. Real copy
progress counts files; there is no invented byte progress, ETA or unsafe cancellation.
Independent source/visual review and full/DPI regression results are recorded separately.
Clean Windows VM and physical SD/Dreamcast launch gates remain pending.
