"""Persistencia y compatibilidad de ES-Shell Suite (Grupo 11).

``ESBConverter`` guarda y vuelve a cargar los documentos JSON comunes del
proyecto (conocimiento del dominio, memoria de trabajo y dictamen de salida)
sin cambiar sus nombres de campo ni su significado.

Principios de diseno:

- Solo biblioteca estandar para leer y escribir (``json``, UTF-8, ``pathlib``).
  La validacion se delega en ``SchemaManager`` del Grupo 4, que usa
  ``jsonschema``; se importa solo cuando hace falta validar.
- Se valida antes de guardar y despues de cargar. Si algo falla se lanza una
  excepcion clara; nunca se devuelven datos parciales como si fueran validos.
- La escritura es atomica: se escribe un archivo temporal en la misma carpeta
  y luego se reemplaza el destino. Un fallo no deja un archivo a medias ni
  destruye la version anterior.
- No se descarta ningun dato: los campos adicionales que permiten los esquemas
  se conservan y lo que no se puede representar en JSON se rechaza.
- La conversion de formatos externos esta separada de la lectura/escritura y
  no trae ningun formato definido: se registran con ``register_format`` cuando
  el curso acuerde cuales se admiten.

Las firmas publicas siguen la orientacion del README del grupo y estan
pendientes de acuerdo con los grupos consumidores (4, 10 y 12).
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable

RAIZ = Path(__file__).resolve().parent.parent
CONTRATOS = RAIZ / "contracts"

TIPO_CONOCIMIENTO = "conocimiento_dominio"
TIPO_SESION = "memoria_trabajo"
TIPO_DICTAMEN = "dictamen_salida"

PREFIJO_SESION = "sesion_"
EXTENSION = ".json"
_PATRON_ID_SESION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

__all__ = [
    "ESBConverter",
    "StorageError",
    "StorageFileNotFoundError",
    "StorageAccessError",
    "InvalidJSONError",
    "IncompatibleStructureError",
    "UnsupportedFormatError",
    "ValidationUnavailableError",
    "CONTRATOS",
]


# --- Excepciones -----------------------------------------------------------

class StorageError(Exception):
    """Base de todos los errores del modulo de persistencia."""


class StorageFileNotFoundError(StorageError, FileNotFoundError):
    """El archivo pedido no existe."""


class StorageAccessError(StorageError, OSError):
    """No se pudo leer o escribir: permisos, ruta que es una carpeta, disco."""


class InvalidJSONError(StorageError, ValueError):
    """El archivo no es JSON valido (mal formado, no UTF-8, NaN, claves repetidas)."""


class IncompatibleStructureError(StorageError, ValueError):
    """El documento es JSON, pero no cumple el contrato o no se puede serializar.

    ``errores`` contiene la lista de mensajes de validacion (en el formato de
    ``SchemaManager``: ``"$.ruta: descripcion"``).
    """

    def __init__(self, mensaje: str, errores: Iterable[str] | None = None):
        super().__init__(mensaje)
        self.errores = list(errores) if errores is not None else [mensaje]


class UnsupportedFormatError(StorageError, ValueError):
    """El formato externo no esta registrado (compatibilidad no definida)."""


class ValidationUnavailableError(StorageError):
    """No se puede validar: falta SchemaManager, jsonschema o los esquemas."""


# --- Utilidades internas ---------------------------------------------------

def _rechazar_constante(valor: str) -> None:
    # json.load acepta NaN e Infinity por defecto, pero no son JSON estandar.
    raise ValueError(f"Constante numerica no valida en JSON: {valor}")


def _sin_claves_repetidas(pares: list[tuple[str, Any]]) -> dict:
    # json.load se queda en silencio con la ultima clave repetida: eso
    # alteraria la informacion sin avisar.
    resultado: dict[str, Any] = {}
    for clave, valor in pares:
        if clave in resultado:
            raise ValueError(f"Clave repetida en un objeto JSON: '{clave}'")
        resultado[clave] = valor
    return resultado


def _normalizar(valor: Any, ruta: str = "$") -> Any:
    """Devuelve una copia representable en JSON sin perdida silenciosa.

    Las tuplas pasan a listas (sin perdida de informacion). Se rechazan claves
    que no sean texto (json las convertiria sin avisar), numeros no finitos y
    tipos que JSON no representa (set, bytes, datetime, objetos propios).
    """
    if valor is None or isinstance(valor, (bool, str, int)):
        return valor
    if isinstance(valor, float):
        if not math.isfinite(valor):
            raise IncompatibleStructureError(
                f"{ruta}: los numeros no finitos (NaN, Infinity) no son JSON valido."
            )
        return valor
    if isinstance(valor, dict):
        copia = {}
        for clave, elemento in valor.items():
            if not isinstance(clave, str):
                raise IncompatibleStructureError(
                    f"{ruta}: la clave {clave!r} no es texto; JSON la "
                    "convertiria y cambiaria el dato."
                )
            copia[clave] = _normalizar(elemento, f"{ruta}.{clave}")
        return copia
    if isinstance(valor, (list, tuple)):
        return [_normalizar(e, f"{ruta}[{i}]") for i, e in enumerate(valor)]
    raise IncompatibleStructureError(
        f"{ruta}: el tipo {type(valor).__name__} no se puede guardar en JSON."
    )


# --- Clase principal -------------------------------------------------------

class ESBConverter:
    """Guarda, carga y convierte los documentos JSON de ES-Shell Suite.

    Parametros:
        schema_manager: instancia de ``SchemaManager`` (Grupo 4) o compatible
            (``validar_datos`` y ``validar_memoria``). Si no se da, se crea
            una con los esquemas de ``contracts/``.
        schemas_dir: carpeta de esquemas para el ``SchemaManager`` creado
            aqui. Por defecto ``contracts/`` (la misma que usa el Grupo 12).
        validate: valor por defecto de validacion en cada operacion. Se puede
            cambiar por llamada con el argumento ``validate``.
        create_dirs: si es True, crea las carpetas que falten al guardar.
    """

    def __init__(
        self,
        schema_manager: Any = None,
        schemas_dir: str | os.PathLike | None = None,
        validate: bool = True,
        create_dirs: bool = True,
    ):
        self._schema_manager = schema_manager
        self._schemas_dir = Path(schemas_dir) if schemas_dir is not None else CONTRATOS
        self._validate = validate
        self._create_dirs = create_dirs
        self._formatos: dict[str, tuple[Callable | None, Callable | None]] = {}

    # --- Validacion --------------------------------------------------------

    @property
    def schema_manager(self) -> Any:
        """``SchemaManager`` en uso; se crea la primera vez que se necesita."""
        if self._schema_manager is None:
            try:
                from grupo_04_schema.esb_schema import SchemaManager
            except ImportError as error:
                raise ValidationUnavailableError(
                    "No se puede validar: falta SchemaManager (grupo_04_schema) "
                    "o la biblioteca jsonschema. Instale jsonschema, pase un "
                    "schema_manager propio o use validate=False. "
                    f"Detalle: {error}"
                ) from error
            carpeta = self._schemas_dir if self._schemas_dir.is_dir() else None
            self._schema_manager = SchemaManager(carpeta_esquemas=carpeta)
        return self._schema_manager

    def _debe_validar(self, validate: bool | None) -> bool:
        return self._validate if validate is None else validate

    def _validar(self, datos: dict, tipo: str, contexto: str) -> None:
        try:
            resultado = self.schema_manager.validar_datos(datos, tipo)
        except StorageError:
            raise
        except Exception as error:  # esquema ausente, mal formado, etc.
            raise ValidationUnavailableError(
                f"No se pudo validar {contexto} con el esquema '{tipo}': {error}"
            ) from error
        self._exigir(resultado, tipo, contexto)

    def _validar_sesion_con_conocimiento(
        self, sesion: dict, conocimiento: dict, contexto: str
    ) -> None:
        try:
            resultado = self.schema_manager.validar_memoria(sesion, conocimiento)
        except StorageError:
            raise
        except Exception as error:
            raise ValidationUnavailableError(
                f"No se pudo validar {contexto} contra el conocimiento: {error}"
            ) from error
        self._exigir(resultado, TIPO_SESION, contexto)

    @staticmethod
    def _exigir(resultado: dict, tipo: str, contexto: str) -> None:
        if resultado["valido"]:
            return
        errores = resultado["errores"]
        raise IncompatibleStructureError(
            f"{contexto} no cumple el contrato '{tipo}' "
            f"({len(errores)} error(es)). Primero: {errores[0]}",
            errores,
        )

    # --- Lectura y escritura (sin conocimiento del dominio) -----------------

    @staticmethod
    def _leer_json(ruta: str | os.PathLike) -> Any:
        ruta = Path(ruta)
        try:
            with open(ruta, "r", encoding="utf-8-sig") as archivo:
                return json.load(
                    archivo,
                    parse_constant=_rechazar_constante,
                    object_pairs_hook=_sin_claves_repetidas,
                )
        except FileNotFoundError as error:
            raise StorageFileNotFoundError(f"No se encontro el archivo: {ruta}") from error
        except json.JSONDecodeError as error:
            raise InvalidJSONError(
                f"JSON mal formado en {ruta} (linea {error.lineno}, "
                f"columna {error.colno}): {error.msg}"
            ) from error
        except UnicodeDecodeError as error:
            raise InvalidJSONError(f"{ruta} no esta codificado en UTF-8: {error}") from error
        except ValueError as error:
            raise InvalidJSONError(f"JSON invalido en {ruta}: {error}") from error
        except OSError as error:
            raise StorageAccessError(f"No se pudo leer {ruta}: {error}") from error

    def _escribir_json(self, datos: Any, ruta: str | os.PathLike) -> Path:
        ruta = Path(ruta)
        try:
            texto = json.dumps(datos, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        except (TypeError, ValueError) as error:  # defensa: _normalizar ya filtra
            raise IncompatibleStructureError(f"No se pudo serializar a JSON: {error}") from error

        if ruta.is_dir():
            raise StorageAccessError(f"La ruta de destino es una carpeta: {ruta}")

        temporal = None
        try:
            if self._create_dirs:
                ruta.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporal = tempfile.mkstemp(
                dir=ruta.parent, prefix=f".{ruta.name}.", suffix=".tmp"
            )
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
                archivo.write(texto)
                archivo.flush()
                os.fsync(archivo.fileno())
            # mkstemp crea el archivo con permisos 0600; se conservan los del
            # destino si existe, o se usan permisos normales de lectura.
            modo = stat.S_IMODE(ruta.stat().st_mode) if ruta.exists() else 0o644
            os.chmod(temporal, modo)
            os.replace(temporal, ruta)
            temporal = None
        except OSError as error:
            raise StorageAccessError(f"No se pudo escribir {ruta}: {error}") from error
        finally:
            if temporal is not None:
                with contextlib.suppress(OSError):
                    os.unlink(temporal)
        return ruta

    # --- Guardar / cargar un documento --------------------------------------

    def _guardar(self, datos: Any, ruta, tipo: str, etiqueta: str, validate) -> Path:
        copia = _normalizar(datos)
        if not isinstance(copia, dict):
            raise IncompatibleStructureError(
                f"{etiqueta}: se esperaba un objeto JSON (dict), no {type(datos).__name__}."
            )
        if self._debe_validar(validate):
            self._validar(copia, tipo, etiqueta)
        return self._escribir_json(copia, ruta)

    def _cargar(self, ruta, tipo: str, etiqueta: str, validate) -> dict:
        datos = self._leer_json(ruta)
        if not isinstance(datos, dict):
            raise IncompatibleStructureError(
                f"{etiqueta} en {ruta}: se esperaba un objeto JSON, no "
                f"{type(datos).__name__}."
            )
        if self._debe_validar(validate):
            self._validar(datos, tipo, f"{etiqueta} en {ruta}")
        return datos

    # Conocimiento del dominio

    def save_knowledge(self, knowledge: dict, path, *, validate: bool | None = None) -> Path:
        """Guarda un ``conocimiento_dominio`` en ``path`` y devuelve la ruta.

        Valida antes de escribir; si falla no se toca el archivo existente.
        """
        return self._guardar(knowledge, path, TIPO_CONOCIMIENTO, "El conocimiento", validate)

    def load_knowledge(self, path, *, validate: bool | None = None) -> dict:
        """Carga y valida un ``conocimiento_dominio`` desde ``path``."""
        return self._cargar(path, TIPO_CONOCIMIENTO, "El conocimiento", validate)

    # Sesiones (memoria de trabajo)

    def save_session(
        self,
        session: dict,
        path,
        *,
        knowledge: dict | None = None,
        validate: bool | None = None,
    ) -> Path:
        """Guarda una ``memoria_trabajo`` en ``path`` y devuelve la ruta.

        Si se pasa ``knowledge``, ademas se comprueba que los hechos existan
        en la base y respeten tipo, opciones y rango (``validar_memoria``).
        """
        copia = _normalizar(session)
        if not isinstance(copia, dict):
            raise IncompatibleStructureError(
                f"La sesion: se esperaba un objeto JSON (dict), no {type(session).__name__}."
            )
        if self._debe_validar(validate):
            self._validar(copia, TIPO_SESION, "La sesion")
            if knowledge is not None:
                self._validar_sesion_con_conocimiento(
                    copia, _normalizar(knowledge), "La sesion"
                )
        return self._escribir_json(copia, path)

    def load_session(
        self, path, *, knowledge: dict | None = None, validate: bool | None = None
    ) -> dict:
        """Carga y valida una ``memoria_trabajo`` desde ``path``."""
        sesion = self._cargar(path, TIPO_SESION, "La sesion", validate)
        if knowledge is not None and self._debe_validar(validate):
            self._validar_sesion_con_conocimiento(
                sesion, _normalizar(knowledge), f"La sesion en {path}"
            )
        return sesion

    # Sesiones identificadas por session_id dentro de una carpeta
    # (convencion propuesta, pendiente de acuerdo con G10 y G12)

    @staticmethod
    def session_filename(session_id: str) -> str:
        """Nombre de archivo para un ``session_id``: ``sesion_<session_id>.json``.

        Solo admite letras, digitos, punto, guion y guion bajo (maximo 128
        caracteres, sin empezar por signo). Asi el nombre nunca contiene
        separadores de ruta y dos ids distintos no chocan entre si.
        """
        if not isinstance(session_id, str) or not _PATRON_ID_SESION.match(session_id):
            raise ValueError(
                f"session_id no admitido para un nombre de archivo: {session_id!r}. "
                "Use letras, digitos, '.', '-' o '_' (maximo 128 caracteres)."
            )
        return f"{PREFIJO_SESION}{session_id}{EXTENSION}"

    def session_path(self, directory, session_id: str) -> Path:
        """Ruta ``<directory>/sesion_<session_id>.json``."""
        return Path(directory) / self.session_filename(session_id)

    def save_session_to_dir(
        self, session: dict, directory, *, knowledge: dict | None = None,
        validate: bool | None = None,
    ) -> Path:
        """Guarda la sesion en ``directory`` nombrandola por su ``session_id``."""
        session_id = session.get("session_id") if isinstance(session, dict) else None
        ruta = self.session_path(directory, session_id)
        return self.save_session(session, ruta, knowledge=knowledge, validate=validate)

    def load_session_from_dir(
        self, directory, session_id: str, *, knowledge: dict | None = None,
        validate: bool | None = None,
    ) -> dict:
        """Carga la sesion ``session_id`` guardada en ``directory``.

        Comprueba que el ``session_id`` interno coincida con el del nombre.
        """
        ruta = self.session_path(directory, session_id)
        sesion = self.load_session(ruta, knowledge=knowledge, validate=validate)
        if sesion.get("session_id") != session_id:
            raise IncompatibleStructureError(
                f"El archivo {ruta} contiene la sesion {sesion.get('session_id')!r}, "
                f"no {session_id!r}."
            )
        return sesion

    def list_sessions(self, directory) -> list[str]:
        """``session_id`` de las sesiones guardadas en ``directory`` (orden alfabetico).

        Solo mira los nombres de archivo; no abre ni valida su contenido.
        """
        carpeta = Path(directory)
        if not carpeta.is_dir():
            raise StorageFileNotFoundError(f"No se encontro la carpeta: {carpeta}")
        ids = []
        for archivo in carpeta.glob(f"{PREFIJO_SESION}*{EXTENSION}"):
            session_id = archivo.name[len(PREFIJO_SESION):-len(EXTENSION)]
            if _PATRON_ID_SESION.match(session_id):
                ids.append(session_id)
        return sorted(ids)

    # Dictamen de salida (propuesta: el README pide confirmar si se persiste)

    def save_verdict(self, verdict: dict, path, *, validate: bool | None = None) -> Path:
        """Guarda un ``dictamen_salida``. Pendiente de confirmar con los demas grupos."""
        return self._guardar(verdict, path, TIPO_DICTAMEN, "El dictamen", validate)

    def load_verdict(self, path, *, validate: bool | None = None) -> dict:
        """Carga y valida un ``dictamen_salida``."""
        return self._cargar(path, TIPO_DICTAMEN, "El dictamen", validate)

    # --- Compatibilidad externa ---------------------------------------------
    #
    # No hay ningun formato externo acordado. Estos metodos solo ofrecen el
    # punto de enganche: cuando se defina un formato, se registra su
    # importador/exportador y ESBConverter se encarga de validar el resultado
    # contra el contrato. El JSON comun sigue siendo el formato interno.

    def register_format(
        self,
        name: str,
        *,
        importer: Callable[[Path], dict] | None = None,
        exporter: Callable[[dict, Path], None] | None = None,
    ) -> None:
        """Registra un formato externo de conocimiento.

        ``importer(path)`` debe devolver un ``conocimiento_dominio`` (dict).
        ``exporter(knowledge, path)`` debe escribir el formato externo.
        Cada uno documenta que campos transforma y que hace con los que no
        tienen correspondencia; no debe descartarlos en silencio.
        """
        nombre = name.strip().lower() if isinstance(name, str) else ""
        if not nombre:
            raise ValueError("El nombre del formato no puede estar vacio.")
        if nombre == "json":
            raise ValueError("'json' es el formato interno; no se registra como externo.")
        if importer is None and exporter is None:
            raise ValueError("Debe indicar al menos un importer o un exporter.")
        self._formatos[nombre] = (importer, exporter)

    def registered_formats(self) -> list[str]:
        """Nombres de los formatos externos registrados (vacio si no hay ninguno)."""
        return sorted(self._formatos)

    def _convertidor(self, formato: str, posicion: int, accion: str) -> Callable:
        nombre = formato.strip().lower() if isinstance(formato, str) else ""
        registro = self._formatos.get(nombre)
        funcion = registro[posicion] if registro else None
        if funcion is None:
            registrados = ", ".join(self.registered_formats()) or "ninguno"
            raise UnsupportedFormatError(
                f"No hay un convertidor para {accion} el formato {formato!r}. "
                f"Formatos registrados: {registrados}. La compatibilidad externa "
                "esta pendiente de acuerdo entre los grupos."
            )
        return funcion

    def import_knowledge(self, path, format: str, *, validate: bool | None = None) -> dict:
        """Convierte un archivo externo al ``conocimiento_dominio`` interno."""
        importer = self._convertidor(format, 0, "importar")
        ruta = Path(path)
        try:
            datos = importer(ruta)
        except StorageError:
            raise
        except FileNotFoundError as error:
            raise StorageFileNotFoundError(f"No se encontro el archivo: {ruta}") from error
        except OSError as error:
            raise StorageAccessError(f"No se pudo leer {ruta}: {error}") from error
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
            raise IncompatibleStructureError(
                f"El convertidor '{format}' no pudo transformar {ruta}: {error!r}"
            ) from error
        datos = _normalizar(datos)
        if not isinstance(datos, dict):
            raise IncompatibleStructureError(
                f"El convertidor '{format}' debe devolver un objeto, no {type(datos).__name__}."
            )
        if self._debe_validar(validate):
            self._validar(datos, TIPO_CONOCIMIENTO, f"El resultado de importar {format!r}")
        return datos

    def export_knowledge(
        self, knowledge: dict, path, format: str, *, validate: bool | None = None
    ) -> Path:
        """Convierte un ``conocimiento_dominio`` interno a un formato externo."""
        exporter = self._convertidor(format, 1, "exportar")
        copia = _normalizar(knowledge)
        if not isinstance(copia, dict):
            raise IncompatibleStructureError(
                f"El conocimiento: se esperaba un objeto JSON, no {type(knowledge).__name__}."
            )
        if self._debe_validar(validate):
            self._validar(copia, TIPO_CONOCIMIENTO, "El conocimiento a exportar")
        ruta = Path(path)
        try:
            exporter(copia, ruta)
        except StorageError:
            raise
        except OSError as error:
            raise StorageAccessError(f"No se pudo escribir {ruta}: {error}") from error
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
            raise IncompatibleStructureError(
                f"El convertidor '{format}' no pudo exportar a {ruta}: {error!r}"
            ) from error
        return ruta
