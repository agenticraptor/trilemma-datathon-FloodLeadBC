# uPlot (vendored)

- Library: uPlot, a small, fast charting library for time series.
- Version: **1.6.32** (pinned; the latest 1.6.x on the npm registry on 2026-10-08).
- Source: npm registry tarball <https://registry.npmjs.org/uplot/-/uplot-1.6.32.tgz>
  (tarball sha1 `c800a63b432bad692d6d746f44f0882aa73a49ae`, as published in the registry's `dist.shasum`).
  Upstream project: <https://github.com/leeoniya/uPlot>.
- Licence: MIT, see `LICENSE` (copied unchanged from the tarball).
- Files copied unchanged from the tarball's `package/` directory (nothing else from the tarball is used):

| File | From | sha256 |
|---|---|---|
| `uPlot.iife.min.js` | `dist/uPlot.iife.min.js` | `19c8d4c6ad88929a79f4ae49d6f7161566dfd0ba3d15cc495e974f787eb78f1f` |
| `uPlot.min.css` | `dist/uPlot.min.css` | `df630c6a8d6f8eeaff264b50f73ce5b114f646ffd9a0bb74f049b0a00135fa04` |
| `LICENSE` | `LICENSE` | `8f989229699b4fe2f1a0432d0e9edc338a8a911e250e2d1b01ecd770a5f5b1bd` |

Verify: `cd web/vendor/uplot && sha256sum uPlot.iife.min.js uPlot.min.css LICENSE`.

To upgrade: download the new tarball into an empty directory, copy the same three files, update this table.
