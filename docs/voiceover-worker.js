// Single-thread FFmpeg stays on this device and runs outside the UI thread.
function progress(message) {
  self.postMessage({ type: "status", message });
}

function tempoFilters(ratio) {
  const filters = [];
  // Keep every stage in [0.5,2] for pitch-preserving time stretch.
  while (ratio < 0.5) {
    filters.push("atempo=0.5");
    ratio /= 0.5;
  }
  while (ratio > 2) {
    filters.push("atempo=2");
    ratio /= 2;
  }
  if (Math.abs(ratio - 1) > 1e-8) filters.push("atempo=" + ratio.toFixed(10));
  return filters;
}

self.onmessage = async ({ data }) => {
  try {
    const { takes, fit } = data;
    const chapterSeconds = 150;
    progress("正在加载本地编码器，首次约需下载 31 MB…");
    importScripts("vendor/ffmpeg-core/ffmpeg-core.js");
    const binary = await fetch("vendor/ffmpeg-core/ffmpeg-core.wasm");
    if (!binary.ok) throw Error("编码器加载失败，HTTP " + binary.status);
    const core = await createFFmpegCore({
      wasmBinary: new Uint8Array(await binary.arrayBuffer()),
    });
    const errors = [];
    core.setLogger(({ message }) => {
      errors.push(message);
      if (errors.length > 6) errors.shift();
    });
    function run(args) {
      core.reset();
      if (core.exec("-hide_banner", "-loglevel", "error", ...args) !== 0)
        throw Error(errors.join(" ").slice(-320) || "媒体编码失败");
    }
    const args = [],
      chains = [];
    for (let i = 0; i < takes.length; i++) {
      const take = takes[i],
        file = "voice" + i + ".wav";
      if (!Number.isFinite(take.duration) || take.duration <= 0)
        throw Error("有一段录音缺少有效时长。");
      core.FS.writeFile(file, new Uint8Array(await take.blob.arrayBuffer()));
      args.push("-i", file);
      const speed =
        fit === "stretch"
          ? take.duration / chapterSeconds
          : Math.max(1, take.duration / chapterSeconds);
      const filters = [
        ...tempoFilters(speed),
        "aresample=48000",
        "apad",
        "atrim=end_sample=7200000",
        "asetpts=N/SR/TB",
      ];
      chains.push("[" + i + ":a]" + filters.join(",") + "[p" + i + "]");
    }
    progress("正在对齐四段录音，编码十分钟人声音轨…");
    chains.push("[p0][p1][p2][p3]concat=n=4:v=0:a=1[a]");
    run([
      ...args,
      "-filter_complex",
      chains.join(";"),
      "-map",
      "[a]",
      "-c:a",
      "aac",
      "-b:a",
      "128k",
      "-movflags",
      "+faststart",
      "mix.m4a",
    ]);
    for (let i = 0; i < 4; i++) core.FS.unlink("voice" + i + ".wav");
    progress("正在读取原片并替换旁白…");
    const response = await fetch("presentation.mp4");
    if (!response.ok) throw Error("原片下载失败，HTTP " + response.status);
    core.FS.writeFile("film.mp4", new Uint8Array(await response.arrayBuffer()));
    run([
      "-i",
      "film.mp4",
      "-i",
      "mix.m4a",
      "-map",
      "0:v:0",
      "-map",
      "1:a:0",
      "-c",
      "copy",
      "-metadata:s:a:0",
      "language=eng",
      "-movflags",
      "+faststart",
      "team.mp4",
    ]);
    const video = core.FS.readFile("team.mp4");
    const audio = core.FS.readFile("mix.m4a");
    self.postMessage({ type: "done", video, audio }, [
      video.buffer,
      audio.buffer,
    ]);
  } catch (error) {
    self.postMessage({
      type: "error",
      message: String(error.message || error),
    });
  }
};
