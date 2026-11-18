"use strict";
const $ = (id) => document.getElementById(id);
const colors = {
  model: "#ac452b",
  stratified: "#745793",
  marginal: "#336a88",
  prefix: "#007650",
  uniform: "#6c725f",
};
const order = ["prefix", "model", "stratified", "marginal", "uniform"];
const visible = new Set(order);
const percent = (n) => (n * 100).toFixed(1) + "%";
const points = (n) => (n >= 0 ? "+" : "") + (n * 100).toFixed(1);
const svgNS = "http://www.w3.org/2000/svg";
let data,
  ablations,
  level,
  mask,
  method = "prefix",
  step = 1,
  rotation = 0,
  timer = null;
function option(value, label) {
  return new Option(label, value);
}
function svgNode(kind, attrs, txt) {
  const node = document.createElementNS(svgNS, kind);
  Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
  if (txt !== undefined) node.textContent = txt;
  return node;
}
function chart() {
  const area = $("chart"),
    box = area.getBoundingClientRect();
  const w = Math.max(280, box.width),
    h = box.height,
    x0 = 41,
    y0 = 17,
    x1 = w - 12,
    y1 = h - 34;
  const series = data.levels[level].curves,
    n = series.prefix.length;
  const x = (t) => x0 + (t / n) * (x1 - x0),
    y = (v) => y1 - v * (y1 - y0);
  const svg = svgNode("svg", {
    viewBox: [0, 0, w, h].join(" "),
    role: "img",
    "aria-label": "Average recovery by number of sampled structures",
  });
  const text = (x, y, content, align = "start") =>
    svg.append(
      svgNode(
        "text",
        {
          x,
          y,
          "text-anchor": align,
          fill: "#586962",
          "font-size": 10,
          "font-family": "Consolas, monospace",
        },
        content,
      ),
    );
  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    svg.append(
      svgNode("line", {
        x1: x0,
        x2: x1,
        y1: y(v),
        y2: y(v),
        stroke: "#dce1d7",
        "stroke-dasharray": "3 4",
      }),
    );
    text(x0 - 6, y(v) + 4, Math.round(v * 100) + "%", "end");
  }
  const ticks = Array.from(
    new Set([0, 1, Math.round(n / 3), Math.round((2 * n) / 3), n]),
  );
  for (const t of ticks) text(x(t), y1 + 15, t, "middle");
  text((x0 + x1) / 2, h - 2, "PROPOSALS", "middle");
  for (const key of [...order].reverse()) {
    if (!visible.has(key)) continue;
    const coords = [
      [x(0), y(0)],
      ...series[key].map((v, i) => [x(i + 1), y(v)]),
    ];
    svg.append(
      svgNode("polyline", {
        points: coords.map((p) => p.join(",")).join(" "),
        fill: "none",
        stroke: colors[key],
        "stroke-width": key === "prefix" ? 3.5 : 2.1,
        "stroke-linejoin": "round",
        "stroke-dasharray": key === "uniform" ? "4 4" : "none",
      }),
    );
    svg.append(
      svgNode("circle", {
        cx: x(n),
        cy: y(series[key][n - 1]),
        r: 3.2,
        fill: colors[key],
      }),
    );
  }
  area.replaceChildren(svg);
  const tip = document.createElement("div");
  tip.className = "tooltip";
  tip.hidden = true;
  area.append(tip);
  svg.onpointermove = (e) => {
    const pos = e.clientX - area.getBoundingClientRect().left;
    const t = Math.max(
      1,
      Math.min(n, Math.round(((pos - x0) * n) / (x1 - x0))),
    );
    tip.textContent =
      "Draw " +
      t +
      "\n" +
      order
        .filter((k) => visible.has(k))
        .map((k) => data.labels[k] + "  " + percent(series[k][t - 1]))
        .join("\n");
    tip.style.left = Math.max(3, Math.min(w - 167, pos + 7)) + "px";
    tip.style.top = "14px";
    tip.hidden = false;
  };
  svg.onpointerleave = () => (tip.hidden = true);
}
function voxel(heights) {
  const canvas = $("voxel"),
    b = canvas.getBoundingClientRect(),
    dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.round(b.width * dpr);
  canvas.height = Math.round(b.height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  const s = Math.min(b.width / 9, b.height / 5.9),
    center = b.width / 2,
    floor = b.height * 0.56;
  const project = (x, y, z) => [
    center + (x - y) * s,
    floor + (x + y - 3) * s * 0.46 - z * s * 0.82,
  ];
  function face(corners, fill, stroke) {
    ctx.beginPath();
    corners
      .map((v) => project(...v))
      .forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 1;
    ctx.stroke();
  }
  // Move the floor down to reserve space for three visible cube layers.
  ctx.translate(0, s * 0.82);
  const blocks = [];
  let idx = 0;
  for (let p = 0; p < 9; p++) {
    let x = p % 3,
      y = Math.floor(p / 3);
    for (let r = 0; r < rotation; r++) [x, y] = [2 - y, x];
    const h = mask[p] === "1" ? Number(heights[idx++]) : 0;
    face(
      [
        [x, y, 0],
        [x + 1, y, 0],
        [x + 1, y + 1, 0],
        [x, y + 1, 0],
      ],
      h ? "#c7d3ae" : "#e3e8d7",
      "#aebc9c",
    );
    if (h) blocks.push({ x, y, h });
  }
  blocks.sort((a, b) => a.x + a.y - (b.x + b.y) || a.x - b.x);
  blocks.forEach(({ x, y, h }) => {
    for (let z = 0; z < h; z++) {
      face(
        [
          [x, y + 1, z],
          [x + 1, y + 1, z],
          [x + 1, y + 1, z + 1],
          [x, y + 1, z + 1],
        ],
        "#70a78a",
        "#356c51",
      );
      face(
        [
          [x + 1, y, z],
          [x + 1, y + 1, z],
          [x + 1, y + 1, z + 1],
          [x + 1, y, z + 1],
        ],
        "#49816a",
        "#356c51",
      );
      face(
        [
          [x, y, z + 1],
          [x + 1, y, z + 1],
          [x + 1, y + 1, z + 1],
          [x, y + 1, z + 1],
        ],
        "#bfdbad",
        "#356c51",
      );
    }
  });
  canvas.setAttribute(
    "aria-label",
    "Stack heights " +
      heights.split("").join(", ") +
      " in row-major order on footprint " +
      mask,
  );
}
function stop() {
  clearInterval(timer);
  timer = null;
  $("play").textContent = "▶";
  $("play").setAttribute("aria-label", "Play proposals");
}
function draw() {
  const stream = data.examples[mask][method],
    current = stream[step - 1],
    seen = new Set(stream.slice(0, step));
  $("step").max = stream.length;
  $("step").value = step;
  $("counter").value = step + " / " + stream.length;
  $("novelty").textContent = stream.slice(0, step - 1).includes(current)
    ? "Repeat"
    : "New structure";
  $("draw-info").textContent =
    "Heights [" +
    current.split("").join(", ") +
    "]  ·  " +
    seen.size +
    "/" +
    data.levels[level].solutions +
    " recovered";
  $("footprint").replaceChildren(
    ...mask.split("").map((bit) => {
      let cell = document.createElement("i");
      cell.className = "cell" + (bit === "1" ? " occupied" : "");
      return cell;
    }),
  );
  voxel(current);
}
function update() {
  const info = data.levels[level],
    m = info.metrics,
    contrast = info.contrasts.model;
  $("recovery").textContent = percent(m.prefix.recovery);
  $("baseline").textContent = percent(m.model.recovery);
  $("gain").textContent = points(contrast.mean) + " pp";
  $("budget").textContent = info.n;
  $("play").disabled = info.n < 2;
  $("interval").textContent =
    "Paired 95% bootstrap interval for the gain: " +
    points(contrast.ci95[0]) +
    " to " +
    points(contrast.ci95[1]) +
    " pp.";
  $("design").textContent =
    data.manifest.model.name +
    " · " +
    info.masks +
    " footprints · " +
    data.manifest.seeds.length +
    " paired seeds. Each footprint admits " +
    info.solutions +
    " legal structures. Replay shows seed " +
    data.manifest.seeds[0] +
    ".";
  const masks = Object.keys(data.examples)
    .filter((m) => m.split("1").length - 1 === Number(level))
    .sort();
  if (!masks.includes(mask)) mask = masks[Math.floor(masks.length / 2)];
  $("mask").replaceChildren(
    ...masks.map((m) => option(m, m.match(/.../g).join(" / "))),
  );
  $("mask").value = mask;
  $("scores").replaceChildren(
    ...order.map((k) => {
      const tr = document.createElement("tr");
      if (k === "prefix") tr.className = "focus";
      [
        data.labels[k],
        ...["validity", "uniqueness", "recovery"].map((metric) =>
          percent(m[k][metric]),
        ),
      ].forEach((v) => {
        const td = document.createElement("td");
        td.textContent = v;
        tr.append(td);
      });
      return tr;
    }),
  );
  chart();
  draw();
  if (ablations) {
    const variants = [
      ["prefix", "Qwen", "Model spread"],
      ["fixed_scale", "Qwen", "Fixed at 1"],
      ["flat_logits", "Uniform", "Fixed at 1"],
      ["flat_with_model_scale", "Uniform", "Model spread"],
    ];
    $("ablation").hidden = false;
    $("ablation-scores").replaceChildren(
      ...variants.map(([key, preference, scale]) => {
        const tr = document.createElement("tr");
        for (const item of [
          preference,
          scale,
          percent(ablations.levels[level][key].recovery),
        ]) {
          const td = document.createElement("td");
          td.textContent = item;
          tr.append(td);
        }
        return tr;
      }),
    );
  }
}
async function init() {
  const response = await fetch("run.json");
  if (!response.ok)
    throw Error("Experiment data returned HTTP " + response.status);
  data = await response.json();
  $("status").hidden = true;
  $("report").hidden = false;
  const params = new URLSearchParams(location.search),
    levels = Object.keys(data.levels);
  level = levels.includes(params.get("level"))
    ? params.get("level")
    : levels[levels.length - 1];
  mask = params.get("mask");
  method = order.includes(params.get("method"))
    ? params.get("method")
    : "prefix";
  const requested = Number(params.get("step"));
  step =
    Number.isInteger(requested) && requested >= 1
      ? Math.min(requested, data.levels[level].n)
      : 1;
  $("level").replaceChildren(
    ...levels.map((v) => option(v, v + " column" + (v === "1" ? "" : "s"))),
  );
  $("level").disabled = false;
  $("level").value = level;
  $("method-select").replaceChildren(
    ...order.map((k) => option(k, data.labels[k])),
  );
  $("method-select").value = method;
  for (const k of order) {
    const btn = document.createElement("button"),
      swatch = document.createElement("i");
    btn.type = "button";
    swatch.className = "dot";
    swatch.style.background = colors[k];
    btn.append(swatch, document.createTextNode(data.labels[k]));
    btn.setAttribute("aria-pressed", "true");
    btn.onclick = () => {
      if (visible.has(k)) visible.delete(k);
      else visible.add(k);
      btn.setAttribute("aria-pressed", String(visible.has(k)));
      chart();
    };
    $("legend").append(btn);
  }
  $("level").onchange = (e) => {
    stop();
    level = e.target.value;
    step = 1;
    update();
  };
  $("mask").onchange = (e) => {
    stop();
    mask = e.target.value;
    step = 1;
    draw();
  };
  $("method-select").onchange = (e) => {
    stop();
    method = e.target.value;
    step = 1;
    draw();
  };
  $("step").oninput = (e) => {
    stop();
    step = Number(e.target.value);
    draw();
  };
  $("rotate").onclick = () => {
    rotation = (rotation + 1) % 4;
    draw();
  };
  $("play").onclick = () => {
    if (timer) {
      stop();
      return;
    }
    if (step === data.levels[level].n) step = 1;
    draw();
    $("play").textContent = "Ⅱ";
    $("play").setAttribute("aria-label", "Pause proposals");
    timer = setInterval(() => {
      step++;
      draw();
      if (step === data.levels[level].n) stop();
    }, 620);
  };
  new ResizeObserver(() => {
    chart();
    draw();
  }).observe($("chart"));
  update();
  try {
    const optional = await fetch("ablation.json");
    if (optional.ok) {
      const extra = await optional.json();
      if (extra.trace_sha256 === data.manifest.trace_sha256) {
        ablations = extra;
        update();
      }
    }
  } catch {
    /* Custom runs can omit the reference-only ablation study. */
  }
}
init().catch((e) => {
  $("status").textContent =
    "Could not load the experiment. " +
    e.message +
    ". Start the local server with python lab.py serve.";
});
