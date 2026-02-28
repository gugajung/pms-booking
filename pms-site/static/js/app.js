const state = {
  result: null,
};

async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "Falha na API");
  }
  return data;
}

function formPayload(form) {
  const fd = new FormData(form);
  const data = Object.fromEntries(fd.entries());
  ["height", "beta_deg", "crest_width", "gamma", "cohesion", "phi_deg", "ru"].forEach((k) => {
    data[k] = Number(data[k]);
  });
  ["n_slices", "grid_x", "grid_y"].forEach((k) => {
    data[k] = Number(data[k]);
  });
  return data;
}

function fsClass(fs) {
  if (fs >= 1.5) return "good";
  if (fs >= 1.3) return "warn";
  return "bad";
}

function renderTopTable(top) {
  const body = document.getElementById("topTable");
  body.innerHTML = top
    .map((s, i) => `
      <tr>
        <td>#${i + 1}</td>
        <td>${s.fs.toFixed(3)}</td>
        <td>(${s.xc.toFixed(2)}, ${s.yc.toFixed(2)})</td>
        <td>${s.radius.toFixed(2)} m</td>
      </tr>
    `)
    .join("");
}

function drawAnalysis(result) {
  const canvas = document.getElementById("slopeCanvas");
  const ctx = canvas.getContext("2d");
  const { context, critical } = result;

  const H = context.height;
  const beta = (context.beta_deg * Math.PI) / 180;
  const run = H / Math.tan(beta);
  const crest = context.crest_width;

  const xMin = -H;
  const xMax = run + crest;
  const yMin = -0.2 * H;
  const yMax = Math.max(1.3 * H, critical.yc + critical.radius * 0.2);

  const pad = 32;
  const sx = (canvas.width - 2 * pad) / (xMax - xMin);
  const sy = (canvas.height - 2 * pad) / (yMax - yMin);
  const scale = Math.min(sx, sy);

  function tx(x) {
    return pad + (x - xMin) * scale;
  }

  function ty(y) {
    return canvas.height - pad - (y - yMin) * scale;
  }

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  ctx.fillStyle = "#f8fbff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  ctx.beginPath();
  ctx.moveTo(tx(xMin), ty(0));
  ctx.lineTo(tx(0), ty(0));
  ctx.lineTo(tx(run), ty(H));
  ctx.lineTo(tx(run + crest), ty(H));
  ctx.lineTo(tx(xMax), ty(0));
  ctx.lineTo(tx(xMin), ty(0));
  ctx.closePath();
  const grd = ctx.createLinearGradient(0, ty(H), 0, ty(0));
  grd.addColorStop(0, "#ddd0b0");
  grd.addColorStop(1, "#b9935f");
  ctx.fillStyle = grd;
  ctx.fill();

  ctx.strokeStyle = "#204b76";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(tx(0), ty(0));
  ctx.lineTo(tx(run), ty(H));
  ctx.lineTo(tx(run + crest), ty(H));
  ctx.stroke();

  ctx.strokeStyle = "#d32f2f";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(tx(critical.xc), ty(critical.yc), critical.radius * scale, 0, Math.PI * 2);
  ctx.stroke();

  const x1 = critical.x1;
  const x2 = critical.x2;
  const n = 120;
  ctx.strokeStyle = "#6d1b7b";
  ctx.lineWidth = 3;
  ctx.beginPath();
  for (let i = 0; i <= n; i++) {
    const x = x1 + ((x2 - x1) * i) / n;
    const inside = critical.radius ** 2 - (x - critical.xc) ** 2;
    if (inside <= 0) continue;
    const y = critical.yc - Math.sqrt(inside);
    if (i === 0) ctx.moveTo(tx(x), ty(y));
    else ctx.lineTo(tx(x), ty(y));
  }
  ctx.stroke();

  ctx.strokeStyle = "rgba(18, 68, 120, 0.25)";
  ctx.lineWidth = 1;
  critical.slices.forEach((s) => {
    const x = s.x_mid;
    const inside = critical.radius ** 2 - (x - critical.xc) ** 2;
    if (inside <= 0) return;
    const yb = critical.yc - Math.sqrt(inside);
    const yt = x <= 0 ? 0 : x <= run ? (H / run) * x : H;
    ctx.beginPath();
    ctx.moveTo(tx(x), ty(yb));
    ctx.lineTo(tx(x), ty(yt));
    ctx.stroke();
  });
}

async function runAnalysis(payload) {
  const status = document.getElementById("status");
  status.textContent = "Processando...";

  try {
    const result = await api("/api/analysis", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    state.result = result;
    renderTopTable(result.top_surfaces);
    drawAnalysis(result);

    const fs = result.critical.fs;
    const badge = document.getElementById("fsBadge");
    badge.textContent = `FS: ${fs.toFixed(3)}`;
    badge.className = `fs-badge ${fsClass(fs)}`;

    status.textContent = `Superfície crítica encontrada. Centro (${result.critical.xc.toFixed(2)}, ${result.critical.yc.toFixed(2)}), R=${result.critical.radius.toFixed(2)} m.`;
    document.getElementById("btnReport").disabled = false;
  } catch (err) {
    document.getElementById("status").textContent = err.message;
  }
}

async function downloadReport() {
  if (!state.result) return;
  const res = await fetch("/api/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      context: state.result.context,
      critical: state.result.critical,
    }),
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.error || "Erro ao gerar laudo");
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "laudo_estabilidade.html";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function bind() {
  const form = document.getElementById("analysisForm");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    await runAnalysis(formPayload(form));
  });

  document.getElementById("btnReport").addEventListener("click", async () => {
    const status = document.getElementById("status");
    try {
      await downloadReport();
      status.textContent = "Laudo gerado com sucesso (HTML para impressão/PDF).";
    } catch (err) {
      status.textContent = err.message;
    }
  });

  runAnalysis(formPayload(form));
}

bind();
