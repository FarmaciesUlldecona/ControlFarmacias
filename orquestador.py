#!/usr/bin/env python
from __future__ import annotations

import argparse
import fnmatch
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime
from typing import Any

from orquestador_snapshot import SnapshotError, comparar_snapshots, tomar_snapshot


VERSION = "0.1.3"
EXIT_PAUSA = 2
EXIT_ERROR = 1


class OrquestadorError(RuntimeError):
    pass


def cargar_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OrquestadorError(f"No existe el archivo: {path}") from exc
    except json.JSONDecodeError as exc:
        raise OrquestadorError(f"JSON inválido en {path}: {exc}") from exc


def guardar_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def ejecutar(
    args: list[str],
    *,
    cwd: Path,
    input_text: str | None = None,
    timeout: int = 120,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd),
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise OrquestadorError(
            "Comando fallido:\n"
            + " ".join(args)
            + f"\nCódigo: {proc.returncode}"
            + f"\nSTDOUT:\n{proc.stdout[-6000:]}"
            + f"\nSTDERR:\n{proc.stderr[-6000:]}"
        )
    return proc


def git(repo: Path, *args: str, timeout: int = 120) -> str:
    proc = ejecutar(["git", *args], cwd=repo, timeout=timeout)
    return proc.stdout.strip()


def normalizar_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def coincide(path: str, patron: str) -> bool:
    path = normalizar_path(path)
    patron = normalizar_path(patron)
    # fnmatch en Windows puede ser sensible a separadores; ya los normalizamos.
    return fnmatch.fnmatchcase(path, patron)


def validar_rutas(
    changed: set[str],
    *,
    rutas_permitidas: list[str],
    rutas_protegidas: list[str],
    permitir_escritura: bool,
) -> tuple[bool, list[str]]:
    problemas: list[str] = []

    for path in sorted(changed):
        if any(coincide(path, p) for p in rutas_protegidas):
            problemas.append(f"Ruta protegida modificada: {path}")
            continue

        if not permitir_escritura:
            problemas.append(f"Cambio no permitido en modo solo lectura: {path}")
            continue

        if rutas_permitidas and not any(coincide(path, p) for p in rutas_permitidas):
            problemas.append(f"Cambio fuera de la allowlist: {path}")

    return (len(problemas) == 0, problemas)


def estado_git(repo: Path) -> dict[str, Any]:
    return {
        "branch": git(repo, "branch", "--show-current"),
        "head": git(repo, "rev-parse", "HEAD"),
        "status": git(repo, "status", "--short", "--untracked-files=all"),
        "staged": git(repo, "diff", "--cached", "--name-only"),
    }


def crear_pausa(
    run_dir: Path,
    *,
    motivo: str,
    pregunta: str = "",
    opciones: list[str] | None = None,
    detalle: str = "",
) -> None:
    opciones = opciones or []
    lines = [
        "# PAUSA — requiere decisión de Pio",
        "",
        f"**Motivo:** {motivo}",
        "",
    ]
    if pregunta:
        lines += [f"**Pregunta:** {pregunta}", ""]
    if opciones:
        lines += ["## Opciones"]
        for opcion in opciones:
            lines.append(f"- {opcion}")
        lines.append("")
    if detalle:
        lines += ["## Detalle", detalle, ""]
    lines += [
        "## Cómo continuar",
        "",
        "1. Revisa esta pausa con ChatGPT.",
        "2. Decide qué quieres hacer.",
        "3. Continúa con:",
        "",
        "```powershell",
        f'python "{Path(__file__).resolve()}" --resume "{run_dir}" --decision "TU DECISION"',
        "```",
        "",
        "El orquestador no ejecutará nada más hasta recibir esa decisión.",
        "",
    ]
    (run_dir / "PAUSA_PIO.md").write_text("\n".join(lines), encoding="utf-8")


def cargar_reglas(base_dir: Path) -> str:
    return (base_dir / "prompts" / "reglas_supervisor.md").read_text(encoding="utf-8")


def construir_prompt_ejecutor(
    *,
    tarea: dict[str, Any],
    reglas: str,
    instruccion: str,
    ciclo: int,
    decision_pio: str | None = None,
) -> str:
    decision = decision_pio or "(ninguna decisión nueva de Pio)"
    rutas = "\n".join(f"- {p}" for p in tarea.get("rutas_permitidas", [])) or "- ninguna"
    return f"""
Eres el EJECUTOR técnico de ControlFarmacias dentro de un orquestador supervisado.

CICLO: {ciclo}

OBJETIVO APROBADO POR PIO:
{tarea["objetivo"]}

CRITERIO DE FINALIZACIÓN:
{tarea.get("criterio_finalizacion", "Completar únicamente el objetivo aprobado.")}

CONTEXTO:
{tarea.get("contexto", "")}

INSTRUCCIÓN MECÁNICA ACTUAL:
{instruccion}

ÚLTIMA DECISIÓN EXPRESA DE PIO:
{decision}

RUTAS DE ESCRITURA AUTORIZADAS PARA ESTA TAREA:
{rutas}

REGLAS PERMANENTES:
{reglas}

OBLIGACIONES DE ESTE TURNO:
1. Ejecuta únicamente el paso mecánico solicitado y ya autorizado.
2. No amplíes el alcance.
3. Si aparece una decisión de negocio, arquitectura, representación de datos, heurística dudosa,
   cambio de modelo/prompt/schema, nueva llamada IA externa, acceso a SQL/Farmatic/Supabase,
   cambio de patrón, dependencia nueva, red, commit/push o una discrepancia que requiera criterio,
   NO la resuelvas: devuelve estado REQUIERE_OK_PIO.
4. No hagas git add, commit ni push.
5. No intentes pedir permisos: trabaja dentro del sandbox disponible.
6. Devuelve tu respuesta final estrictamente según el JSON Schema suministrado.
""".strip()


def construir_prompt_supervisor(
    *,
    tarea: dict[str, Any],
    reglas: str,
    resultado_ejecutor: dict[str, Any],
    changed_paths: set[str],
    estado_antes: dict[str, Any],
    estado_despues: dict[str, Any],
    ciclo: int,
) -> str:
    return f"""
Eres el SUPERVISOR de ControlFarmacias. Estás en modo READ-ONLY.
Tu función NO es programar ni arreglar nada. Tu función es decidir si el trabajo puede continuar
automáticamente o si Pio debe decidir.

CICLO: {ciclo}

OBJETIVO APROBADO:
{tarea["objetivo"]}

CRITERIO DE FINALIZACIÓN:
{tarea.get("criterio_finalizacion", "")}

CONTEXTO:
{tarea.get("contexto", "")}

REGLAS PERMANENTES:
{reglas}

RESULTADO ESTRUCTURADO DEL EJECUTOR:
{json.dumps(resultado_ejecutor, ensure_ascii=False, indent=2)}

RUTAS CAMBIADAS DETECTADAS POR EL ORQUESTADOR:
{json.dumps(sorted(changed_paths), ensure_ascii=False, indent=2)}

ESTADO GIT ANTES DEL CICLO:
{json.dumps(estado_antes, ensure_ascii=False, indent=2)}

ESTADO GIT DESPUÉS DEL CICLO:
{json.dumps(estado_despues, ensure_ascii=False, indent=2)}

DECISIÓN:
- AUTO_CONTINUE solo si el siguiente paso es inequívocamente mecánico, reversible, local,
  ya implícitamente autorizado por el objetivo y no requiere ninguna decisión nueva.
- REQUIERE_OK_PIO ante cualquier ambigüedad, cambio de criterio, arquitectura, negocio,
  datos, representación, seguridad, costes, IA externa, acceso a sistemas, patrón, git publicado,
  dependencia, red, regresión, test inesperado o nueva capacidad no previamente autorizada.
- FINALIZADO si el objetivo aprobado ya está satisfecho y no hay nada mecánico pendiente.

Si eliges AUTO_CONTINUE, "siguiente_instruccion" debe ser concreta, pequeña y ejecutable.
Si eliges REQUIERE_OK_PIO, formula una sola decisión clara para Pio y, cuando sea útil,
ofrece opciones concretas.
No modifiques archivos.
Devuelve estrictamente el JSON Schema suministrado.
""".strip()


def invocar_codex(
    *,
    codex_exe: str,
    repo: Path,
    sandbox: str,
    schema: Path,
    output_path: Path,
    prompt: str,
    timeout: int,
    model: str | None,
) -> dict[str, Any]:
    # Los flags de política/entorno son GLOBALES en Codex CLI y deben
    # situarse antes del subcomando "exec". Los flags de salida estructurada
    # pertenecen a "codex exec" y van después.
    cmd = [
        codex_exe,
        "--cd",
        str(repo),
        "--sandbox",
        sandbox,
        "--ask-for-approval",
        "never",
    ]
    if model:
        cmd += ["--model", model]

    cmd += [
        "exec",
        "--output-schema",
        str(schema),
        "--output-last-message",
        str(output_path),
        "-",
    ]

    # En Windows, una instalación global vía npm suele resolver "codex" a
    # codex.CMD. subprocess/CreateProcess no ejecuta directamente .CMD/.BAT
    # cuando shell=False, por lo que debemos pasar ese wrapper por cmd.exe.
    resolved_codex = shutil.which(codex_exe) or codex_exe
    suffix = Path(resolved_codex).suffix.lower()

    if os.name == "nt" and suffix in (".cmd", ".bat"):
        # Conservamos todos los argumentos como lista y dejamos que
        # subprocess.list2cmdline construya una línea compatible con cmd.exe.
        codex_cmd = [resolved_codex, *cmd[1:]]
        command_line = subprocess.list2cmdline(codex_cmd)
        launch_cmd = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command_line]
    else:
        launch_cmd = [resolved_codex, *cmd[1:]]

    proc = ejecutar(
        launch_cmd,
        cwd=repo,
        input_text=prompt,
        timeout=timeout,
        check=False,
    )

    (output_path.parent / f"{output_path.stem}.stdout.txt").write_text(
        proc.stdout, encoding="utf-8"
    )
    (output_path.parent / f"{output_path.stem}.stderr.txt").write_text(
        proc.stderr, encoding="utf-8"
    )

    if proc.returncode != 0:
        raise OrquestadorError(
            f"Codex terminó con código {proc.returncode}. "
            f"Revisa {output_path.parent / (output_path.stem + '.stderr.txt')}"
        )

    try:
        return cargar_json(output_path)
    except OrquestadorError as exc:
        raise OrquestadorError(
            f"Codex no produjo JSON válido en {output_path}: {exc}"
        ) from exc


def comprobar_entorno(config: dict[str, Any], base_dir: Path) -> Path:
    repo = Path(config["repo"]).expanduser()
    if not repo.exists():
        raise OrquestadorError(f"No existe el repositorio configurado: {repo}")
    if not (repo / ".git").exists():
        raise OrquestadorError(f"No parece un repositorio Git: {repo}")

    codex_exe = config.get("codex_exe", "codex")
    if shutil.which(codex_exe) is None:
        raise OrquestadorError(
            f"No encuentro '{codex_exe}' en PATH. Abre PowerShell y comprueba: codex --version"
        )

    for rel in (
        "schemas/executor.schema.json",
        "schemas/supervisor.schema.json",
        "prompts/reglas_supervisor.md",
    ):
        if not (base_dir / rel).exists():
            raise OrquestadorError(f"Falta archivo del orquestador: {rel}")
    return repo


def validar_tarea(tarea: dict[str, Any]) -> None:
    if not tarea.get("id"):
        raise OrquestadorError("La tarea necesita 'id'.")
    if not tarea.get("objetivo"):
        raise OrquestadorError("La tarea necesita 'objetivo'.")
    modo = tarea.get("modo", "read_only")
    if modo not in ("read_only", "workspace_write"):
        raise OrquestadorError("modo debe ser read_only o workspace_write.")
    if modo == "workspace_write" and not tarea.get("rutas_permitidas"):
        raise OrquestadorError(
            "Una tarea workspace_write necesita rutas_permitidas explícitas."
        )


def ejecutar_ciclo(
    *,
    base_dir: Path,
    config: dict[str, Any],
    tarea: dict[str, Any],
    state: dict[str, Any],
    run_dir: Path,
    decision_pio: str | None,
) -> tuple[str, dict[str, Any]]:
    repo = Path(config["repo"])
    reglas = cargar_reglas(base_dir)
    ciclo = int(state["ciclo"]) + 1
    cycle_dir = run_dir / f"ciclo_{ciclo:02d}"
    cycle_dir.mkdir(parents=True, exist_ok=True)

    estado_previo = estado_git(repo)

    # Barreras de Git: el orquestador nunca debe moverse de rama/HEAD por sí mismo.
    if estado_previo["head"] != state["head_inicial"]:
        crear_pausa(
            run_dir,
            motivo="HEAD cambió desde el inicio del run.",
            detalle=f"Inicial: {state['head_inicial']}\nActual: {estado_previo['head']}",
        )
        return "REQUIERE_OK_PIO", state

    instruccion = state.get("siguiente_instruccion") or tarea["objetivo"]
    prompt_executor = construir_prompt_ejecutor(
        tarea=tarea,
        reglas=reglas,
        instruccion=instruccion,
        ciclo=ciclo,
        decision_pio=decision_pio,
    )
    (cycle_dir / "prompt_ejecutor.md").write_text(prompt_executor, encoding="utf-8")

    sandbox = "workspace-write" if tarea.get("modo") == "workspace_write" else "read-only"
    # Línea base inmediata: los cambios preexistentes no se atribuyen al ciclo.
    snapshot_antes = tomar_snapshot(repo)
    estado_antes = snapshot_antes.estado_git()
    executor_result = invocar_codex(
        codex_exe=config.get("codex_exe", "codex"),
        repo=repo,
        sandbox=sandbox,
        schema=base_dir / "schemas" / "executor.schema.json",
        output_path=cycle_dir / "resultado_ejecutor.json",
        prompt=prompt_executor,
        timeout=int(config.get("timeout_seconds", 1800)),
        model=config.get("modelo") or None,
    )

    snapshot_despues_ejecutor = tomar_snapshot(repo)
    cambios_ejecutor = comparar_snapshots(snapshot_antes, snapshot_despues_ejecutor)
    estado_despues_ejecutor = snapshot_despues_ejecutor.estado_git()
    changed = cambios_ejecutor.paths_cambiados

    ok_paths, problemas_paths = validar_rutas(
        changed,
        rutas_permitidas=tarea.get("rutas_permitidas", []),
        rutas_protegidas=config.get("rutas_protegidas", []),
        permitir_escritura=(tarea.get("modo") == "workspace_write"),
    )

    # Barreras duras: cualquier violación detiene ANTES del revisor.
    hard_errors: list[str] = []
    if not ok_paths:
        hard_errors.extend(problemas_paths)
    if cambios_ejecutor.cambio_head:
        hard_errors.append("Codex cambió HEAD/creó un commit, acción prohibida en V0.")
    if cambios_ejecutor.cambio_rama:
        hard_errors.append("Codex cambió de rama, acción prohibida en V0.")
    if cambios_ejecutor.cambio_staged:
        hard_errors.append("Cambió el índice Git (git add/staging), acción prohibida en V0.")

    if hard_errors:
        crear_pausa(
            run_dir,
            motivo="Barrera dura del orquestador activada.",
            pregunta="¿Cómo quieres proceder tras esta desviación?",
            detalle="\n".join(f"- {x}" for x in hard_errors),
        )
        state["ciclo"] = ciclo
        state["status"] = "REQUIERE_OK_PIO"
        guardar_json(run_dir / "state.json", state)
        return "REQUIERE_OK_PIO", state

    if executor_result.get("estado") in ("REQUIERE_OK_PIO", "BLOQUEADO"):
        crear_pausa(
            run_dir,
            motivo=executor_result.get("resumen", "El ejecutor ha solicitado detenerse."),
            pregunta=executor_result.get("pregunta_para_pio", ""),
            opciones=executor_result.get("opciones_para_pio", []),
            detalle=executor_result.get("detalle", ""),
        )
        state["ciclo"] = ciclo
        state["status"] = "REQUIERE_OK_PIO"
        guardar_json(run_dir / "state.json", state)
        return "REQUIERE_OK_PIO", state

    prompt_supervisor = construir_prompt_supervisor(
        tarea=tarea,
        reglas=reglas,
        resultado_ejecutor=executor_result,
        changed_paths=changed,
        estado_antes=estado_antes,
        estado_despues=estado_despues_ejecutor,
        ciclo=ciclo,
    )
    (cycle_dir / "prompt_supervisor.md").write_text(prompt_supervisor, encoding="utf-8")

    supervisor_result = invocar_codex(
        codex_exe=config.get("codex_exe", "codex"),
        repo=repo,
        sandbox="read-only",
        schema=base_dir / "schemas" / "supervisor.schema.json",
        output_path=cycle_dir / "decision_supervisor.json",
        prompt=prompt_supervisor,
        timeout=int(config.get("timeout_seconds", 1800)),
        model=config.get("modelo_supervisor") or config.get("modelo") or None,
    )

    snapshot_final_ciclo = tomar_snapshot(repo)
    cambios_supervisor = comparar_snapshots(
        snapshot_despues_ejecutor, snapshot_final_ciclo
    )
    estado_final_ciclo = snapshot_final_ciclo.estado_git()
    # El supervisor es read-only: cualquier cambio del workspace o Git pausa.
    if cambios_supervisor.hay_cambios:
        crear_pausa(
            run_dir,
            motivo="El estado Git cambió durante el turno read-only del supervisor.",
            detalle=json.dumps(
                {
                    "antes_supervisor": estado_despues_ejecutor,
                    "despues_supervisor": estado_final_ciclo,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        state["ciclo"] = ciclo
        state["status"] = "REQUIERE_OK_PIO"
        guardar_json(run_dir / "state.json", state)
        return "REQUIERE_OK_PIO", state

    decision = supervisor_result.get("estado")
    state["ciclo"] = ciclo
    state["ultima_decision_supervisor"] = supervisor_result
    state["decision_pio_consumida"] = decision_pio or ""
    state["status"] = decision

    if decision == "AUTO_CONTINUE":
        next_instruction = supervisor_result.get("siguiente_instruccion", "").strip()
        if not next_instruction:
            crear_pausa(
                run_dir,
                motivo="Supervisor pidió AUTO_CONTINUE pero no dio siguiente instrucción.",
            )
            state["status"] = "REQUIERE_OK_PIO"
            guardar_json(run_dir / "state.json", state)
            return "REQUIERE_OK_PIO", state
        state["siguiente_instruccion"] = next_instruction
        guardar_json(run_dir / "state.json", state)
        return "AUTO_CONTINUE", state

    if decision == "FINALIZADO":
        summary = [
            "# Orquestación finalizada",
            "",
            f"Tarea: **{tarea['id']}**",
            "",
            supervisor_result.get("motivo", "Objetivo completado."),
            "",
            f"Ciclos ejecutados: {ciclo}",
            "",
            "No se ha realizado commit ni push.",
            "",
        ]
        (run_dir / "FINALIZADO.md").write_text("\n".join(summary), encoding="utf-8")
        guardar_json(run_dir / "state.json", state)
        return "FINALIZADO", state

    crear_pausa(
        run_dir,
        motivo=supervisor_result.get("motivo", "El supervisor requiere decisión de Pio."),
        pregunta=supervisor_result.get("pregunta_para_pio", ""),
        opciones=supervisor_result.get("opciones_para_pio", []),
        detalle=supervisor_result.get("detalle", ""),
    )
    state["status"] = "REQUIERE_OK_PIO"
    guardar_json(run_dir / "state.json", state)
    return "REQUIERE_OK_PIO", state


def nuevo_run(
    *,
    base_dir: Path,
    config: dict[str, Any],
    tarea_path: Path,
) -> int:
    tarea = cargar_json(tarea_path)
    validar_tarea(tarea)
    repo = comprobar_entorno(config, base_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in tarea["id"])
    run_dir = base_dir / "runs" / f"{timestamp}_{safe_id}"
    run_dir.mkdir(parents=True, exist_ok=False)

    estado = estado_git(repo)
    state = {
        "version": VERSION,
        "task_path": str(tarea_path.resolve()),
        "run_dir": str(run_dir.resolve()),
        "ciclo": 0,
        "status": "INICIADO",
        "head_inicial": estado["head"],
        "branch_inicial": estado["branch"],
        "siguiente_instruccion": tarea["objetivo"],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    guardar_json(run_dir / "state.json", state)
    guardar_json(run_dir / "tarea_snapshot.json", tarea)

    max_cycles = int(tarea.get("max_ciclos", config.get("max_ciclos_default", 5)))
    decision_pio = None

    print(f"[Orquestador V{VERSION}] Run: {run_dir}")
    print(f"Repo: {repo}")
    print(f"HEAD: {estado['head']}")
    print(f"Modo: {tarea.get('modo', 'read_only')}")
    print()

    while state["ciclo"] < max_cycles:
        status, state = ejecutar_ciclo(
            base_dir=base_dir,
            config=config,
            tarea=tarea,
            state=state,
            run_dir=run_dir,
            decision_pio=decision_pio,
        )
        decision_pio = None

        print(f"Ciclo {state['ciclo']}: {status}")

        if status == "AUTO_CONTINUE":
            continue
        if status == "FINALIZADO":
            print(f"FINALIZADO: {run_dir / 'FINALIZADO.md'}")
            return 0
        print(f"PAUSA: {run_dir / 'PAUSA_PIO.md'}")
        return EXIT_PAUSA

    crear_pausa(
        run_dir,
        motivo=f"Se alcanzó el máximo de {max_cycles} ciclos automáticos.",
        pregunta="¿Autorizas continuar con más ciclos o prefieres revisar el estado?",
    )
    state["status"] = "REQUIERE_OK_PIO"
    guardar_json(run_dir / "state.json", state)
    print(f"PAUSA por máximo de ciclos: {run_dir / 'PAUSA_PIO.md'}")
    return EXIT_PAUSA


def reanudar_run(
    *,
    base_dir: Path,
    config: dict[str, Any],
    run_dir: Path,
    decision: str,
) -> int:
    if not decision.strip():
        raise OrquestadorError("--decision no puede estar vacío.")

    state = cargar_json(run_dir / "state.json")
    tarea = cargar_json(run_dir / "tarea_snapshot.json")
    validar_tarea(tarea)
    comprobar_entorno(config, base_dir)

    if state.get("status") != "REQUIERE_OK_PIO":
        raise OrquestadorError(
            f"El run no está pausado. Estado actual: {state.get('status')}"
        )

    # Conservamos la pausa histórica pero indicamos que fue atendida.
    pause = run_dir / "PAUSA_PIO.md"
    if pause.exists():
        attended = run_dir / f"PAUSA_PIO_ATENDIDA_ciclo_{state['ciclo']:02d}.md"
        if not attended.exists():
            pause.replace(attended)

    # La decisión humana no relaja barreras absolutas.
    state["status"] = "REANUDADO"
    state["siguiente_instruccion"] = (
        "Continúa desde el punto pausado aplicando EXCLUSIVAMENTE esta decisión expresa de Pio:\n"
        + decision.strip()
        + "\nNo amplíes el alcance."
    )
    guardar_json(run_dir / "state.json", state)

    max_cycles = int(tarea.get("max_ciclos", config.get("max_ciclos_default", 5)))
    # Al reanudar permitimos hasta max_cycles adicionales al contador actual.
    limite = state["ciclo"] + max_cycles
    decision_pio = decision.strip()

    print(f"Reanudando: {run_dir}")
    print(f"Decisión Pio: {decision_pio}")

    while state["ciclo"] < limite:
        status, state = ejecutar_ciclo(
            base_dir=base_dir,
            config=config,
            tarea=tarea,
            state=state,
            run_dir=run_dir,
            decision_pio=decision_pio,
        )
        decision_pio = None

        print(f"Ciclo {state['ciclo']}: {status}")

        if status == "AUTO_CONTINUE":
            continue
        if status == "FINALIZADO":
            print(f"FINALIZADO: {run_dir / 'FINALIZADO.md'}")
            return 0
        print(f"PAUSA: {run_dir / 'PAUSA_PIO.md'}")
        return EXIT_PAUSA

    crear_pausa(
        run_dir,
        motivo=f"Se alcanzó el máximo de {max_cycles} ciclos adicionales.",
        pregunta="¿Autorizas continuar o prefieres revisar?",
    )
    state["status"] = "REQUIERE_OK_PIO"
    guardar_json(run_dir / "state.json", state)
    return EXIT_PAUSA


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Orquestador supervisado ControlFarmacias → Codex"
    )
    parser.add_argument("--task", type=Path, help="JSON de tarea nueva.")
    parser.add_argument("--resume", type=Path, help="Directorio de run pausado.")
    parser.add_argument("--decision", type=str, help="Decisión expresa de Pio al reanudar.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().with_name("config.json"),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Comprueba entorno/configuración sin ejecutar Codex.",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    config = cargar_json(args.config)

    try:
        if args.check:
            repo = comprobar_entorno(config, base_dir)
            print(f"OK Orquestador V{VERSION}")
            print(f"Repo: {repo}")
            print(f"Codex: {shutil.which(config.get('codex_exe', 'codex'))}")
            print(f"Git HEAD: {git(repo, 'rev-parse', 'HEAD')}")
            print("No se ejecutó ninguna tarea.")
            return 0

        if args.resume:
            if not args.decision:
                raise OrquestadorError("--resume requiere --decision.")
            return reanudar_run(
                base_dir=base_dir,
                config=config,
                run_dir=args.resume.resolve(),
                decision=args.decision,
            )

        if args.task:
            return nuevo_run(
                base_dir=base_dir,
                config=config,
                tarea_path=args.task.resolve(),
            )

        parser.error("Usa --task, --resume o --check.")
        return EXIT_ERROR

    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario. No se reanuda automáticamente.")
        return 130
    except (OrquestadorError, SnapshotError, subprocess.TimeoutExpired) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
