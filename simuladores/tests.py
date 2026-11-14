from datetime import date

from django.test import SimpleTestCase, override_settings

from . import renapo
from .curp import validar_formato


class CurpTests(SimpleTestCase):
    def test_curp_correcta(self):
        self.assertEqual(validar_formato("PEPJ900101HPLRRN02"), (True, ""))
        self.assertEqual(validar_formato(" gomA050315mplnrna2 "), (True, ""))

    def test_digito_verificador_equivocado(self):
        valida, motivo = validar_formato("PEPJ900101HPLRRN03")
        self.assertFalse(valida)
        self.assertIn("dígito verificador", motivo)

    def test_longitud_y_formato(self):
        self.assertFalse(validar_formato("PEPJ900101")[0])
        self.assertFalse(validar_formato("1EPJ900101HPLRRN02")[0])
        self.assertFalse(validar_formato("PEPJ900101HXXRRN02")[0])  # entidad inexistente
        self.assertFalse(validar_formato("")[0])
        self.assertFalse(validar_formato(None)[0])

    def test_fecha_imposible(self):
        self.assertFalse(validar_formato("PEPJ900231HPLRRN09")[0])  # 31 de febrero


class SimuladorRenapoTests(SimpleTestCase):
    @override_settings(DEBUG=True)
    def test_responde_con_los_datos_que_codifica_la_curp(self):
        respuesta = renapo.consultar("GOMA050315MPLNRNA2")
        self.assertTrue(respuesta.encontrada)
        self.assertEqual(respuesta.fecha_nacimiento, date(2005, 3, 15))
        self.assertEqual(respuesta.sexo, "M")
        self.assertEqual(respuesta.entidad_nacimiento, "PL")
        self.assertTrue(respuesta.simulada)

    @override_settings(DEBUG=True)
    def test_curp_dada_de_baja(self):
        respuesta = renapo.consultar(renapo.CURP_DADA_DE_BAJA)
        self.assertFalse(respuesta.encontrada)
        self.assertEqual(respuesta.estatus, "baja")

    @override_settings(DEBUG=False)
    def test_no_funciona_en_produccion(self):
        with self.assertRaises(RuntimeError):
            renapo.consultar("PEPJ900101HPLRRN02")
