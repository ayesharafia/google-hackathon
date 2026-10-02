# Browser dependency record

Task 1.5 uses native HTML, CSS and JavaScript only. No third-party browser
library is loaded, so there is no library version or checksum to record yet.
The 3D viewer is not delivered by this shell; three.js must be vendored and
recorded by exact version and SHA-256 when Task 3.5 introduces it. [plan §6.0]

Display typography uses locally installed Optima/Candara with sans-serif
fallback. No licensed font file is redistributed. Body uses the OS text face.
[ASSUMPTION: native instrument-desk typography]

## Results viewer dependency

Three.js 0.180.0, MIT. Source: https://registry.npmjs.org/three/-/three-0.180.0.tgz
Tarball npm SHA-512 integrity checked before extraction. Only the two ES modules,
OrbitControls and original license are redistributed; no package scripts execute.

| File | SHA-256 |
|---|---|
| three.module.min.js | e2b5ee6bccd38fd6d8a2428546b83c5f2426d84b152ef82be8055556e3b40eb6 |
| three.core.min.js | 61ba0df005b05991361d040d8ff670e1aadfd0ce7aeebd1fdb0725957a8957de |
| OrbitControls.js | b97879c748170baadeb3fb84cea1ffdf4674e283dc06042f34e2acb95a76042c |
| THREE-LICENSE | bfe119ea4fd413f5f7ca3fcd63adb0c4a073ed39daa2fe7d3e6b769e21272601 |
| STLLoader.js | 023ed97f848b633d8bcd53d4db3b996d29d0c644088700691297c552257d480b |
