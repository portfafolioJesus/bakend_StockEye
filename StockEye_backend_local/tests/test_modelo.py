from dataclasses import asdict
from pathlib import Path
import json

import numpy as np
from PIL import Image
import pytest
import torch
from transformers import SegformerConfig, SegformerForSemanticSegmentation

from preparar_modelo import preparar
from stockeye.motor import CLASES, FORMATO, PIPELINE, MotorSegFormer
from stockeye import inferencia_base as base
from stockeye.procesador import Servicio
from .conftest import encolar, foto


@pytest.fixture
def checkpoint(tmp_path):
    # Modelo pequeño aleatorio SOLO para verificar el cargador y el recorrido real.
    # Nunca se distribuye como modelo entrenado ni se miden sus aciertos.
    arquitectura = SegformerConfig(num_labels=3, depths=[1, 1, 1, 1], hidden_sizes=[8, 16, 32, 64],
        num_attention_heads=[1, 2, 4, 8], mlp_ratios=[2, 2, 2, 2], decoder_hidden_size=16)
    modelo = SegformerForSemanticSegmentation(arquitectura)
    with torch.no_grad():
        modelo.decode_head.classifier.weight.zero_()
        modelo.decode_head.classifier.bias.copy_(torch.tensor([0., 0., 8.]))
    cfg = base.Config(lado_completa=128, crop=128, tile=64, alto_rectificado=64)
    p = tmp_path / "best.pt"
    torch.save(dict(modelo=modelo.state_dict(), model_config=arquitectura.to_dict(), config=asdict(cfg), pipeline=PIPELINE), p)
    return p


def test_pt_unico_real_pipeline_y_api_con_cpu(cfg, checkpoint, monkeypatch):
    def prohibido(*a, **kw): raise AssertionError("No debe descargar arquitectura de Internet")
    monkeypatch.setattr(SegformerConfig, "from_pretrained", prohibido)
    preparar(checkpoint, cfg.modelo.archivo, modo="completa", umbral=.5)
    cfg.modelo.dispositivo = "cpu"
    s = Servicio(cfg); s.cargar_motor()
    assert s.motor is not None, s.error_modelo
    for sucursal in (1, 2): foto(cfg.carpetas[sucursal] / "real.png")
    encolar(s)
    while s.procesar_uno(): pass
    assert s.registro.conteos()["completada"] == 2
    for trabajo in s.registro.listar()[0]:
        d = s.archivos.leer(trabajo["id"])
        assert d["gondolas"][0]["pct_vacio_observado"] == 100
        assert d["gondolas"][0]["pct_vacio_gondola_completa"] is None
        assert d["gondolas"][0]["semaforo"] == "revisar"
        assert d["modelo_sha256"] == s.motor.sha256
        mapa = np.asarray(Image.open(s.archivos.archivo(trabajo["id"], "mascara")))
        assert mapa.shape == (64, 96) and np.all(mapa == 2)


def test_best_pt_sin_operacion_requiere_datos_explicitos(cfg, checkpoint):
    cfg.modelo.archivo = checkpoint
    with pytest.raises(ValueError, match="modo validado"): MotorSegFormer(cfg)
    cfg.modelo.modo = "completa"; cfg.modelo.umbral_vacio = .5
    assert MotorSegFormer(cfg).operacion["modo"] == "completa"


def test_tensores_incompatibles_no_se_aceptan(cfg, checkpoint):
    c = torch.load(checkpoint, weights_only=True)
    c["modelo"]["decode_head.classifier.weight"] = torch.zeros(5, 16, 1, 1)
    torch.save(c, checkpoint)
    with pytest.raises(RuntimeError): preparar(checkpoint, cfg.modelo.archivo, modo="completa", umbral=.5)


def test_cambiar_pt_cambia_identidad_sin_cambiar_endpoints(cfg, checkpoint):
    preparar(checkpoint, cfg.modelo.archivo, modo="completa", umbral=.5)
    anterior = MotorSegFormer(cfg).sha256
    c = torch.load(checkpoint, weights_only=True)
    c["modelo"]["decode_head.classifier.bias"][1] = 1
    torch.save(c, checkpoint)
    nuevo = cfg.modelo.archivo.with_name("nuevo.pt")
    preparar(checkpoint, nuevo, modo="completa", umbral=.5)
    cfg.modelo.archivo.unlink(); nuevo.replace(cfg.modelo.archivo)
    assert MotorSegFormer(cfg).sha256 != anterior


def test_presupuesto_tiempo_se_aplica_sin_fingir_resultado(cfg, checkpoint):
    preparar(checkpoint, cfg.modelo.archivo, modo="completa", umbral=.5)
    cfg.limites.tiempo_max_s = .0000001
    motor = MotorSegFormer(cfg)
    with pytest.raises(TimeoutError): motor.inferir(foto(cfg.carpetas[1] / "foto.png"))


def test_validacion_tamano_antes_de_decodificacion_modelo(cfg, checkpoint):
    preparar(checkpoint, cfg.modelo.archivo, modo="completa", umbral=.5)
    cfg.limites.max_pixeles = 100
    motor = MotorSegFormer(cfg)
    with pytest.raises(ValueError, match="max_pixeles"):
        motor.inferir(foto(cfg.carpetas[1] / "foto.png"))


def test_preparacion_preserva_checkpoint_y_requiere_operacion(cfg, checkpoint):
    original = checkpoint.read_bytes()
    with pytest.raises(ValueError, match="--modo"): preparar(checkpoint, cfg.modelo.archivo)
    preparar(checkpoint, cfg.modelo.archivo, modo="completa", umbral=.5)
    empaquetado = torch.load(cfg.modelo.archivo, weights_only=True)
    assert empaquetado["formato"] == FORMATO and empaquetado["clases"] == CLASES
    assert checkpoint.read_bytes() == original
    assert "opt" not in empaquetado


def test_preparacion_rechaza_cambio_de_clases(cfg, checkpoint):
    c = torch.load(checkpoint, weights_only=True)
    c["clases"] = {"0": "vacio", "1": "ocupado", "2": "fondo"}
    torch.save(c, checkpoint)
    with pytest.raises(ValueError, match="clases"):
        preparar(checkpoint, cfg.modelo.archivo, modo="completa", umbral=.5)


@pytest.mark.parametrize("alterar", [False, True])
def test_preparar_desde_bundle_verifica_integridad(cfg, checkpoint, alterar):
    c = torch.load(checkpoint, weights_only=True)
    carpeta = checkpoint.parent / "bundle"; carpeta.mkdir()
    pesos = carpeta / "weights.pt"
    torch.save({"modelo": c["modelo"]}, pesos)
    arquitectura = carpeta / "model_config.json"
    arquitectura.write_text(json.dumps(c["model_config"]))
    identidad = {"pipeline": PIPELINE, "config": c["config"], "modo": "completa", "umbral": .5}
    manifest = {"esquema": "stockeye-bundle-1", "bundle_id": base.huella_json(identidad), "identidad": identidad,
                "archivos": {p.name: base.sha_archivo(p) for p in (pesos, arquitectura)}}
    (carpeta / "manifest.json").write_text(json.dumps(manifest))
    if alterar:
        arquitectura.write_text("{}")
        with pytest.raises(ValueError, match="alterado"):
            preparar(pesos, cfg.modelo.archivo)
    else:
        preparar(pesos, cfg.modelo.archivo)
        assert MotorSegFormer(cfg).operacion == {"modo": "completa", "umbral_vacio": .5}
