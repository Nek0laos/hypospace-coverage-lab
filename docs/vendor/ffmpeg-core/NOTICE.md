# FFmpeg WebAssembly core

The files `ffmpeg-core.js` and `ffmpeg-core.wasm` are the unmodified single-thread UMD build from the official npm release of `@ffmpeg/core` 0.12.10. The upstream package declares GPL-2.0-or-later. The license text is included in [COPYING.GPLv2](COPYING.GPLv2).

[Upstream release package](https://registry.npmjs.org/@ffmpeg/core/-/core-0.12.10.tgz) · [Corresponding source and build scripts, including the component revisions](https://github.com/ffmpegwasm/ffmpeg.wasm/tree/71aa99d37c02a7b4c435275ca9ef50e612f6efa1) · [Upstream build instructions](https://ffmpegwasm.netlify.app/docs/contribution/core/)

The studio loads the core on export, encodes the four audio chapters as AAC and copies the original H.264 video stream.

