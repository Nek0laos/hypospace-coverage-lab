import { prepareTake, openDrafts, draftOp } from "./voiceover-audio.js";

const $ = (id) => document.getElementById(id);
const takes = Array(4).fill(null);
let chapters = [],
  role = 0,
  mode = "loading",
  db = null;
let recorder = null,
  stream = null,
  timer = null,
  clockStart = 0;
let sampleURL = null,
  videoURL = null,
  audioURL = null;
const hasMic = !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
function time(value) {
  const n = Math.max(0, Math.floor(value));
  return (
    String(Math.floor(n / 60)).padStart(2, "0") +
    ":" +
    String(n % 60).padStart(2, "0")
  );
}
function status(message, error = false, el = $("status")) {
  el.textContent = message;
  el.dataset.error = String(error);
}
function modeTo(value) {
  mode = value;
  controls();
}
function controls() {
  const idle = mode === "idle";
  const recording = mode === "recording" || mode === "count-record";
  const rehearsal = mode === "rehearsing" || mode === "count-rehearse";
  $("record").textContent = recording
    ? mode === "count-record"
      ? "取消倒计时"
      : "结束并保存"
    : "开始录音";
  $("record").disabled = !(hasMic && (idle || recording));
  $("rehearse").textContent = rehearsal ? "停止排练" : "跟读排练";
  $("rehearse").disabled = !(idle || rehearsal);
  for (const name of ["import", "remove"]) $(name).disabled = !idle;
  for (const [i, btn] of Array.from($("roles").children).entries()) {
    btn.disabled = !idle;
    btn.setAttribute("aria-pressed", String(role === i));
    btn.lastElementChild.textContent = takes[i]
      ? "已就绪 · " + time(takes[i].duration)
      : "待录制";
  }
  const count = takes.filter(Boolean).length;
  $("ready").textContent = "已就绪 " + count + " / 4";
  $("export").disabled = !idle || count !== 4;
  for (const option of document.querySelectorAll("[name=fit]"))
    option.disabled = !idle;
}
function clearResult() {
  if (videoURL) {
    $("preview").pause();
    $("preview").removeAttribute("src");
    $("preview").load();
    URL.revokeObjectURL(videoURL);
    URL.revokeObjectURL(audioURL);
    videoURL = audioURL = null;
    $("result").hidden = true;
  }
  status("", false, $("export-status"));
}
function renderTake() {
  $("audition").pause();
  $("audition").removeAttribute("src");
  $("audition").load();
  if (sampleURL) URL.revokeObjectURL(sampleURL);
  sampleURL = null;
  const take = takes[role];
  $("take").hidden = !take;
  if (take) {
    sampleURL = URL.createObjectURL(take.blob);
    $("audition").src = sampleURL;
    $("save-take").href = sampleURL;
    $("save-take").download = "speaker-" + (role + 1) + ".wav";
    $("take-name").textContent = take.name;
    const gap = take.duration - 150;
    const timing =
      Math.abs(gap) < 0.05
        ? "已对齐章节"
        : gap > 0
          ? "比章节长 " + gap.toFixed(1) + " 秒"
          : "比章节短 " + (-gap).toFixed(1) + " 秒";
    $("take-length").textContent =
      take.duration.toFixed(1) +
      " 秒 · " +
      timing +
      (take.peak < 0.001 ? " · 音量接近静音，请试听" : "");
  }
}
function drawCue(seconds) {
  const cues = chapters[role].cues;
  const i = cues.findIndex((c) => c[1] > seconds);
  $("timer").textContent = time(seconds) + " / 02:30";
  if (i < 0) {
    $("cue").textContent = "本章台本已读完。";
    $("next-cue").textContent =
      mode === "recording" ? "读完后点击「结束并保存」。" : "";
    return;
  }
  $("cue").textContent = cues[i][2];
  $("next-cue").textContent = cues[i + 1] ? "Next · " + cues[i + 1][2] : "";
}
function showRole(i) {
  role = i;
  const ch = chapters[i];
  $("chapter-range").textContent =
    "讲述者 " +
    (i + 1) +
    "  /  影片 " +
    time(ch.start) +
    " – " +
    time(ch.start + 150);
  $("chapter-title").textContent = ch.zh + " · " + ch.title;
  $("script-download").href = "voice-scripts/" + ch.file;
  $("script-download").download = ch.file;
  const sections = ch.scenes.map((scene) => {
    const block = document.createElement("section"),
      title = document.createElement("h3"),
      stamp = document.createElement("span"),
      p = document.createElement("p");
    stamp.textContent = time(scene.at);
    title.append(stamp, scene.title);
    title.lang = "en";
    p.lang = "en";
    p.textContent = scene.text;
    block.append(title, p);
    return block;
  });
  $("scenes").replaceChildren(...sections);
  $("scenes").scrollTop = 0;
  $("cue-label").textContent = "逐句提词 · 章节内时间";
  drawCue(0);
  renderTake();
  controls();
  status(
    hasMic
      ? ""
      : "此浏览器可导入录音。如需现场录音，请在支持麦克风的 HTTPS 或 localhost 页面打开。",
  );
}
async function storeTake(index, take) {
  takes[index] = take;
  clearResult();
  if (!db) return false;
  try {
    await draftOp(db, "readwrite", (store) =>
      take ? store.put(take, index) : store.delete(index),
    );
    return true;
  } catch {
    return false;
  }
}
async function accept(blob, name, index) {
  modeTo("processing");
  status("正在读取音频…");
  try {
    const take = await prepareTake(blob, name);
    const stored = await storeTake(index, take);
    renderTake();
    status(
      stored
        ? "本段已保存在此浏览器。可试听、重录或下载 WAV。"
        : "本段可用。浏览器草稿存储不可用，请下载 WAV 备份。",
    );
  } catch (e) {
    status(e.message, true);
  } finally {
    modeTo("idle");
  }
}
function releaseMic() {
  if (stream) stream.getTracks().forEach((t) => t.stop());
  stream = null;
}
function stopTimer() {
  clearInterval(timer);
  timer = null;
}
function finish() {
  const previous = mode;
  stopTimer();
  if (previous === "recording" && recorder?.state === "recording") {
    modeTo("processing");
    recorder.stop();
    return;
  }
  releaseMic();
  recorder = null;
  modeTo("idle");
  $("cue-label").textContent = "逐句提词 · 章节内时间";
  drawCue(0);
  status(previous.startsWith("count") ? "已取消准备。" : "排练结束。");
}
async function start(record) {
  if (mode !== "idle") {
    finish();
    return;
  }
  $("audition").pause();
  $("preview").pause();
  const idx = role;
  modeTo("arming");
  try {
    if (record) {
      status("正在请求麦克风…");
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const type = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"].find(
        (t) => MediaRecorder.isTypeSupported(t),
      );
      recorder = new MediaRecorder(stream, type ? { mimeType: type } : {});
      const current = recorder,
        chunks = [];
      let failed = false;
      current.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      current.onerror = (e) => {
        failed = true;
        stopTimer();
        releaseMic();
        recorder = null;
        modeTo("idle");
        status(
          e.error?.message || "麦克风录制中断。请重新录制或导入音频。",
          true,
        );
      };
      current.onstop = () => {
        if (failed) return;
        stopTimer();
        releaseMic();
        recorder = null;
        $("cue-label").textContent = "逐句提词 · 章节内时间";
        drawCue(0);
        accept(
          new Blob(chunks, { type: current.mimeType }),
          "讲述者 " + (idx + 1) + " · 麦克风录音",
          idx,
        );
      };
    }
    modeTo(record ? "count-record" : "count-rehearse");
    const readyAt = performance.now() + 3000;
    function tick() {
      const now = performance.now();
      if (mode.startsWith("count")) {
        const count = Math.ceil((readyAt - now) / 1000);
        if (count > 0) {
          $("cue-label").textContent = "准备 · " + count;
          status(count + " 秒后" + (record ? "开始录音" : "开始排练"));
          return;
        }
        if (record) recorder.start(1000);
        modeTo(record ? "recording" : "rehearsing");
        clockStart = now;
        $("cue-label").textContent = record ? "● 正在录音" : "跟读排练";
        status(record ? "读完后点击「结束并保存」。" : "排练只显示提词。");
      }
      const elapsed = (now - clockStart) / 1000;
      if (mode === "rehearsing" && elapsed >= 150) {
        finish();
        return;
      }
      drawCue(elapsed);
    }
    tick();
    timer = setInterval(() => {
      try {
        tick();
      } catch (e) {
        stopTimer();
        releaseMic();
        modeTo("idle");
        status(e.message, true);
      }
    }, 100);
  } catch (e) {
    stopTimer();
    releaseMic();
    recorder = null;
    modeTo("idle");
    status(
      e.name === "NotAllowedError"
        ? "未获得麦克风权限。可以重新授权，或选择「导入音频」。"
        : "录音未开始：" + e.message,
      true,
    );
  }
}
async function makeMovie() {
  if (mode !== "idle" || takes.some((t) => !t)) return;
  clearResult();
  $("audition").pause();
  modeTo("exporting");
  const message = $("export-status");
  status("正在启动合成…", false, message);
  let worker;
  function finishExport(error) {
    worker?.terminate();
    modeTo("idle");
    if (error)
      status(
        "合成失败：" + error + "。四段录音仍可试听和重新导出。",
        true,
        message,
      );
  }
  try {
    worker = new Worker("voiceover-worker.js");
    worker.onerror = (e) => finishExport(e.message);
    worker.onmessage = ({ data }) => {
      if (data.type === "status") {
        status(data.message, false, message);
        return;
      }
      if (data.type === "error") {
        finishExport(data.message);
        return;
      }
      if (data.type === "done") {
        videoURL = URL.createObjectURL(
          new Blob([data.video], { type: "video/mp4" }),
        );
        audioURL = URL.createObjectURL(
          new Blob([data.audio], { type: "audio/mp4" }),
        );
        $("save-video").href = videoURL;
        $("save-audio").href = audioURL;
        $("preview").src = videoURL;
        $("result").hidden = false;
        status(
          "合成完成。可预览并下载 10:00 的配音视频或单独音轨。",
          false,
          message,
        );
        finishExport();
      }
    };
    worker.postMessage({
      takes: takes.map(({ blob, duration }) => ({ blob, duration })),
      fit: document.querySelector("[name=fit]:checked").value,
    });
  } catch (e) {
    finishExport(e.message);
  }
}
async function init() {
  const response = await fetch("voice-scripts/chapters.json");
  if (!response.ok) throw Error("英文台本加载失败，请刷新。");
  chapters = await response.json();
  try {
    db = await openDrafts();
    await Promise.all(
      chapters.map(async (_, i) => {
        takes[i] =
          (await draftOp(db, "readonly", (store) => store.get(i))) || null;
      }),
    );
  } catch {
    db = null;
  }
  chapters.forEach((ch, i) => {
    const button = document.createElement("button"),
      name = document.createElement("strong"),
      state = document.createElement("span");
    name.textContent = "讲述者 " + (i + 1) + " · " + ch.zh;
    button.append(name, state);
    button.onclick = () => showRole(i);
    $("roles").append(button);
  });
  const requested = Number(new URLSearchParams(location.search).get("speaker"));
  mode = "idle";
  showRole(
    Number.isInteger(requested) && requested >= 1 && requested <= 4
      ? requested - 1
      : 0,
  );
  $("record").onclick = () => start(true);
  $("rehearse").onclick = () => start(false);
  $("import").onclick = () => $("file").click();
  $("file").onchange = () => {
    const file = $("file").files[0];
    $("file").value = "";
    if (file) accept(file, file.name, role);
  };
  $("remove").onclick = async () => {
    modeTo("processing");
    const saved = await storeTake(role, null);
    renderTake();
    modeTo("idle");
    status(
      saved ? "已移除本段。" : "已移除当前页面中的录音；浏览器未确认草稿删除。",
    );
  };
  for (const option of document.querySelectorAll("[name=fit]"))
    option.onchange = clearResult;
  $("export").onclick = makeMovie;
}
window.addEventListener("pagehide", releaseMic);
init().catch((e) => status(e.message, true));
