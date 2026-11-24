"""Pruebas de ESBConverter (Grupo 11).

Cubren ida y vuelta de conocimiento, sesion y dictamen, errores previsibles
(archivo inexistente, JSON mal formado, estructura incompatible, permisos),
escritura atomica, convencion de nombres de sesion y el punto de enganche de
compatibilidad externa. No usan datos personales reales.
"""

import copy
import json
import os
from pathlib import Path

import pytest

from grupo_11_storage import (
    ESBConverter,
    IncompatibleStructureError,
    InvalidJSONError,
    StorageAccessError,
    StorageError,
    StorageFileNotFoundError,
    UnsupportedFormatError,
)
from grupo_11_storage.esb_storage import CONTRATOS

RAIZ = Path(__file__).resolve().parents[2]
EJEMPLOS = RAIZ / "grupo_11_storage" / "ejemplos"
EJEMPLOS_G4 = RAIZ / "grupo_04_schema" / "ejemplos"


def leer(ruta):
    with open(ruta, encoding="utf-8") as archivo:
        return json.load(archivo)


@pytest.fixture
def conv():
    return ESBConverter()


@pytest.fixture
def conocimiento():
    return leer(EJEMPLOS / "conocimiento_ejemplo.json")


@pytest.fixture
def sesion():
    return leer(EJEMPLOS / "sesion_ejemplo.json")


@pytest.fixture
def dictamen():
    return leer(EJEMPLOS / "dictamen_ejemplo.json")


def archivos_temporales(carpeta):
    return [p for p in Path(carpeta).iterdir() if p.name.endswith(".tmp")]


# --- Ida y vuelta -----------------------------------------------------------

class TestIdaYVuelta:
    def test_conocimiento(self, conv, conocimiento, tmp_path):
        ruta = tmp_path / "kb.json"
        assert conv.save_knowledge(conocimiento, ruta) == ruta
        assert conv.load_knowledge(ruta) == conocimiento

    def test_sesion(self, conv, sesion, tmp_path):
        ruta = tmp_path / "sesion.json"
        conv.save_session(sesion, ruta)
        assert conv.load_session(ruta) == sesion

    def test_dictamen(self, conv, dictamen, tmp_path):
        ruta = tmp_path / "dictamen.json"
        conv.save_verdict(dictamen, ruta)
        assert conv.load_verdict(ruta) == dictamen

    def test_conocimiento_academico_de_g4(self, conv, tmp_path):
        original = leer(EJEMPLOS_G4 / "conocimiento_dominio.json")
        ruta = tmp_path / "academico.json"
        conv.save_knowledge(original, ruta)
        assert conv.load_knowledge(ruta) == original

    def test_casos_de_g4(self, conv, tmp_path):
        base = EJEMPLOS_G4 / "casos"
        for caso in sorted(p for p in base.iterdir() if p.is_dir()):
            memoria = leer(caso / "memoria_trabajo.json")
            dictamen = leer(caso / "dictamen_salida.json")
            conv.save_session(memoria, tmp_path / f"{caso.name}_m.json")
            conv.save_verdict(dictamen, tmp_path / f"{caso.name}_d.json")
            assert conv.load_session(tmp_path / f"{caso.name}_m.json") == memoria
            assert conv.load_verdict(tmp_path / f"{caso.name}_d.json") == dictamen

    def test_conserva_campos_adicionales_y_orden(self, conv, conocimiento, tmp_path):
        conocimiento["meta"]["descripcion"] = "campo extra permitido"
        conocimiento["rules"][0]["etiqueta_extra"] = {"a": [1, 2, {"b": None}]}
        conocimiento["seccion_extra"] = {"z": 1, "a": 2}
        ruta = tmp_path / "kb.json"
        conv.save_knowledge(conocimiento, ruta)
        cargado = conv.load_knowledge(ruta)
        assert cargado == conocimiento
        assert list(cargado) == list(conocimiento)
        assert list(cargado["seccion_extra"]) == ["z", "a"]

    def test_conserva_unicode_sin_escapar(self, conv, conocimiento, tmp_path):
        ruta = tmp_path / "kb.json"
        conv.save_knowledge(conocimiento, ruta)
        texto = ruta.read_text(encoding="utf-8")
        assert "¿Que materia se consulta?" in texto
        assert "\\u" not in texto
        assert texto.endswith("\n")

    def test_no_modifica_el_diccionario_de_entrada(self, conv, conocimiento, tmp_path):
        antes = copy.deepcopy(conocimiento)
        conv.save_knowledge(conocimiento, tmp_path / "kb.json")
        assert conocimiento == antes

    def test_tuplas_se_guardan_como_listas(self, conv, conocimiento, tmp_path):
        conocimiento["attributes"][1]["range"] = (0, 3)
        ruta = tmp_path / "kb.json"
        conv.save_knowledge(conocimiento, ruta)
        assert conv.load_knowledge(ruta)["attributes"][1]["range"] == [0, 3]

    def test_sobrescribe_el_archivo_existente(self, conv, conocimiento, tmp_path):
        ruta = tmp_path / "kb.json"
        conv.save_knowledge(conocimiento, ruta)
        conocimiento["meta"]["version"] = "2.0"
        conv.save_knowledge(conocimiento, ruta)
        assert conv.load_knowledge(ruta)["meta"]["version"] == "2.0"
        assert archivos_temporales(tmp_path) == []

    def test_crea_carpetas_que_faltan(self, conv, conocimiento, tmp_path):
        ruta = tmp_path / "a" / "b" / "kb.json"
        conv.save_knowledge(conocimiento, ruta)
        assert ruta.is_file()

    def test_no_crea_carpetas_si_se_desactiva(self, conocimiento, tmp_path):
        conv = ESBConverter(create_dirs=False)
        with pytest.raises(StorageAccessError):
            conv.save_knowledge(conocimiento, tmp_path / "no_existe" / "kb.json")

    def test_acepta_str_y_path(self, conv, conocimiento, tmp_path):
        ruta = tmp_path / "kb.json"
        conv.save_knowledge(conocimiento, str(ruta))
        assert conv.load_knowledge(str(ruta)) == conocimiento

    def test_acepta_bom_utf8(self, conv, conocimiento, tmp_path):
        ruta = tmp_path / "kb.json"
        ruta.write_text(json.dumps(conocimiento, ensure_ascii=False), encoding="utf-8-sig")
        assert conv.load_knowledge(ruta) == conocimiento


# --- Archivo inexistente, JSON invalido, permisos -----------------------------

class TestErroresDeLectura:
    def test_archivo_inexistente(self, conv, tmp_path):
        with pytest.raises(StorageFileNotFoundError) as info:
            conv.load_knowledge(tmp_path / "no_existe.json")
        assert isinstance(info.value, FileNotFoundError)
        assert isinstance(info.value, StorageError)
        assert "no_existe.json" in str(info.value)

    @pytest.mark.parametrize("cargar", ["load_knowledge", "load_session", "load_verdict"])
    def test_inexistente_en_los_tres_tipos(self, conv, tmp_path, cargar):
        with pytest.raises(StorageFileNotFoundError):
            getattr(conv, cargar)(tmp_path / "x.json")

    def test_json_mal_formado_indica_linea(self, conv, tmp_path):
        ruta = tmp_path / "roto.json"
        ruta.write_text('{\n  "meta": {,\n}', encoding="utf-8")
        with pytest.raises(InvalidJSONError) as info:
            conv.load_knowledge(ruta)
        assert "linea 2" in str(info.value)
        assert isinstance(info.value, ValueError)

    def test_archivo_vacio(self, conv, tmp_path):
        ruta = tmp_path / "vacio.json"
        ruta.write_text("", encoding="utf-8")
        with pytest.raises(InvalidJSONError):
            conv.load_session(ruta)

    def test_no_utf8(self, conv, tmp_path):
        ruta = tmp_path / "latin1.json"
        ruta.write_bytes('{"a": "¿qué?"}'.encode("latin-1"))
        with pytest.raises(InvalidJSONError):
            conv.load_knowledge(ruta)

    def test_rechaza_nan_e_infinity(self, conv, tmp_path):
        ruta = tmp_path / "nan.json"
        ruta.write_text('{"promedio": NaN}', encoding="utf-8")
        with pytest.raises(InvalidJSONError):
            conv.load_session(ruta)

    def test_rechaza_claves_repetidas(self, conv, tmp_path):
        ruta = tmp_path / "dup.json"
        ruta.write_text('{"session_id": "a", "session_id": "b"}', encoding="utf-8")
        with pytest.raises(InvalidJSONError) as info:
            conv.load_session(ruta)
        assert "session_id" in str(info.value)

    def test_ruta_que_es_carpeta(self, conv, tmp_path):
        with pytest.raises(StorageAccessError):
            conv.load_knowledge(tmp_path)

    @pytest.mark.skipif(
        not hasattr(os, "geteuid") or os.geteuid() == 0,
        reason="root ignora los permisos de archivo",
    )
    def test_sin_permiso_de_lectura(self, conv, conocimiento, tmp_path):
        ruta = tmp_path / "kb.json"
        conv.save_knowledge(conocimiento, ruta)
        ruta.chmod(0o000)
        try:
            with pytest.raises(StorageAccessError):
                conv.load_knowledge(ruta)
        finally:
            ruta.chmod(0o644)


# --- Estructura incompatible ----------------------------------------------------

class TestEstructuraIncompatible:
    def test_carga_json_valido_pero_fuera_de_contrato(self, conv, conocimiento, tmp_path):
        del conocimiento["rules"]
        ruta = tmp_path / "kb.json"
        ruta.write_text(json.dumps(conocimiento), encoding="utf-8")
        with pytest.raises(IncompatibleStructureError) as info:
            conv.load_knowledge(ruta)
        assert any("rules" in e for e in info.value.errores)
        assert "kb.json" in str(info.value)

    def test_carga_raiz_que_no_es_objeto(self, conv, tmp_path):
        ruta = tmp_path / "lista.json"
        ruta.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(IncompatibleStructureError):
            conv.load_session(ruta)

    def test_carga_con_tipo_equivocado(self, conv, sesion, tmp_path):
        # Una sesion no es un conocimiento.
        ruta = tmp_path / "sesion.json"
        conv.save_session(sesion, ruta)
        with pytest.raises(IncompatibleStructureError):
            conv.load_knowledge(ruta)

    def test_guardar_invalido_no_escribe_nada(self, conv, conocimiento, tmp_path):
        conocimiento["rules"][0]["conditions"][0]["operator"] = "~="
        ruta = tmp_path / "kb.json"
        with pytest.raises(IncompatibleStructureError):
            conv.save_knowledge(conocimiento, ruta)
        assert not ruta.exists()
        assert archivos_temporales(tmp_path) == []

    def test_guardar_invalido_conserva_la_version_anterior(self, conv, conocimiento, tmp_path):
        ruta = tmp_path / "kb.json"
        conv.save_knowledge(conocimiento, ruta)
        contenido = ruta.read_bytes()
        conocimiento["attributes"] = []
        with pytest.raises(IncompatibleStructureError):
            conv.save_knowledge(conocimiento, ruta)
        assert ruta.read_bytes() == contenido

    def test_errores_semanticos_de_g4(self, conv, conocimiento, tmp_path):
        conocimiento["rules"][0]["conditions"][0]["attribute_id"] = "no_existe"
        with pytest.raises(IncompatibleStructureError) as info:
            conv.save_knowledge(conocimiento, tmp_path / "kb.json")
        assert any("no_existe" in e for e in info.value.errores)

    def test_guardar_objeto_que_no_es_dict(self, conv, tmp_path):
        with pytest.raises(IncompatibleStructureError):
            conv.save_knowledge(["no", "es", "dict"], tmp_path / "kb.json")

    def test_no_serializable(self, conv, sesion, tmp_path):
        sesion["facts"]["conjunto"] = {1, 2}
        with pytest.raises(IncompatibleStructureError) as info:
            conv.save_session(sesion, tmp_path / "s.json")
        assert "set" in str(info.value)

    def test_clave_que_no_es_texto(self, conv, sesion, tmp_path):
        sesion["facts"][1] = "uno"  # json la convertiria en "1" sin avisar
        with pytest.raises(IncompatibleStructureError):
            conv.save_session(sesion, tmp_path / "s.json")

    def test_nan_al_guardar(self, conv, sesion, tmp_path):
        sesion["facts"]["promedio"] = float("nan")
        with pytest.raises(IncompatibleStructureError):
            conv.save_session(sesion, tmp_path / "s.json", validate=False)

    def test_sesion_contra_conocimiento(self, conv, conocimiento, sesion, tmp_path):
        ruta = tmp_path / "s.json"
        conv.save_session(sesion, ruta, knowledge=conocimiento)
        assert conv.load_session(ruta, knowledge=conocimiento) == sesion

    def test_sesion_con_hecho_fuera_de_rango(self, conv, conocimiento, sesion, tmp_path):
        sesion["facts"]["promedio"] = 9.9
        with pytest.raises(IncompatibleStructureError) as info:
            conv.save_session(sesion, tmp_path / "s.json", knowledge=conocimiento)
        assert any("rango" in e for e in info.value.errores)
        assert not (tmp_path / "s.json").exists()

    def test_sesion_con_hecho_no_declarado_al_cargar(self, conv, conocimiento, sesion, tmp_path):
        ruta = tmp_path / "s.json"
        sesion["facts"]["inventado"] = "x"
        conv.save_session(sesion, ruta)  # sin conocimiento solo valida estructura
        with pytest.raises(IncompatibleStructureError):
            conv.load_session(ruta, knowledge=conocimiento)

    @pytest.mark.skipif(
        not hasattr(os, "geteuid") or os.geteuid() == 0,
        reason="root ignora los permisos de carpeta",
    )
    def test_sin_permiso_de_escritura(self, conv, conocimiento, tmp_path):
        carpeta = tmp_path / "solo_lectura"
        carpeta.mkdir()
        carpeta.chmod(0o555)
        try:
            with pytest.raises(StorageAccessError):
                conv.save_knowledge(conocimiento, carpeta / "kb.json")
        finally:
            carpeta.chmod(0o755)

    def test_guardar_sobre_una_carpeta(self, conv, conocimiento, tmp_path):
        with pytest.raises(StorageAccessError):
            conv.save_knowledge(conocimiento, tmp_path)


# --- Validacion opcional ---------------------------------------------------------

class TestValidacionOpcional:
    def borrador(self, conocimiento):
        # El contrato exige al menos una regla; los borradores de G1 traen rules: [].
        conocimiento["rules"] = []
        return conocimiento

    def test_borrador_se_rechaza_por_defecto(self, conv, conocimiento, tmp_path):
        with pytest.raises(IncompatibleStructureError):
            conv.save_knowledge(self.borrador(conocimiento), tmp_path / "kb.json")

    def test_borrador_con_validate_false(self, conv, conocimiento, tmp_path):
        ruta = tmp_path / "kb.json"
        conv.save_knowledge(self.borrador(conocimiento), ruta, validate=False)
        assert conv.load_knowledge(ruta, validate=False)["rules"] == []
        with pytest.raises(IncompatibleStructureError):
            conv.load_knowledge(ruta)

    def test_default_desactivado_en_el_constructor(self, conocimiento, tmp_path):
        conv = ESBConverter(validate=False)
        ruta = tmp_path / "kb.json"
        conv.save_knowledge(self.borrador(conocimiento), ruta)
        with pytest.raises(IncompatibleStructureError):
            conv.load_knowledge(ruta, validate=True)

    def test_validate_false_no_admite_json_roto(self, conocimiento, tmp_path):
        ruta = tmp_path / "roto.json"
        ruta.write_text("{", encoding="utf-8")
        with pytest.raises(InvalidJSONError):
            ESBConverter(validate=False).load_knowledge(ruta)

    def test_usa_contracts_por_defecto(self, conv):
        assert Path(conv.schema_manager.carpeta_esquemas) == CONTRATOS.resolve()

    def test_acepta_un_schema_manager_propio(self, conocimiento, tmp_path):
        llamadas = []

        class Falso:
            def validar_datos(self, datos, tipo):
                llamadas.append(tipo)
                return {"valido": False, "errores": ["$: rechazado por el falso"]}

        conv = ESBConverter(schema_manager=Falso())
        with pytest.raises(IncompatibleStructureError) as info:
            conv.save_knowledge(conocimiento, tmp_path / "kb.json")
        assert llamadas == ["conocimiento_dominio"]
        assert info.value.errores == ["$: rechazado por el falso"]

    def test_esquema_inexistente_es_error_claro(self, conocimiento, tmp_path):
        from grupo_11_storage import ValidationUnavailableError

        vacia = tmp_path / "sin_esquemas"
        vacia.mkdir()
        conv = ESBConverter(schemas_dir=vacia)
        with pytest.raises(ValidationUnavailableError):
            conv.save_knowledge(conocimiento, tmp_path / "kb.json")


# --- Sesiones por session_id -----------------------------------------------------

class TestSesionesPorId:
    def test_nombre_de_archivo(self, conv):
        assert conv.session_filename("sess_2026_10123") == "sesion_sess_2026_10123.json"

    @pytest.mark.parametrize(
        "malo", ["", "../escape", "a/b", "a\\b", "con espacio", ".oculto", "-x", None, 5, "x" * 129]
    )
    def test_rechaza_ids_peligrosos(self, conv, malo):
        with pytest.raises(ValueError):
            conv.session_filename(malo)

    def test_guardar_y_cargar_por_id(self, conv, sesion, tmp_path):
        ruta = conv.save_session_to_dir(sesion, tmp_path)
        assert ruta == tmp_path / "sesion_sess_ejemplo_001.json"
        assert conv.load_session_from_dir(tmp_path, "sess_ejemplo_001") == sesion

    def test_listar_sesiones(self, conv, sesion, tmp_path):
        for sid in ("b_2", "a_1", "c-3"):
            conv.save_session_to_dir({**sesion, "session_id": sid}, tmp_path)
        (tmp_path / "otro.json").write_text("{}", encoding="utf-8")
        assert conv.list_sessions(tmp_path) == ["a_1", "b_2", "c-3"]

    def test_listar_carpeta_inexistente(self, conv, tmp_path):
        with pytest.raises(StorageFileNotFoundError):
            conv.list_sessions(tmp_path / "no_existe")

    def test_cargar_id_inexistente(self, conv, tmp_path):
        with pytest.raises(StorageFileNotFoundError):
            conv.load_session_from_dir(tmp_path, "nada")

    def test_id_interno_distinto_al_del_nombre(self, conv, sesion, tmp_path):
        conv.save_session(sesion, tmp_path / "sesion_otra.json")
        with pytest.raises(IncompatibleStructureError):
            conv.load_session_from_dir(tmp_path, "otra")

    def test_guardar_sesion_sin_id_valido(self, conv, sesion, tmp_path):
        del sesion["session_id"]
        with pytest.raises(ValueError):
            conv.save_session_to_dir(sesion, tmp_path)


# --- Compatibilidad externa (punto de enganche) ------------------------------------

def importador_de_prueba(ruta):
    """Formato ficticio de prueba: 'titulo;atributo;valor' por linea."""
    lineas = Path(ruta).read_text(encoding="utf-8").splitlines()
    titulo, atributo, regla = lineas[0], lineas[1], lineas[2]
    return {
        "meta": {"project_title": titulo, "version": "1.0", "author_group": "externo"},
        "attributes": [
            {"id": atributo, "name": atributo.title(), "type": "numeric", "range": [0, 10]}
        ],
        "rules": [
            {
                "id": "r1",
                "description": regla,
                "priority": 1,
                "conditions": [{"attribute_id": atributo, "operator": ">", "value": 5}],
                "conclusion": {"attribute_id": "salida", "value": "alto"},
                "explanation_template": "",
            }
        ],
    }


def exportador_de_prueba(conocimiento, ruta):
    Path(ruta).write_text(conocimiento["meta"]["project_title"] + "\n", encoding="utf-8")


class TestCompatibilidadExterna:
    def test_sin_formatos_registrados(self, conv, tmp_path):
        assert conv.registered_formats() == []
        with pytest.raises(UnsupportedFormatError) as info:
            conv.import_knowledge(tmp_path / "x.csv", "csv")
        assert "pendiente" in str(info.value)

    def test_exportar_sin_formato(self, conv, conocimiento, tmp_path):
        with pytest.raises(UnsupportedFormatError):
            conv.export_knowledge(conocimiento, tmp_path / "x", "xml")

    def test_importar_con_formato_registrado(self, conv, tmp_path):
        conv.register_format("Demo", importer=importador_de_prueba, exporter=exportador_de_prueba)
        origen = tmp_path / "origen.demo"
        origen.write_text("Titulo ficticio\ntemperatura\nTemperatura alta\n", encoding="utf-8")
        resultado = conv.import_knowledge(origen, "demo")
        assert resultado["meta"]["project_title"] == "Titulo ficticio"
        # El resultado ya es JSON interno: se guarda y se recarga sin perdida.
        destino = tmp_path / "kb.json"
        conv.save_knowledge(resultado, destino)
        assert conv.load_knowledge(destino) == resultado

    def test_exportar_con_formato_registrado(self, conv, conocimiento, tmp_path):
        conv.register_format("demo", exporter=exportador_de_prueba)
        destino = tmp_path / "salida.demo"
        assert conv.export_knowledge(conocimiento, destino, "DEMO") == destino
        assert destino.read_text(encoding="utf-8").startswith("Elegibilidad")

    def test_formato_solo_importador_no_exporta(self, conv, conocimiento, tmp_path):
        conv.register_format("demo", importer=importador_de_prueba)
        with pytest.raises(UnsupportedFormatError):
            conv.export_knowledge(conocimiento, tmp_path / "x", "demo")

    def test_importador_que_produce_documento_invalido(self, conv, tmp_path):
        conv.register_format("malo", importer=lambda ruta: {"meta": {}})
        with pytest.raises(IncompatibleStructureError):
            conv.import_knowledge(tmp_path / "x", "malo")

    def test_importador_que_falla_se_traduce(self, conv, tmp_path):
        conv.register_format("roto", importer=lambda ruta: {}["falta"])
        with pytest.raises(IncompatibleStructureError) as info:
            conv.import_knowledge(tmp_path / "x", "roto")
        assert "roto" in str(info.value)

    def test_importar_archivo_inexistente(self, conv, tmp_path):
        conv.register_format("demo", importer=importador_de_prueba)
        with pytest.raises(StorageFileNotFoundError):
            conv.import_knowledge(tmp_path / "no_existe.demo", "demo")

    def test_exportar_valida_antes_de_convertir(self, conv, conocimiento, tmp_path):
        llamado = []
        conv.register_format("demo", exporter=lambda k, r: llamado.append(r))
        conocimiento["rules"] = []
        with pytest.raises(IncompatibleStructureError):
            conv.export_knowledge(conocimiento, tmp_path / "x", "demo")
        assert llamado == []

    def test_no_se_registra_json_como_externo(self, conv):
        with pytest.raises(ValueError):
            conv.register_format("json", importer=importador_de_prueba)

    @pytest.mark.parametrize("nombre", ["", "  ", None])
    def test_nombre_de_formato_invalido(self, conv, nombre):
        with pytest.raises(ValueError):
            conv.register_format(nombre, importer=importador_de_prueba)

    def test_registro_sin_funciones(self, conv):
        with pytest.raises(ValueError):
            conv.register_format("demo")


# --- Ejemplos del repositorio -------------------------------------------------------

def test_ejemplos_del_grupo_son_consistentes_entre_si(conocimiento, sesion, dictamen):
    from grupo_04_schema.esb_schema import SchemaManager

    resultado = SchemaManager(carpeta_esquemas=CONTRATOS).validar_conjunto(
        conocimiento, sesion, dictamen, atributo_resultado="dictamen"
    )
    assert resultado == {"valido": True, "errores": []}
