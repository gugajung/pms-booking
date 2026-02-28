from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Callable

from flask import Flask, jsonify, render_template, request, Response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)

GAMMA_W = 9.81  # kN/m3


@dataclass
class SliceData:
    x_mid: float
    alpha_deg: float
    height: float
    width: float
    weight: float


@dataclass
class SurfaceResult:
    fs: float
    xc: float
    yc: float
    r: float
    x1: float
    x2: float
    slices: list[SliceData]


def ground_line(height: float, beta_deg: float, crest_width: float) -> tuple[Callable[[float], float], float, float]:
    beta_rad = math.radians(beta_deg)
    run = height / max(math.tan(beta_rad), 1e-6)

    def ground(x: float) -> float:
        if x <= 0:
            return 0.0
        if x <= run:
            return (height / run) * x
        return height

    x_min = -height
    x_max = run + crest_width
    return ground, x_min, x_max


def find_intersections(ground: Callable[[float], float], xc: float, yc: float, r: float, x_min: float, x_max: float) -> list[float]:
    points: list[float] = []
    steps = 500
    dx = (x_max - x_min) / steps

    def f(x: float) -> float | None:
        inside = r * r - (x - xc) ** 2
        if inside <= 0:
            return None
        yb = yc - math.sqrt(inside)
        return ground(x) - yb

    prev_x = x_min
    prev_f = f(prev_x)
    for i in range(1, steps + 1):
        x = x_min + i * dx
        cur_f = f(x)
        if prev_f is None or cur_f is None:
            prev_x, prev_f = x, cur_f
            continue

        if prev_f == 0:
            points.append(prev_x)
        elif cur_f == 0:
            points.append(x)
        elif prev_f * cur_f < 0:
            a, b = prev_x, x
            fa, fb = prev_f, cur_f
            for _ in range(28):
                m = (a + b) / 2
                fm = f(m)
                if fm is None:
                    break
                if fa * fm <= 0:
                    b, fb = m, fm
                else:
                    a, fa = m, fm
            points.append((a + b) / 2)

        prev_x, prev_f = x, cur_f

    points = sorted(points)
    deduped: list[float] = []
    for p in points:
        if not deduped or abs(p - deduped[-1]) > 1e-3:
            deduped.append(p)
    return deduped


def bishop_fs(
    slices: list[SliceData],
    cohesion: float,
    phi_deg: float,
    ru: float,
) -> float | None:
    phi = math.radians(phi_deg)
    tan_phi = math.tan(phi)

    fs = 1.5
    for _ in range(60):
        sum_num = 0.0
        sum_den = 0.0

        for s in slices:
            alpha = math.radians(s.alpha_deg)
            w = s.weight
            u = ru * w
            m_alpha = math.cos(alpha) + (math.sin(alpha) * tan_phi) / max(fs, 1e-6)
            if m_alpha <= 1e-6:
                return None

            resisting = cohesion * s.width + (w - u) * tan_phi
            sum_num += resisting / m_alpha
            sum_den += w * math.sin(alpha)

        if sum_den <= 1e-6:
            return None

        new_fs = sum_num / sum_den
        if not math.isfinite(new_fs) or new_fs <= 0:
            return None
        if abs(new_fs - fs) < 1e-4:
            return new_fs
        fs = new_fs

    return fs


def evaluate_surface(
    ground: Callable[[float], float],
    xc: float,
    yc: float,
    r: float,
    x_min: float,
    x_max: float,
    height: float,
    gamma: float,
    cohesion: float,
    phi_deg: float,
    ru: float,
    n_slices: int,
) -> SurfaceResult | None:
    intersections = find_intersections(ground, xc, yc, r, x_min, x_max)
    if len(intersections) < 2:
        return None

    x1 = intersections[0]
    x2 = intersections[-1]
    if x2 - x1 < 0.55 * height:
        return None

    dx = (x2 - x1) / n_slices
    slices: list[SliceData] = []

    for i in range(n_slices):
        xm = x1 + (i + 0.5) * dx
        inside = r * r - (xm - xc) ** 2
        if inside <= 0:
            return None

        yb = yc - math.sqrt(inside)
        yt = ground(xm)
        h = yt - yb
        if h <= 0:
            return None

        dy_dx = (xm - xc) / max(math.sqrt(inside), 1e-6)
        alpha = abs(math.degrees(math.atan(dy_dx)))
        width = dx / max(math.cos(math.radians(alpha)), 1e-6)
        w = gamma * h * dx
        slices.append(SliceData(x_mid=xm, alpha_deg=alpha, height=h, width=width, weight=w))

    fs = bishop_fs(slices=slices, cohesion=cohesion, phi_deg=phi_deg, ru=ru)
    if fs is None:
        return None

    return SurfaceResult(fs=fs, xc=xc, yc=yc, r=r, x1=x1, x2=x2, slices=slices)


def search_critical_surface(data: dict) -> tuple[SurfaceResult, dict, list[SurfaceResult]]:
    height = float(data.get("height", 20))
    beta_deg = float(data.get("beta_deg", 40))
    crest_width = float(data.get("crest_width", 16))

    gamma = float(data.get("gamma", 20))
    cohesion = float(data.get("cohesion", 25))
    phi_deg = float(data.get("phi_deg", 30))
    ru = float(data.get("ru", 0.15))

    n_slices = int(data.get("n_slices", 24))
    grid_x = int(data.get("grid_x", 20))
    grid_y = int(data.get("grid_y", 16))

    if height <= 0:
        raise ValueError("Altura do talude deve ser maior que zero")
    if not (5 <= n_slices <= 80):
        raise ValueError("Numero de fatias deve estar entre 5 e 80")

    ground, x_min, x_max = ground_line(height, beta_deg, crest_width)

    xc_min, xc_max = -2.5 * height, -0.1 * height
    yc_min, yc_max = 0.2 * height, 2.8 * height

    candidates: list[SurfaceResult] = []

    for ix in range(grid_x):
        xc = xc_min + (xc_max - xc_min) * ix / max(grid_x - 1, 1)
        for iy in range(grid_y):
            yc = yc_min + (yc_max - yc_min) * iy / max(grid_y - 1, 1)

            ref_x = x_max * 0.9
            ref_y = ground(ref_x)
            r = math.dist((xc, yc), (ref_x, ref_y))

            surface = evaluate_surface(
                ground=ground,
                xc=xc,
                yc=yc,
                r=r,
                x_min=x_min,
                x_max=x_max,
                height=height,
                gamma=gamma,
                cohesion=cohesion,
                phi_deg=phi_deg,
                ru=ru,
                n_slices=n_slices,
            )
            if surface:
                candidates.append(surface)

    if not candidates:
        raise ValueError("Nao foi possivel encontrar superficie valida. Ajuste os parametros.")

    candidates.sort(key=lambda c: c.fs)
    best = candidates[0]

    context = {
        "height": height,
        "beta_deg": beta_deg,
        "crest_width": crest_width,
        "gamma": gamma,
        "cohesion": cohesion,
        "phi_deg": phi_deg,
        "ru": ru,
        "n_slices": n_slices,
    }

    return best, context, candidates[:5]


@app.get("/")
def home() -> str:
    return render_template("index.html")


@app.post("/api/analysis")
def run_analysis() -> Response:
    data = request.get_json(force=True) or {}

    try:
        best, context, top = search_critical_surface(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(
        {
            "ok": True,
            "context": context,
            "critical": {
                "fs": round(best.fs, 3),
                "xc": round(best.xc, 3),
                "yc": round(best.yc, 3),
                "radius": round(best.r, 3),
                "x1": round(best.x1, 3),
                "x2": round(best.x2, 3),
                "slices": [asdict(s) for s in best.slices],
            },
            "top_surfaces": [
                {
                    "fs": round(s.fs, 3),
                    "xc": round(s.xc, 3),
                    "yc": round(s.yc, 3),
                    "radius": round(s.r, 3),
                }
                for s in top
            ],
        }
    )


@app.post("/api/report")
def generate_report() -> Response:
    payload = request.get_json(force=True) or {}
    context = payload.get("context") or {}
    critical = payload.get("critical") or {}

    if not context or not critical:
        return jsonify({"error": "Dados insuficientes para gerar laudo."}), 400

    fs = float(critical.get("fs", 0))
    stability = "Estavel" if fs >= 1.5 else "Atencao" if fs >= 1.3 else "Instavel"

    html = render_template(
        "report.html",
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
        context=context,
        critical=critical,
        stability=stability,
    )

    return Response(
        html,
        mimetype="text/html",
        headers={"Content-Disposition": "attachment; filename=laudo_estabilidade.html"},
    )


if __name__ == "__main__":
    app.run(debug=True)
