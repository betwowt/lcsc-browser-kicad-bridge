# Third-party notices

This repository is a browser front end and loopback service around existing open-source conversion
code. The converter sources are pulled in as a pinned git submodule and are not copied or modified.

## LCSC_Kicad_import

- Project: <https://github.com/silencewwh/LCSC_Kicad_import>
- Location: `vendor/LCSC_Kicad_import` (submodule, revision pinned by this repository)
- License: GNU General Public License, version 3 (`vendor/LCSC_Kicad_import/LICENSE.txt`)
- Usage: `plugins/impart_easyeda.py`, `plugins/lcsc_project_import.py`,
  `plugins/lcsc_download_cache.py` and `plugins/lcsc_model_download.py` perform the download,
  conversion, project staging and library-table registration.
- The portable executable bundles these modules, so the GPL-3.0 attribution applies to the binaries.

## EasyEDA to KiCad converter

- Original project: <https://github.com/uPesy/easyeda2kicad.py>
- Original author: uPesy and contributors.
- Bundled mirror: <https://github.com/Steffen-W/easyeda2kicad.py>, included as a submodule of
  `LCSC_Kicad_import`; the complete license text is at
  `vendor/LCSC_Kicad_import/plugins/easyeda2kicad/LICENSE`.
- License: GNU Affero General Public License, version 3.
- Usage: conversion of EasyEDA symbols, footprints and 3D models to KiCad formats. Because the
  executable embeds this code, distributing the executable also distributes AGPL-3.0 code; the
  corresponding source is this repository plus its submodule at the released tag.

## Import-LIB-KiCad-Plugin

- Project: <https://github.com/Steffen-W/Import-LIB-KiCad-Plugin>
- Original author/maintainer: Steffen Wittemeier and contributors.
- License: GNU General Public License, version 3.
- Usage: `LCSC_Kicad_import` derived its EasyEDA importer adapter from this project.

## This repository

- Browser extension (`extension/`), loopback service (`server/`), packaging and release tooling.
- License: GNU Affero General Public License, version 3 (`LICENSE.txt`), required because the
  distributed binaries combine the AGPL-3.0 converter above.
