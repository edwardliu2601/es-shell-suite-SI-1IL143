"""Pruebas unitarias del editor: python -m unittest discover -s tests -v"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from grupo_02_rules.esb_rules import RuleEditor, RuleEditorError

BASE = {
    "meta": {"project_title": "Ejemplo", "version": "1.0", "author_group": "Pruebas"},
    "attributes": [
        {"id": "promedio", "name": "Promedio", "type": "numeric", "range": [0, 3]},
        {"id": "materia", "name": "Materia", "type": "categorical", "options": ["Tesis", "Electiva"]},
        {"id": "activo", "name": "Activo", "type": "boolean"},
        {"id": "dictamen", "name": "Resultado", "type": "categorical", "options": ["Elegible", "No elegible"]}
    ],
    "rules": []
}


def example_rule():
    return {
        "id": "rule_01", "description": "Requisito académico", "priority": 10,
        "conditions": [
            {"attribute_id": "promedio", "operator": ">=", "value": 2.0},
            {"attribute_id": "materia", "operator": "==", "value": "Tesis"}
        ],
        "conclusion": {"attribute_id": "dictamen", "value": "Elegible"},
        "explanation_template": "Cumple los criterios."
    }


class RuleEditorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "conocimiento_dominio.json"
        self.path.write_text(json.dumps(BASE), encoding="utf-8")
        self.editor = RuleEditor(self.path)

    def test_create_and_save_preserves_meta_attributes(self):
        self.editor.create_rule(example_rule())
        self.editor.save_rules()
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(stored["meta"], BASE["meta"])
        self.assertEqual(stored["attributes"], BASE["attributes"])
        self.assertEqual(stored["rules"][0]["id"], "rule_01")

    def test_edit_priority_and_description(self):
        self.editor.create_rule(example_rule())
        self.editor.edit_rule("rule_01", {"description": "Criterio actualizado"})
        self.editor.set_priority("rule_01", 20)
        self.assertEqual(self.editor.get_rule("rule_01")["priority"], 20)
        self.assertEqual(self.editor.get_rule("rule_01")["description"], "Criterio actualizado")

    def test_duplicate_id_rejected(self):
        self.editor.create_rule(example_rule())
        with self.assertRaisesRegex(RuleEditorError, "ya existe"):
            self.editor.create_rule(example_rule())

    def test_unknown_condition_attribute_rejected(self):
        rule = example_rule()
        rule["conditions"][0]["attribute_id"] = "desconocido"
        self.assertFalse(self.editor.validate_rule(rule)["valido"])

    def test_order_operator_rejected_on_categorical(self):
        rule = example_rule()
        rule["conditions"][1]["operator"] = ">"
        self.assertFalse(self.editor.validate_rule(rule)["valido"])

    def test_invalid_categorical_value_rejected(self):
        rule = example_rule()
        rule["conditions"][1]["value"] = "Otra"
        self.assertFalse(self.editor.validate_rule(rule)["valido"])

    def test_bool_priority_is_not_int(self):
        rule = example_rule()
        rule["priority"] = True
        self.assertFalse(self.editor.validate_rule(rule)["valido"])

    def test_empty_conditions_rejected(self):
        rule = example_rule()
        rule["conditions"] = []
        self.assertFalse(self.editor.validate_rule(rule)["valido"])

    def test_boolean_condition_supported(self):
        rule = example_rule()
        rule["conditions"] = [{"attribute_id": "activo", "operator": "==", "value": True}]
        self.assertTrue(self.editor.validate_rule(rule)["valido"])

    def test_new_conclusion_fact_warned_but_accepted(self):
        rule = example_rule()
        rule["conclusion"] = {"attribute_id": "hecho_nuevo", "value": "nuevo"}
        result = self.editor.validate_rule(rule)
        self.assertTrue(result["valido"])
        self.assertTrue(result["advertencias"])

    def test_change_rule_id_not_allowed(self):
        self.editor.create_rule(example_rule())
        with self.assertRaisesRegex(RuleEditorError, "cambiar el id"):
            self.editor.edit_rule("rule_01", {"id": "rule_02"})

    def test_delete_rule(self):
        self.editor.create_rule(example_rule())
        self.editor.delete_rule("rule_01")
        self.assertEqual(self.editor.list_rules(), [])

    def test_external_metadata_change_preserved(self):
        self.editor.create_rule(example_rule())
        newer = copy.deepcopy(BASE)
        newer["meta"]["version"] = "2.0"
        newer["attributes"].append({"id": "nuevo", "name": "Nuevo", "type": "text"})
        self.path.write_text(json.dumps(newer), encoding="utf-8")
        self.editor.save_rules()
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(stored["meta"]["version"], "2.0")
        self.assertEqual(stored["attributes"][-1]["id"], "nuevo")

    def test_external_rules_change_not_overwritten(self):
        self.editor.create_rule(example_rule())
        newer = copy.deepcopy(BASE)
        newer["rules"] = [example_rule()]
        self.path.write_text(json.dumps(newer), encoding="utf-8")
        with self.assertRaisesRegex(RuleEditorError, "cambiaron en disco"):
            self.editor.save_rules()

    def test_schema_manager_accepted(self):
        class FakeSchema:
            def validar_datos(self, data, tipo):
                return {"valido": tipo == "conocimiento_dominio", "errores": []}
        editor = RuleEditor(self.path, schema_manager=FakeSchema())
        editor.create_rule(example_rule())
        editor.save_rules()
        self.assertEqual(len(editor.list_rules()), 1)

    def test_schema_manager_rejected_does_not_save(self):
        class FakeSchema:
            def validar_datos(self, data, tipo):
                return {"valido": False, "errores": ["rechazado para prueba"]}
        editor = RuleEditor(self.path, schema_manager=FakeSchema())
        editor.create_rule(example_rule())
        with self.assertRaisesRegex(RuleEditorError, "rechazado para prueba"):
            editor.save_rules()
        self.assertEqual(json.loads(self.path.read_text())["rules"], [])

    def test_load_discards_unsaved_changes(self):
        self.editor.create_rule(example_rule())
        self.assertEqual(self.editor.load_rules(), [])

    def test_invalid_json_rejected(self):
        self.path.write_text("{ no es JSON", encoding="utf-8")
        with self.assertRaises(RuleEditorError):
            RuleEditor(self.path)

    def test_nan_is_rejected(self):
        rule = example_rule()
        rule["conditions"][0]["value"] = float("nan")
        self.assertFalse(self.editor.validate_rule(rule)["valido"])

    def test_invalid_operator_structure_returns_error(self):
        rule = example_rule()
        rule["conditions"][0]["operator"] = [">="]
        self.assertFalse(self.editor.validate_rule(rule)["valido"])

    def test_invalid_rule_id_type_returns_error(self):
        rule = example_rule()
        rule["id"] = ["rule_01"]
        self.assertFalse(self.editor.validate_rule(rule)["valido"])

    def test_changed_attributes_trigger_revalidation_before_save(self):
        self.editor.create_rule(example_rule())
        newer = copy.deepcopy(BASE)
        newer["attributes"] = [a for a in newer["attributes"] if a["id"] != "promedio"]
        self.path.write_text(json.dumps(newer), encoding="utf-8")
        with self.assertRaisesRegex(RuleEditorError, "no declarado"):
            self.editor.save_rules()

    def test_list_is_deep_copy(self):
        self.editor.create_rule(example_rule())
        rules = self.editor.list_rules()
        rules[0]["priority"] = 999
        self.assertEqual(self.editor.get_rule("rule_01")["priority"], 10)


if __name__ == "__main__":
    unittest.main()
