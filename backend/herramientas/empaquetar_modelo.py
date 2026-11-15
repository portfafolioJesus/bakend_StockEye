"""Convierte el checkpoint del notebook (best.pt, SegFormer) en un modelo ONNX
listo para el worker, y mide si cumple el presupuesto de tiempo en ESTE equipo.

Uso (requiere el venv de herramientas, que sí tiene PyTorch):
    .venv-herramientas/bin/python herramientas/empaquetar_modelo.py \
        --checkpoint modelos/best.pt --version v1 --umbral 0.5 --presupuesto 3

Genera en modelos/:
    segformer-mit-b1-v1.onnx   pesos para onnxruntime (sin PyTorch)
    segformer-mit-b1-v1.json   manifiesto: clases, umbral, lado elegido, métricas y benchmark
Después se registra en la BD con:
    python -m stockeye.cli modelo registrar modelos/segformer-mit-b1-v1.json --activar
"""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

CLASES = {"0": "fondo", "1": "ocupado", "2": "vacio"}
# Arquitectura MiT-b1 (nvidia/mit-b1) fija: no se descarga nada de Hugging Face.
ARQUITECTURAS = {
    "nvidia/mit-b0": dict(hidden_sizes=[32, 64, 160, 256], depths=[2, 2, 2, 2], decoder_hidden_size=256),
    "nvidia/mit-b1": dict(hidden_sizes=[64, 128, 320, 512], depths=[2, 2, 2, 2], decoder_hidden_size=256),
    "nvidia/mit-b2": dict(hidden_sizes=[64, 128, 320, 512], depths=[3, 4, 6, 3], decoder_hidden_size=768),
}
# Tope de píxeles de entrada a la red (≈ 1280×704, 1152×640, 1024×576, 896×504, 768×432)
PIXELES = (900_000, 740_000, 600_000, 450_000, 330_000)


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def cargar_torch(checkpoint: Path):
    import torch
    from transformers import SegformerConfig, SegformerForSemanticSegmentation

    datos = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if not isinstance(datos, dict) or not isinstance(datos.get("modelo"), dict):
        raise SystemExit("El archivo no contiene el state_dict 'modelo' del notebook StockEye.")
    config = datos.get("config", {}) or {}
    base = config.get("modelo_base", "nvidia/mit-b1")
    arquitectura = datos.get("model_config")
    if arquitectura:
        hf = SegformerConfig.from_dict(arquitectura)
    else:
        if base not in ARQUITECTURAS:
            raise SystemExit(f"Modelo base desconocido {base}; agrega su arquitectura a ARQUITECTURAS.")
        hf = SegformerConfig(num_labels=3, num_attention_heads=[1, 2, 5, 8], sr_ratios=[8, 4, 2, 1],
                             patch_sizes=[7, 3, 3, 3], strides=[4, 2, 2, 2], mlp_ratios=[4, 4, 4, 4],
                             **ARQUITECTURAS[base])
    hf.num_labels = 3
    hf.id2label = {0: "fondo", 1: "ocupado", 2: "vacio"}
    hf.label2id = {v: k for k, v in hf.id2label.items()}
    modelo = SegformerForSemanticSegmentation(hf)
    modelo.load_state_dict(datos["modelo"], strict=True)      # falla si la arquitectura no calza
    return modelo.eval(), datos, base, hf.to_dict()


def exportar_onnx(modelo, salida: Path):
    import torch

    class SoloLogits(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, pixel_values):
            return self.m(pixel_values=pixel_values).logits

    envoltorio = SoloLogits(modelo).eval()
    ejemplo = torch.randn(1, 3, 576, 1024)
    tmp = salida.with_suffix(".tmp.onnx")
    try:
        torch.onnx.export(envoltorio, (ejemplo,), str(tmp), input_names=["pixel_values"], output_names=["logits"],
                          dynamic_axes={"pixel_values": {2: "alto", 3: "ancho"}, "logits": {2: "alto4", 3: "ancho4"}},
                          opset_version=17, dynamo=False, do_constant_folding=True)
    except Exception as error:   # PyTorch sin exportador clásico → exportador dynamo
        print(f"  exportador clásico no disponible ({type(error).__name__}); uso dynamo")
        alto, ancho = torch.export.Dim("alto", min=32, max=4096), torch.export.Dim("ancho", min=32, max=4096)
        programa = torch.onnx.export(envoltorio, (ejemplo,), dynamo=True, input_names=["pixel_values"],
                                     output_names=["logits"], dynamic_shapes=({2: alto, 3: ancho},))
        programa.save(str(tmp))
    import onnx
    m = onnx.load(str(tmp), load_external_data=True)
    onnx.checker.check_model(m)
    onnx.save(m, str(salida), save_as_external_data=False)   # un solo archivo
    for f in salida.parent.glob(tmp.name + "*"):
        f.unlink()
    tmp.unlink(missing_ok=True)


def comparar(modelo, ruta_onnx: Path) -> float:
    """Diferencia máxima entre PyTorch y ONNX en los logits (debe ser ~1e-4)."""
    import numpy as np
    import onnxruntime as ort
    import torch

    x = torch.randn(1, 3, 704, 1280)
    with torch.inference_mode():
        ref = modelo(pixel_values=x).logits.numpy()
    ses = ort.InferenceSession(str(ruta_onnx), providers=["CPUExecutionProvider"])
    out = ses.run(None, {"pixel_values": x.numpy()})[0]
    return float(np.abs(ref - out).max())


def imagen_sintetica(ancho: int, alto: int):
    """Góndola dibujada (el tiempo no depende del contenido, pero así el postproceso trabaja)."""
    import cv2
    import numpy as np
    rng = np.random.default_rng(0)
    img = np.full((alto, ancho, 3), 60, np.uint8)
    repisas = 4
    for r in range(repisas):
        y0 = int(alto * (0.08 + r * 0.22)); y1 = y0 + int(alto * 0.18)
        x = int(ancho * 0.03)
        while x < ancho * 0.97:
            w = int(ancho * rng.uniform(0.03, 0.06))
            if rng.random() > 0.15:
                color = tuple(int(c) for c in rng.integers(40, 250, 3))
                cv2.rectangle(img, (x, y0), (x + w - 4, y1), color, -1)
            x += w
        cv2.rectangle(img, (0, y1 + 2), (ancho, y1 + 14), (200, 200, 200), -1)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes()


def medir(ruta_onnx: Path, pixeles: int, hilos: int, fotos: list[bytes], repeticiones: int, umbral: float):
    from stockeye.inferencia.segformer_onnx import MotorSegFormerOnnx

    motor = MotorSegFormerOnnx(ruta_onnx, lado=1280, pixeles_max=pixeles, umbral_vacio=umbral, hilos=hilos)
    tiempos = []
    for _ in range(repeticiones):
        for jpg in fotos:
            t = time.perf_counter()
            motor.inferir_bytes(jpg)          # decodificar + inferir + % + anotar
            tiempos.append(time.perf_counter() - t)
    tiempos.sort()
    p95 = tiempos[min(len(tiempos) - 1, int(round(0.95 * (len(tiempos) - 1))))]
    return dict(pixeles_max=pixeles, hilos=hilos, p50_s=round(statistics.median(tiempos), 3), p95_s=round(p95, 3),
                max_s=round(tiempos[-1], 3), n=len(tiempos))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--nombre", default="segformer-mit-b1")
    ap.add_argument("--version", default="v1")
    ap.add_argument("--umbral", type=float, default=0.5,
                    help="p(vacío) mínima por píxel. Usar el validado en Colab [6.3]; 0.5 es provisional.")
    ap.add_argument("--presupuesto", type=float, default=3.0, help="segundos máximos por foto (p95)")
    ap.add_argument("--margen", type=float, default=0.8, help="usar solo este % del presupuesto (holgura)")
    ap.add_argument("--hilos", type=int, nargs="+", default=[2, 4], help="hilos por worker a probar")
    ap.add_argument("--pixeles", type=int, help="forzar tope de píxeles de entrada (omite la elección automática)")
    ap.add_argument("--fotos", type=Path, nargs="*", default=[], help="fotos reales para el benchmark")
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--salida", type=Path, default=RAIZ / "modelos")
    args = ap.parse_args()

    args.salida.mkdir(parents=True, exist_ok=True)
    base_nombre = f"{args.nombre}-{args.version}"
    ruta_onnx, ruta_json = args.salida / f"{base_nombre}.onnx", args.salida / f"{base_nombre}.json"

    print(f"1/4 Cargando {args.checkpoint} …")
    modelo, datos, modelo_base, arquitectura = cargar_torch(args.checkpoint)
    print(f"    {modelo_base}, época {datos.get('epoca')}, métricas {datos.get('metricas')}")

    print(f"2/4 Exportando a ONNX → {ruta_onnx.name} …")
    exportar_onnx(modelo, ruta_onnx)
    dif = comparar(modelo, ruta_onnx)
    print(f"    diferencia máxima PyTorch vs ONNX: {dif:.2e}")
    if dif > 1e-2:
        raise SystemExit("La salida ONNX no coincide con PyTorch; no se publica el modelo.")
    del modelo

    print("3/4 Midiendo tiempos (foto completa: decodificar + inferir + % + imagen anotada) …")
    fotos = [p.read_bytes() for p in args.fotos] or [
        imagen_sintetica(1920, 1080), imagen_sintetica(4000, 3000), imagen_sintetica(1080, 1920)]
    resultados, elegido = [], None
    topes = [args.pixeles] if args.pixeles else list(PIXELES)
    limite = args.presupuesto * args.margen
    for hilos in sorted(args.hilos):
        for pixeles in topes:
            r = medir(ruta_onnx, pixeles, hilos, fotos, args.repeticiones, args.umbral)
            r["cumple"] = r["p95_s"] <= limite
            resultados.append(r)
            print(f"    hilos={hilos} pixeles={pixeles:>7}: p50={r['p50_s']:.2f}s p95={r['p95_s']:.2f}s "
                  f"{'OK' if r['cumple'] else 'excede'}")
            if r["cumple"]:
                break
    # Mayor resolución que cumple con el MENOR número de hilos (deja núcleos para otro worker)
    for hilos in sorted(args.hilos):
        candidatos = [r for r in resultados if r["hilos"] == hilos and r["cumple"]]
        if candidatos:
            elegido = max(candidatos, key=lambda r: r["pixeles_max"])
            break
    if not elegido:
        raise SystemExit(f"Ninguna resolución cumple p95 ≤ {limite:.2f}s en este equipo. Prueba más --hilos.")
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

    print("4/4 Escribiendo manifiesto …")
    manifiesto = dict(
        esquema="stockeye-modelo-1", nombre=args.nombre, version=args.version, familia="SEGFORMER",
        formato="onnx", archivo=ruta_onnx.name, sha256=sha256(ruta_onnx), clases=CLASES,
        umbral_confianza=args.umbral,
        parametros=dict(lado=1280, pixeles_max=elegido["pixeles_max"], hilos_recomendados=elegido["hilos"], modo="completa",
                        area_min_gondola=0.01, area_min_caja=0.002, margen_borde_px=3),
        metricas={k: round(float(v), 4) for k, v in (datos.get("metricas") or {}).items()
                  if isinstance(v, (int, float))},
        origen=dict(checkpoint=args.checkpoint.name, sha256=sha256(args.checkpoint), modelo_base=modelo_base,
                    epoca=datos.get("epoca"), arquitectura=arquitectura),
        benchmark=dict(presupuesto_s=args.presupuesto, margen=args.margen, resultados=resultados,
                       rss_max_mb=round(rss_mb), equipo=equipo(), fecha=datetime.now(timezone.utc).isoformat()),
    )
    ruta_json.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nListo: pixeles_max={elegido['pixeles_max']} hilos={elegido['hilos']} p95={elegido['p95_s']}s "
          f"(presupuesto {args.presupuesto}s) · RAM máx. del proceso de medición ≈ {rss_mb:.0f} MB")
    print(f"Registrar: python -m stockeye.cli modelo registrar {ruta_json.relative_to(RAIZ)} --activar")


def equipo() -> dict:
    import os
    import platform
    cpu = platform.processor()
    try:
        cpu = next(l.split(":", 1)[1].strip() for l in Path("/proc/cpuinfo").read_text().splitlines()
                   if l.startswith("model name"))
    except (OSError, StopIteration):
        pass
    return dict(cpu=cpu, nucleos_logicos=os.cpu_count())


if __name__ == "__main__":
    main()
