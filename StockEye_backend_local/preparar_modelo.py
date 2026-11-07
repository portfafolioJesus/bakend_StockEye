"""Convierte el checkpoint del notebook en un único .pt autocontenido para el PC."""
from __future__ import annotations

import argparse
from dataclasses import fields
import json
import math
import os
from pathlib import Path
import tempfile

from stockeye.motor import CLASES, FORMATO, PIPELINE, sha_archivo


def preparar(checkpoint: Path, salida: Path, *, modo=None, umbral=None, arquitectura_json=None) -> Path:
    import torch
    from stockeye import inferencia_base as base
    checkpoint, salida = Path(checkpoint).resolve(), Path(salida).resolve()
    if checkpoint == salida: raise ValueError("La salida debe ser distinta del checkpoint original.")
    if salida.exists(): raise FileExistsError("La salida ya existe. Usa otro nombre para conservar el modelo anterior.")
    origen = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if not isinstance(origen, dict) or not isinstance(origen.get("modelo"), dict):
        raise ValueError("El archivo no contiene el state_dict 'modelo' del notebook StockEye.")
    if origen.get("clases", CLASES) != CLASES:
        raise ValueError("El orden de clases del checkpoint es incompatible.")
    config = origen.get("config", {})
    arquitectura = origen.get("model_config")
    pipeline = origen.get("pipeline")
    operacion = origen.get("operacion", {})
    manifest_path = checkpoint.parent / "manifest.json"
    procedencia = "checkpoint_del_notebook"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        base.comprobar_bundle(checkpoint.parent, manifest.get("bundle_id"))
        identidad = manifest.get("identidad", {})
        if manifest.get("esquema") != "stockeye-bundle-1" or manifest.get("archivos", {}).get(checkpoint.name) != sha_archivo(checkpoint):
            raise ValueError("El checkpoint no coincide con el manifiesto del bundle.")
        config = identidad.get("config", config)
        pipeline = identidad.get("pipeline", pipeline)
        operacion = {"modo": identidad.get("modo"), "umbral_vacio": identidad.get("umbral")}
        procedencia = "bundle_exportado_del_notebook"
        if arquitectura is None:
            arquitectura_json = arquitectura_json or checkpoint.parent / "model_config.json"
    if arquitectura_json is not None:
        arquitectura = json.loads(Path(arquitectura_json).read_text(encoding="utf-8"))
    if pipeline != PIPELINE or not isinstance(arquitectura, dict) or not isinstance(config, dict):
        raise ValueError("Se requieren pipeline StockEye v6, config y model_config. Usa best.pt corregido o weights.pt de su bundle.")
    modo = modo or operacion.get("modo")
    umbral = umbral if umbral is not None else operacion.get("umbral_vacio")
    if modo not in {"completa", "tta", "mosaicos", "mosaicos+tta"}:
        raise ValueError("Indica --modo con el modo validado en Colab [6.3].")
    if isinstance(umbral, bool) or not isinstance(umbral, (int, float)) or not math.isfinite(umbral) or not 0 < umbral < 1:
        raise ValueError("Indica --umbral con el umbral validado en Colab [6.3].")
    cfg = base.validar_config(base.Config(**{k: v for k, v in config.items() if k in {f.name for f in fields(base.Config)}}))
    hfcfg = base.SegformerConfig.from_dict(arquitectura)
    if hfcfg.num_labels != 3 or hfcfg.num_channels != 3:
        raise ValueError("Solo se admiten tres clases y entrada RGB.")
    # Comprueba compatibilidad real de los tensores antes de entregar el archivo.
    modelo = base.SegformerForSemanticSegmentation(hfcfg)
    modelo.load_state_dict(origen["modelo"], strict=True)
    del modelo
    empaquetado = dict(formato=FORMATO, pipeline=PIPELINE, clases=CLASES, modelo=origen["modelo"],
        model_config=arquitectura, config=config, operacion={"modo": modo, "umbral_vacio": float(umbral)},
        procedencia=procedencia, checkpoint_original_sha256=sha_archivo(checkpoint))
    salida.parent.mkdir(parents=True, exist_ok=True)
    fd, nombre = tempfile.mkstemp(prefix=".modelo_", suffix=".tmp", dir=salida.parent)
    os.close(fd)
    temporal = Path(nombre)
    try:
        torch.save(empaquetado, temporal)
        temporal.replace(salida)
    finally:
        temporal.unlink(missing_ok=True)
    return salida


def main():
    parser = argparse.ArgumentParser(description="Preparar un único .pt local sin entrenar ni modificar el checkpoint original.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--salida", type=Path, default=Path("modelos/modelo.pt"))
    parser.add_argument("--modo", choices=["completa", "tta", "mosaicos", "mosaicos+tta"])
    parser.add_argument("--umbral", type=float)
    parser.add_argument("--arquitectura-json", type=Path)
    args = parser.parse_args()
    destino = preparar(args.checkpoint, args.salida, modo=args.modo, umbral=args.umbral, arquitectura_json=args.arquitectura_json)
    print("Modelo preparado:", destino)
    print("SHA-256:", sha_archivo(destino))
    print("La preparación comprueba formato y tensores; no mide ni certifica precisión predictiva.")


if __name__ == "__main__":
    main()
