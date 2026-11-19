// Normalizing imports to a mono WAV also fixes missing durations in MediaRecorder WebM files.
const sampleRate = 24000;

export async function prepareTake(file, name) {
  if (!file?.size) throw Error("没有收到音频。请检查文件或麦克风后重新录制。");
  const decoder = new OfflineAudioContext(1, 1, sampleRate);
  let audio;
  try {
    audio = await decoder.decodeAudioData(await file.arrayBuffer());
  } catch {
    throw Error("浏览器无法解码此音频。可先转换为 WAV、MP3 或 M4A 再导入。");
  }
  if (!audio.length) throw Error("录音没有可播放的音频。");
  const channels = Array.from({ length: audio.numberOfChannels }, (_, i) =>
    audio.getChannelData(i),
  );
  const data = new ArrayBuffer(44 + 2 * audio.length);
  const view = new DataView(data);
  function ascii(at, text) {
    for (let i = 0; i < text.length; i++)
      view.setUint8(at + i, text.charCodeAt(i));
  }
  ascii(0, "RIFF");
  view.setUint32(4, 36 + audio.length * 2, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, audio.sampleRate, true);
  view.setUint32(28, audio.sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, "data");
  view.setUint32(40, 2 * audio.length, true);
  let peak = 0;
  for (let i = 0; i < audio.length; i++) {
    let sum = 0;
    for (const channel of channels) sum += channel[i];
    const value = Math.max(-1, Math.min(1, sum / channels.length));
    peak = Math.max(peak, Math.abs(value));
    view.setInt16(
      44 + 2 * i,
      Math.round(value * (value < 0 ? 32768 : 32767)),
      true,
    );
  }
  return {
    blob: new Blob([data], { type: "audio/wav" }),
    name,
    duration: audio.duration,
    peak,
  };
}

export function openDrafts() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open("hypospace-four-voice-drafts-v1", 1);
    req.onupgradeneeded = () => req.result.createObjectStore("takes");
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
    req.onblocked = () => reject(Error("本地草稿正被另一个页面使用"));
  });
}

export function draftOp(db, mode, action) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction("takes", mode);
    const request = action(tx.objectStore("takes"));
    tx.oncomplete = () => resolve(request.result);
    tx.onabort = () => reject(tx.error || Error("浏览器草稿保存失败"));
    tx.onerror = () => reject(tx.error);
  });
}
