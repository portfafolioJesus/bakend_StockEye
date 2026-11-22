"""Pruebas sin llamadas a proveedores externos ni inferencia real."""
import json
import unittest

import httpx

from stockeye.ia.openai_compatible import ProveedorOpenAICompatible, error_limite
from stockeye.ia.proveedor import ErrorIA, normalizar_clasificacion


CATALOGO = [{"id":1,"codigo":"LACTEOS","nombre":"Lácteos y huevos"},
            {"id":2,"codigo":"BEBIDAS","nombre":"Bebidas y jugos"}]


class ContratoClasificacion(unittest.TestCase):
    def clasificacion(self, datos):
        return normalizar_clasificacion(datos,CATALOGO,proveedor="falso",modelo="prueba")

    def test_categoria_debe_pertenecer_al_catalogo(self):
        r = self.clasificacion({"decision":"IDENTIFICADA","categoria_codigo":"inventada","confianza":1})
        self.assertIsNone(r.categoria_codigo)
        self.assertEqual(r.decision,"DESCONOCIDA")

    def test_foto_mixta_no_se_fuerza_a_una_categoria(self):
        r = self.clasificacion({"decision":"MIXTA","categoria_codigo":"LACTEOS","confianza":0.9})
        self.assertIsNone(r.categoria_codigo)
        self.assertEqual(r.decision,"MIXTA")

    def test_sin_decision_explicita_requiere_revision(self):
        r = self.clasificacion({"categoria_codigo":"LACTEOS","confianza":1})
        self.assertIsNone(r.categoria_codigo)

    def test_normaliza_codigo_y_conserva_confianza_informativa(self):
        r = self.clasificacion({"decision":"IDENTIFICADA","categoria_codigo":" lacteos ","confianza":0.91})
        self.assertEqual(r.categoria_codigo,"LACTEOS")
        self.assertEqual(r.confianza,0.91)

    def test_confianza_nan_no_se_convierte_en_certeza(self):
        r = self.clasificacion({"decision":"DESCONOCIDA","confianza":float("nan")})
        self.assertIsNone(r.confianza)

    def test_429_desconocido_no_afirma_cuota_diaria(self):
        r = httpx.Response(429,json={"error":{"message":"Rate limit reached"}})
        error = error_limite(r,"groq")
        self.assertEqual(error.motivo,"LIMITE_USO")
        self.assertTrue(error.es_limite)

    def test_limite_por_minuto_no_es_cuota_diaria(self):
        r = httpx.Response(429,json={"error":{"message":"Tokens per minute (TPM) reached"}},
                           headers={"retry-after":"42"})
        error = error_limite(r,"groq")
        self.assertEqual(error.motivo,"LIMITE_TEMPORAL")
        self.assertEqual(error.esperar_s,42)

    def test_cuota_diaria_confirmada(self):
        r = httpx.Response(429,json={"error":{"message":"Tokens per day (TPD) reached"}})
        error = error_limite(r,"groq")
        self.assertEqual(error.motivo,"CUOTA")
        self.assertEqual(error.esperar_s,3600)

    def test_retry_after_invalido_no_rompe_trabajador(self):
        r = httpx.Response(429,json={},headers={"retry-after":"NaN"})
        self.assertEqual(error_limite(r,"groq").esperar_s,30)

    def test_error_no_expone_respuesta_ni_credenciales(self):
        cliente = ProveedorOpenAICompatible("groq","https://example.invalid","solo-prueba","prueba")
        cliente._cliente.close()
        cliente._cliente = httpx.Client(transport=httpx.MockTransport(
            lambda _:httpx.Response(400,text="PASSWORD-SECRETO")),base_url="https://example.invalid")
        with self.assertRaises(ErrorIA) as contexto:
            cliente._post({})
        self.assertNotIn("PASSWORD-SECRETO",str(contexto.exception))
        cliente._cliente.close()

    def test_peticion_clasifica_visibles_con_catalogo_y_no_faltantes(self):
        cliente = ProveedorOpenAICompatible("groq","https://example.invalid","solo-prueba","prueba")
        cuerpos = []
        def responder(request):
            cuerpos.append(json.loads(request.content))
            return httpx.Response(200,json={
                "model":"prueba","choices":[{"message":{"content":json.dumps({
                    "decision":"IDENTIFICADA","categoria_codigo":"LACTEOS",
                    "producto":"Yogures visibles","confianza":0.9})}}],
                "usage":{"prompt_tokens":100,"completion_tokens":20}})
        cliente._cliente.close()
        cliente._cliente = httpx.Client(transport=httpx.MockTransport(responder),base_url="https://example.invalid")
        respuesta = cliente.clasificar(b"imagen-simulada",CATALOGO)
        self.assertEqual(respuesta.categoria_codigo,"LACTEOS")
        self.assertEqual(respuesta.tokens_entrada,100)
        self.assertIn("PRODUCTOS VISIBLES",cuerpos[0]["messages"][0]["content"])
        self.assertIn("LACTEOS",cuerpos[0]["messages"][1]["content"][0]["text"])
        cliente._cliente.close()


if __name__ == "__main__":
    unittest.main()
