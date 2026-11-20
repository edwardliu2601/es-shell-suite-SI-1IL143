"""Integración real con QuestionEditor (G1) y SchemaManager (G4)."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from grupo_01_questions.esb_questions import Attribute, QuestionEditor
from grupo_02_rules.esb_rules import RuleEditor, RuleEditorError
from grupo_02_rules.esb_rules_cli import ejecutar_menu
from grupo_04_schema.esb_schema import SchemaManager

ROOT = Path(__file__).resolve().parents[2]
G1_EXAMPLE = ROOT / "grupo_01_questions/datos_ejemplo/conocimiento_dominio.sample.json"
G4_EXAMPLE = ROOT / "grupo_04_schema/ejemplos/conocimiento_dominio.json"
G2_EXAMPLE = ROOT / "grupo_02_rules/datos_ejemplo/conocimiento_dominio.json"


def regla(id="regla_extra", operator="in", value=None):
    if value is None:
        value = ["Electiva", "Obligatoria"]
    return {
        "id": id,
        "description": "Acepta tipos de materia",
        "priority": 25,
        "conditions": [{"attribute_id": "materia", "operator": operator, "value": value}],
        "conclusion": {"attribute_id": "dictamen", "value": "Elegible"},
        "explanation_template": "La materia pertenece a las categorías permitidas.",
    }


class IntegracionG1G4(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "conocimiento_dominio.json"
        self.schema = SchemaManager()

    def test_g1_crea_atributos_g2_crea_reglas_g4_valida(self):
        # Los atributos provienen del módulo real del G1, no de un mock.
        editor_g1 = QuestionEditor()
        editor_g1.load_from_json(str(G1_EXAMPLE))
        editor_g1.add_attribute(Attribute(
            id="dictamen", name="Resultado", type="categorical",
            options=["Elegible", "No elegible"],
        ))
        editor_g1.save_to_json(str(self.path))  # Inicialmente 'rules': []
        datos_antes = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(datos_antes["rules"]), 0)
        editor_g2 = RuleEditor(self.path, schema_manager=self.schema)
        editor_g2.create_rule(regla())
        editor_g2.save_rules()
        datos = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(self.schema.validar_datos(datos, "conocimiento_dominio"),
                         {"valido": True, "errores": []})
        self.assertEqual(datos["attributes"], datos_antes["attributes"])
        self.assertEqual(datos["meta"], datos_antes["meta"])
        self.assertEqual(datos["attributes"][1]["help_text"],
                         datos_antes["attributes"][1]["help_text"])
        self.assertEqual(datos["attributes"][2]["depends_on"],
                         datos_antes["attributes"][2]["depends_on"])

    def test_g1_guarda_atributos_sin_borrar_reglas_del_g2(self):
        self.path.write_bytes(G2_EXAMPLE.read_bytes())
        before = json.loads(self.path.read_text())
        editor = QuestionEditor()
        editor.load_from_json(str(self.path))
        editor.add_attribute(Attribute(id="nuevo", name="Dato nuevo", type="text"))
        editor.save_to_json(str(self.path))
        after = json.loads(self.path.read_text())
        self.assertEqual(after["rules"], before["rules"])
        self.assertTrue(self.schema.validar_datos(after, "conocimiento_dominio")["valido"])

    def test_g2_edita_regla_de_ejemplo_g4_y_revalida(self):
        self.path.write_bytes(G4_EXAMPLE.read_bytes())
        before = json.loads(self.path.read_text())
        self.assertGreaterEqual(len(before["rules"]), 5)
        editor = RuleEditor(self.path, schema_manager=self.schema)
        nombre = editor.list_rules()[0]["id"]
        editor.set_priority(nombre, 40)
        editor.save_rules()
        after = json.loads(self.path.read_text())
        self.assertEqual(self.schema.validar_datos(after, "conocimiento_dominio"),
                         {"valido": True, "errores": []})
        self.assertEqual(after["rules"][0]["priority"], 40)
        self.assertEqual(before["attributes"], after["attributes"])
        self.assertEqual(before["rules"][1:], after["rules"][1:])

    def test_reemplazo_del_atributo_usado_en_la_regla_se_rechaza(self):
        self.path.write_bytes(G2_EXAMPLE.read_bytes())
        editor = RuleEditor(self.path, schema_manager=self.schema)
        doc = json.loads(self.path.read_text(encoding="utf-8"))
        doc["attributes"] = [a for a in doc["attributes"] if a["id"] != "materia"]
        self.path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(RuleEditorError, "no declarado"):
            editor.save_rules()

    def test_el_contrato_no_acepta_reglas_vacias_finales(self):
        self.path.write_bytes(G2_EXAMPLE.read_bytes())
        editor = RuleEditor(self.path, schema_manager=self.schema)
        editor.delete_rule("rule_01")
        with self.assertRaisesRegex(RuleEditorError, "exige una regla"):
            editor.save_rules()
        self.assertEqual(len(json.loads(self.path.read_text())["rules"]), 1)

    def test_in_aceptado_por_grupo2_y_grupo4(self):
        self.path.write_bytes(G2_EXAMPLE.read_bytes())
        editor = RuleEditor(self.path, schema_manager=self.schema)
        editor.create_rule(regla())
        editor.save_rules()
        doc = json.loads(self.path.read_text())
        self.assertEqual(self.schema.validar_datos(doc, "conocimiento_dominio"),
                         {"valido": True, "errores": []})

    def test_in_rechaza_lista_vacia(self):
        self.path.write_bytes(G2_EXAMPLE.read_bytes())
        editor = RuleEditor(self.path)
        r = regla(value=[])
        result = editor.validate_rule(r)
        self.assertFalse(result["valido"])
        self.assertIn("lista no vacía", " ".join(result["errores"]))

    def test_in_rechaza_elementos_con_tipo_incorrecto(self):
        self.path.write_bytes(G2_EXAMPLE.read_bytes())
        editor = RuleEditor(self.path)
        self.assertFalse(editor.validate_rule(regla(value=["Electiva", 10]))["valido"])
        self.assertFalse(editor.validate_rule(regla(value=["No existe"]))["valido"])

    def test_in_rechaza_valor_no_lista(self):
        self.path.write_bytes(G2_EXAMPLE.read_bytes())
        editor = RuleEditor(self.path)
        self.assertFalse(editor.validate_rule(regla(value="Electiva"))["valido"])

    def test_otros_operadores_no_admiten_listas(self):
        self.path.write_bytes(G2_EXAMPLE.read_bytes())
        editor = RuleEditor(self.path)
        self.assertFalse(editor.validate_rule(regla(operator="==", value=["Electiva"]))["valido"])

    def test_in_soporta_otros_tipos_compatibles(self):
        self.path.write_bytes(G2_EXAMPLE.read_bytes())
        editor = RuleEditor(self.path)
        for attr, vals in (("promedio", [2.0, 2.5]),
                           ("nombre_tesis", ["Proyecto A", "Proyecto B"])):
            with self.subTest(attr=attr):
                r = regla(id=f"r_{attr}")
                r["conditions"][0].update(attribute_id=attr, value=vals)
                self.assertTrue(editor.validate_rule(r)["valido"])

    def test_falta_description_es_error_de_esquema(self):
        self.path.write_bytes(G2_EXAMPLE.read_bytes())
        editor = RuleEditor(self.path)
        r = regla()
        r["description"] = " "
        self.assertFalse(editor.validate_rule(r)["valido"])

    def test_json_no_estandar_nan_es_rechazado(self):
        self.path.write_text('{"meta": {}, "attributes": [], "rules": [NaN]}')
        with self.assertRaises(RuleEditorError):
            RuleEditor(self.path)

    def test_cli_edita_prioridad_y_guarda(self):
        self.path.write_bytes(G2_EXAMPLE.read_bytes())
        editor = RuleEditor(self.path, schema_manager=self.schema)
        # 3=editar -> rule_01 -> 2=prioridad -> 99, 6=guardar, 0=salir
        with patch("builtins.input", side_effect=["3", "rule_01", "2", "99", "6", "0"]):
            ejecutar_menu(editor)
        doc = json.loads(self.path.read_text())
        self.assertEqual(doc["rules"][0]["priority"], 99)
        self.assertTrue(self.schema.validar_datos(doc, "conocimiento_dominio")["valido"])

    def test_cli_crea_regla_con_in_y_guarda(self):
        self.path.write_bytes(G2_EXAMPLE.read_bytes())
        editor = RuleEditor(self.path, schema_manager=self.schema)
        # Crear regla con una condición in y conclusión sobre dictamen.
        entrada = ["2", "regla_cli", "Admite materias comunes", "20", "materia", "in",
                   '["Electiva", "Obligatoria"]', "n", "dictamen", "Elegible",
                   "Regla creada por consola", "6", "0"]
        with patch("builtins.input", side_effect=entrada):
            ejecutar_menu(editor)
        doc = json.loads(self.path.read_text())
        self.assertEqual(doc["rules"][1]["conditions"][0]["operator"], "in")
        self.assertTrue(self.schema.validar_datos(doc, "conocimiento_dominio")["valido"])


if __name__ == "__main__":
    unittest.main()
