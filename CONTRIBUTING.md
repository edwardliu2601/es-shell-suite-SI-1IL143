# Cómo contribuir al proyecto

Este documento explica cómo trabajar dentro del repositorio.
Léelo completo antes de hacer tu primer cambio.

## Reglas básicas

1. **Nadie hace push directo** a `main` ni a `develop`.
2. Cada grupo trabaja **solo dentro de su carpeta** `grupo_XX_*/`.
3. Los archivos en `contracts/` se modifican **solo por acuerdo** de los 12 coordinadores.
4. Todo cambio entra por **Pull Request** con al menos 1 aprobación.
5. Los commits se escriben en español, en modo imperativo ("Agrega", "Corrige", "Documenta").

## Roles

- **Coordinador de grupo**: único miembro del grupo con permiso de escritura en el repo central. Revisa PRs de sus compañeros y hace merge.
- **Integrantes del grupo**: trabajan en un fork personal y abren PRs hacia la rama de su grupo.

## Ramas

- `main` → código estable, solo para integraciones finales.
- `develop` → integración continua de todos los grupos.
- `grupo-XX` → rama viva de cada grupo (ej. `grupo-01`, `grupo-02`).
- `grupo-XX/descripcion-corta` → rama de trabajo específico (ej. `grupo-01/validacion-atributos`).

## Flujo para coordinadores

```bash
# Clonar el repo (una sola vez)
git clone https://github.com/USUARIO/es-shell-suite-SI-1IL143.git
cd es-shell-suite-SI-1IL143

# Para cada cambio nuevo
git checkout develop
git pull
git checkout -b grupo-XX/mi-cambio

# ...trabajar...

git add .
git commit -m "Descripcion del cambio

Co-authored-by: Nombre Compañero <email@dominio.com>"
git push origin grupo-XX/mi-cambio
```

Luego, abrir Pull Request en GitHub hacia `develop`.

## Flujo para integrantes del grupo (fork)

1. Entrar al repo central en GitHub y clic en **Fork** arriba a la derecha.
2. Clonar tu fork:
   ```bash
   git clone https://github.com/TU-USUARIO/es-shell-suite-SI-1IL143.git
   cd es-shell-suite-SI-1IL143
   ```
3. Crear rama:
   ```bash
   git checkout -b mi-cambio
   ```
4. Trabajar, commitear, push a tu fork.
5. Abrir **Pull Request desde tu fork** hacia la rama `grupo-XX` del repo central.
6. El coordinador revisa y hace merge.

## Co-authored commits

Cuando un coordinador empuja trabajo hecho por un compañero, agrega al final del mensaje de commit:
Co-authored-by: Nombre Apellido correo@ejemplo.com

Una línea por coautor. GitHub los reconoce y aparecen en el historial.

## Convenciones de código

- Python 3.11+
- Nombres de archivos en `snake_case` (ej. `esb_questions.py`).
- Clases en `PascalCase` (ej. `QuestionEditor`).
- Funciones y variables en `snake_case`.
- Un PR = un cambio coherente. Nada de PRs gigantes que mezclen cosas.

## Pruebas

- Cada módulo debe incluir pruebas unitarias en su carpeta `tests/`.
- Antes de abrir PR, correr las pruebas localmente.
- Un PR sin pruebas no se aprueba.

## Contratos JSON

Los archivos en `contracts/` definen el acuerdo entre todos los grupos. Modificarlos requiere:

1. Abrir un **issue** describiendo el cambio propuesto.
2. Discusión abierta con los 12 coordinadores.
3. Aprobación del coordinador del Grupo 4 (dueño del esquema).
4. PR a `develop` con etiqueta `contracts`.
