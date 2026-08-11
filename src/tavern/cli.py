"""Tavern CLI entry point.

Subcommands:
  tavern validate <path>              — validate a worldpack
  tavern install <path>               — install a worldpack into ~/.config/tavern/worlds/
  tavern list                         — list installed worldpacks
  tavern uninstall <world-id>         — remove an installed worldpack
  tavern config init|show|check|path  — manage LLM configuration
  tavern play <world-id>              — play an installed world (M0 REPL)
  tavern saves                        — list save files
  tavern export novel <save-name>     — rewrite a save into a prose novel
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tavern import __version__
from tavern.export import ExportError, export_novel
from tavern.llm import LLMError, load_provider
from tavern.llmconfig import (
    InitAborted,
    InitError,
    check_config,
    config_path,
    init_interactive,
    is_secret_field,
    load_config,
    load_config_raw,
    mask_secret,
)
from tavern.repl import (
    INPUT_SYNTAX_PROMPT,
    build_system_prompt,
    build_turn_messages,
    parse_input,
    readline_wide,
    render_inv,
    render_relations,
    render_status,
    render_where,
    render_who,
)
from tavern.roles.memory_keeper import compress as memory_keeper_compress
from tavern.save import (
    Save,
    SaveError,
    SaveExistsError,
    SaveNameError,
    SaveNotFoundError,
    SchemaMismatchError,
    delete_save,
    list_saves,
    save_path,
)
from tavern.worldpack.diagnostics import render_report
from tavern.worldpack.install import (
    InstallError,
    InstalledWorld,
    install,
    list_installed,
    uninstall,
)
from tavern.worldpack.loader import load_worldpack
from tavern.worldpack.schema import WorldPack
from tavern.worldpack.validator import validate_worldpack


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tavern",
        description="Tavern — CLI-native, LLM-driven interactive narrative engine",
    )
    parser.add_argument("--version", action="version", version=f"tavern {__version__}")

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_validate = sub.add_parser(
        "validate", help="validate a worldpack (single world.toml or directory)"
    )
    p_validate.add_argument("path", type=Path, help="path to world.toml or worldpack directory")
    p_validate.add_argument("--strict", action="store_true", help="treat warnings as failures")
    p_validate.add_argument("--verbose", "-v", action="store_true", help="print info diagnostics too")

    p_install = sub.add_parser(
        "install", help="install a worldpack from a file, directory, or archive"
    )
    p_install.add_argument(
        "path", type=Path, help="world.toml, worldpack directory, .tar.gz, or .zip"
    )
    p_install.add_argument(
        "--force", action="store_true",
        help="overwrite an existing world with the same id, or install despite validation errors",
    )
    p_install.add_argument(
        "--no-validate", action="store_true", help="skip validation (not recommended)",
    )

    p_list = sub.add_parser("list", help="list installed worldpacks")
    p_list.add_argument("--long", "-l", action="store_true", help="show full details")

    p_uninstall = sub.add_parser("uninstall", help="remove an installed worldpack")
    p_uninstall.add_argument("world_id", help="the id of the world to remove")
    p_uninstall.add_argument("--yes", "-y", action="store_true", help="skip confirmation")

    p_config = sub.add_parser("config", help="manage LLM configuration")
    config_sub = p_config.add_subparsers(dest="config_command", metavar="<sub>")

    p_ci = config_sub.add_parser("init", help="interactive setup wizard")
    p_ci.add_argument("--force", action="store_true", help="overwrite existing config")
    p_ci.add_argument(
        "--provider", help="skip provider prompt (still asks for key/model)"
    )

    p_cs = config_sub.add_parser("show", help="display current configuration (masked)")
    p_cs.add_argument(
        "--reveal", action="store_true",
        help="show secrets in plain text (careful — do not screenshot)",
    )

    config_sub.add_parser("check", help="validate config.toml syntax and fields")
    config_sub.add_parser("path", help="print the absolute path of config.toml")

    p_play = sub.add_parser(
        "play", help="play an installed world (M0: single-provider REPL)"
    )
    p_play.add_argument("world_id", help="the id of an installed world")
    p_play.add_argument(
        "--provider", default="default",
        help="which [llm.<role>] config to use (default: 'default')",
    )
    p_play.add_argument(
        "--save", default=None,
        help="save name to open or create (default: 'default-<world-id>')",
    )
    p_play.add_argument(
        "--new", action="store_true",
        help="force a fresh save (deletes the existing default save first)",
    )

    p_saves = sub.add_parser("saves", help="list save files")
    p_saves.add_argument("--long", "-l", action="store_true", help="show full details")

    p_export = sub.add_parser("export", help="export a save to another format")
    export_sub = p_export.add_subparsers(dest="export_command", metavar="<format>")
    p_novel = export_sub.add_parser("novel", help="rewrite a save into a prose novel")
    p_novel.add_argument("save_name", help="the name of a save (see `tavern saves`)")
    p_novel.add_argument(
        "--output", type=Path, default=None,
        help="output markdown path (default: ~/tavern-novels/<save>-<timestamp>.md)",
    )
    p_novel.add_argument(
        "--provider", default=None,
        help="LLM role to use (default: 'export' if configured, else 'default')",
    )
    p_novel.add_argument(
        "--force", action="store_true", help="overwrite the output file if it exists",
    )

    return parser


# ── validate ─────────────────────────────────────────────────────────────


def _cmd_validate(args) -> int:
    path: Path = args.path
    if not path.exists():
        print(f"tavern: path does not exist: {path}", file=sys.stderr)
        return 2

    report = validate_worldpack(path)
    render_report(report, verbose=args.verbose)

    if not report.ok:
        return 1
    if args.strict and report.warnings:
        return 1
    return 0


# ── install ──────────────────────────────────────────────────────────────


def _cmd_install(args) -> int:
    path: Path = args.path
    if not path.exists():
        print(f"tavern: source path does not exist: {path}", file=sys.stderr)
        return 2

    try:
        installed = install(
            path,
            force=args.force,
            skip_validate=args.no_validate,
        )
    except InstallError as exc:
        print(f"tavern install: {exc}", file=sys.stderr)
        return 1

    print(
        f"installed world '{installed.id}' ({installed.name}) "
        f"v{installed.version} → {installed.path}"
    )
    return 0


# ── list ─────────────────────────────────────────────────────────────────


def _cmd_list(args) -> int:
    worlds = list_installed()
    if not worlds:
        print("No worlds installed. Use `tavern install <path>` to install one.")
        return 0

    if args.long:
        _render_list_long(worlds)
    else:
        _render_list_short(worlds)
    return 0


def _render_list_short(worlds: list[InstalledWorld]) -> None:
    id_w = max(len("ID"), *(len(w.id) for w in worlds))
    name_w = max(len("NAME"), *(_visual_width(w.name) for w in worlds))
    ver_w = max(len("VERSION"), *(len(w.version) for w in worlds))

    header = f"{'ID':<{id_w}}  {'NAME':<{name_w}}  {'VERSION':<{ver_w}}  TOKENS"
    print(header)
    for w in worlds:
        # simple string ljust doesn't know CJK width; pad manually
        name_padding = " " * (name_w - _visual_width(w.name))
        print(
            f"{w.id:<{id_w}}  {w.name}{name_padding}  "
            f"{w.version:<{ver_w}}  ~{w.estimated_tokens}"
        )


def _render_list_long(worlds: list[InstalledWorld]) -> None:
    for w in worlds:
        print(w.id)
        print(f"  name       : {w.name}")
        print(f"  version    : {w.version}")
        print(f"  tokens     : ~{w.estimated_tokens}")
        print(f"  path       : {w.path}")
        print(f"  installed  : {w.installed_at}")
        print(f"  source     : {w.source}")
        print(f"  source_type: {w.source_type}")
        print()


def _visual_width(s: str) -> int:
    """Approximate terminal display width: CJK chars count as 2."""
    width = 0
    for ch in s:
        code = ord(ch)
        if (
            0x1100 <= code <= 0x115F  # Hangul Jamo
            or 0x2E80 <= code <= 0x9FFF  # CJK
            or 0xAC00 <= code <= 0xD7A3
            or 0xF900 <= code <= 0xFAFF
            or 0xFF00 <= code <= 0xFF60
        ):
            width += 2
        else:
            width += 1
    return width


# ── uninstall ────────────────────────────────────────────────────────────


def _cmd_uninstall(args) -> int:
    try:
        # Peek at the target so we can render a nice confirm prompt.
        target = _peek_installed(args.world_id)
    except InstallError as exc:
        print(f"tavern uninstall: {exc}", file=sys.stderr)
        return 1

    if not args.yes:
        print(
            f"About to remove world '{target.id}' ({target.name} v{target.version})"
        )
        print(f"  path: {target.path}")
        try:
            answer = input("Continue? [y/N]: ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            print("Aborted.")
            return 0

    try:
        removed = uninstall(args.world_id)
    except InstallError as exc:
        print(f"tavern uninstall: {exc}", file=sys.stderr)
        return 1

    print(f"Removed world '{removed.id}'.")
    return 0


def _peek_installed(world_id: str) -> InstalledWorld:
    for w in list_installed():
        if w.id == world_id:
            return w
    raise InstallError(f"no installed world with id '{world_id}'", "not_found")


# ── config ───────────────────────────────────────────────────────────────


def _cmd_config(args) -> int:
    sub = args.config_command
    if sub == "init":
        return _cmd_config_init(args)
    if sub == "show":
        return _cmd_config_show(args)
    if sub == "check":
        return _cmd_config_check(args)
    if sub == "path":
        return _cmd_config_path(args)
    print(
        "tavern config: expected one of {init, show, check, path}",
        file=sys.stderr,
    )
    return 2


def _cmd_config_init(args) -> int:
    try:
        path = init_interactive(
            force=args.force,
            provider_hint=args.provider,
        )
    except InitError as exc:
        print(f"tavern config init: {exc}", file=sys.stderr)
        return 1
    except InitAborted:
        print("\nAborted.", file=sys.stderr)
        return 1

    print(f"\nConfiguration written to {path}.")
    return 0


def _cmd_config_show(args) -> int:
    try:
        raw = load_config_raw()
    except Exception as exc:
        print(f"tavern config show: {exc}", file=sys.stderr)
        return 1

    if not raw:
        print(f"No config file at {config_path()}.")
        print("Run `tavern config init` to create one.")
        return 1

    print(f"config: {config_path()}")
    if args.reveal:
        print("⚠ REVEAL MODE — do not screenshot or paste publicly.")
    print()

    for section_name, section in raw.items():
        if isinstance(section, dict) and _is_nested_table(section):
            for sub, body in section.items():
                if isinstance(body, dict):
                    print(f"[{section_name}.{sub}]")
                    _print_kv_block(body, reveal=args.reveal)
                    print()
        elif isinstance(section, dict):
            print(f"[{section_name}]")
            _print_kv_block(section, reveal=args.reveal)
            print()
    return 0


def _is_nested_table(d: dict) -> bool:
    """Return True if every value in d is itself a table.

    That's the shape of `[llm]` (which contains sub-tables like [llm.default]).
    """
    return bool(d) and all(isinstance(v, dict) for v in d.values())


def _print_kv_block(section: dict, *, reveal: bool) -> None:
    for k, v in section.items():
        if isinstance(v, str) and is_secret_field(k) and not reveal:
            v = mask_secret(v)
        if isinstance(v, str):
            print(f'  {k} = "{v}"')
        else:
            print(f"  {k} = {v!r}")


def _cmd_config_check(args) -> int:
    diags = check_config()

    n_err = 0
    n_warn = 0
    n_info = 0
    for d in diags:
        if d.level == "error":
            mark = "✗"
            n_err += 1
        elif d.level == "warning":
            mark = "⚠"
            n_warn += 1
        else:
            mark = "ℹ"
            n_info += 1
        print(f"{mark} {d.code}  {d.message}")
        if d.hint:
            print(f"     hint: {d.hint}")

    if n_err == 0:
        print("Config OK." if not diags else f"Config OK. ({n_warn} warning(s), {n_info} info)")
        return 0

    print(f"Config has {n_err} error(s), {n_warn} warning(s).")
    return 1


def _cmd_config_path(args) -> int:
    print(config_path())
    return 0


# ── play ─────────────────────────────────────────────────────────────────


def _cmd_play(args) -> int:
    world_id: str = args.world_id

    world = _find_installed_world(world_id)
    if world is None:
        print(
            f"tavern play: world '{world_id}' is not installed.\n"
            f"Run `tavern list` to see installed worlds, or "
            f"`tavern install <path>` to add one.",
            file=sys.stderr,
        )
        return 1

    result = load_worldpack(world.path)
    if result.pack is None:
        codes = ", ".join(e.code for e in result.errors) or "unknown"
        print(
            f"tavern play: world '{world_id}' is broken ({codes}); "
            f"run `tavern validate {world.path}` for details",
            file=sys.stderr,
        )
        return 1
    pack = result.pack

    try:
        provider = load_provider(args.provider)
    except LLMError as exc:
        print(f"tavern play: {exc}", file=sys.stderr)
        return 1

    try:
        save = _open_or_new_save(world_id, args.save, args.new)
    except SaveError as exc:
        print(f"tavern play: {exc}", file=sys.stderr)
        return 1

    try:
        _run_play_loop(pack, provider, save)
    finally:
        save.close()
    return 0


def _open_or_new_save(world_id: str, name: str | None, force_new: bool) -> Save:
    save_name = name if name else f"default-{world_id}"

    if force_new:
        # Only reset the default; if the user named a save, --new is refused.
        if name and name != f"default-{world_id}":
            raise SaveError("--new can only be combined with the default save")
        if save_path(save_name).exists():
            delete_save(save_name)

    if save_path(save_name).exists():
        return Save.open(save_name)
    return Save.new(save_name, world_id=world_id)


def _find_installed_world(world_id: str) -> InstalledWorld | None:
    for w in list_installed():
        if w.id == world_id:
            return w
    return None


# The active provider for the current REPL session — set by _run_play_loop
# so slash-command handlers can reach it without re-plumbing every signature.
_REPL_PROVIDER = None


def _run_play_loop(pack, provider, save: Save) -> None:
    global _REPL_PROVIDER
    _REPL_PROVIDER = provider
    tavern_name = pack.world.initial_tavern.get("name", "?")
    state = save.state

    header = f"── {pack.world.name} · {tavern_name} ──"
    header += f"  (save: {save.name} · {state.turn_count} turns)"
    print(header + "\n")

    if state.turn_count == 0:
        hook = str(pack.world.initial_tavern.get("opening_hook", "")).strip()
        if hook:
            print(hook)
            save.append_turn("system", hook, turn_no=0)
        print()
    else:
        print(f"── continuing from turn {state.turn_count} ──")
        for turn in save.recent_turns(6):
            if turn.role == "system":
                continue
            tag = "[player]" if turn.role == "player" else "[gm]"
            print(f"{tag} {turn.text}")
        print()

    print(f"(provider: {provider.describe()})")
    print("(type /help for commands, /quit to exit)\n")

    while True:
        try:
            line = readline_wide("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return
        if not line:
            continue

        intent = parse_input(line)

        if intent.kind == "slash":
            outcome = _handle_slash(intent.raw, save, pack)
            if outcome == "quit":
                return
            continue

        system_prompt, messages = build_turn_messages(save, pack, intent)
        try:
            reply = provider.complete(messages, system=system_prompt)
        except LLMError as exc:
            print(f"[error] {exc}", file=sys.stderr)
            continue

        turn_no = save.state.turn_count + 1
        # Persist the RAW input, not the LLM-facing line — novels + rewind
        # + replay all want what the player actually typed.
        save.append_turn("player", intent.raw, turn_no=turn_no)
        save.append_turn("gm", reply, turn_no=turn_no)
        save.update_state(turn_count=turn_no)
        print(f"\n{reply}\n")

        if _should_compress(save):
            _run_compression(save, provider, pack)


def _handle_slash(line: str, save: Save, pack) -> str:
    """Return 'quit' to exit REPL, otherwise 'continue'."""
    parts = line.split(maxsplit=1)
    cmd = parts[0]
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/quit", "/exit"):
        print("Goodbye.")
        return "quit"

    if cmd == "/help":
        _print_repl_help()
        return "continue"

    if cmd == "/save":
        return _handle_save(save, arg)

    if cmd == "/load":
        return _handle_load(save, arg)

    if cmd == "/saves":
        _render_saves(list_saves(), long=False)
        return "continue"

    if cmd == "/rewind":
        return _handle_rewind(save, arg)

    if cmd == "/export":
        return _handle_export(save, arg, pack)

    if cmd == "/where":
        print(render_where(pack, save))
        return "continue"

    if cmd == "/who":
        print(render_who(pack, save, arg))
        return "continue"

    if cmd == "/inv":
        print(render_inv(pack, save))
        return "continue"

    if cmd == "/status":
        print(render_status(pack, save))
        return "continue"

    if cmd == "/relations":
        print(render_relations(pack, save))
        return "continue"

    print(f"[unknown command] {cmd} — type /help")
    return "continue"


def _handle_save(save: Save, name: str) -> str:
    if not name:
        print(f"Saved. ({save.state.turn_count} turns in '{save.name}')")
        return "continue"
    try:
        new_save = save.copy_to(name)
    except SaveError as exc:
        print(f"[error] {exc}")
        return "continue"
    # switch to the copy so subsequent turns write there
    save.close()
    # in-place swap: we can't rebind the caller's variable from here, so
    # transfer state through save._conn — done via replacing save's fields.
    save._path = new_save.path
    save._conn = new_save._conn
    print(f"Saved to '{name}'. (now writing to this save)")
    return "continue"


def _handle_load(save: Save, name: str) -> str:
    if not name:
        print("[error] /load requires a save name — see /saves")
        return "continue"
    try:
        loaded = Save.open(name)
    except SaveError as exc:
        print(f"[error] {exc}")
        return "continue"

    save.close()
    save._path = loaded.path
    save._conn = loaded._conn
    print(f"Loaded '{name}'. (turn {save.state.turn_count})")
    # brief resume summary
    for turn in save.recent_turns(4):
        if turn.role == "system":
            continue
        tag = "[player]" if turn.role == "player" else "[gm]"
        print(f"  {tag} {turn.text[:80]}")
    return "continue"


def _handle_rewind(save: Save, arg: str) -> str:
    n = 1
    if arg:
        try:
            n = int(arg)
        except ValueError:
            print(f"[error] /rewind expects an integer, got {arg!r}")
            return "continue"
    if n <= 0:
        print("[error] /rewind N requires N >= 1")
        return "continue"
    if save.state.turn_count == 0:
        print("[error] nothing to rewind — no turns yet")
        return "continue"

    summary = save.summary()
    if summary is not None:
        target = save.state.turn_count - n
        if target <= summary.covered_up_to_turn:
            print(
                f"[error] cannot rewind past turn {summary.covered_up_to_turn} — "
                f"the world's memory of turns 1–{summary.covered_up_to_turn} "
                "has been consolidated. Load an earlier save if you need to go further back."
            )
            return "continue"

    before = save.state.turn_count
    save.rewind(n)
    after = save.state.turn_count
    print(f"Rewound {before - after} turn(s). (now at turn {after})")
    return "continue"


def _handle_export(save: Save, arg: str, pack) -> str:
    """Handle `/export novel [PATH]` inside the REPL.

    Reuses the current REPL's provider — we don't switch to the export role
    mid-session, since the user just picked a provider at boot.
    """
    parts = arg.split(maxsplit=1)
    if not parts or parts[0] != "novel":
        print("[error] usage: /export novel [PATH]")
        return "continue"
    out_path = None
    if len(parts) > 1 and parts[1].strip():
        out_path = Path(parts[1].strip()).expanduser()

    # Provider was set at REPL boot — reuse it via a closure trick.
    provider = _REPL_PROVIDER  # type: ignore[name-defined]

    try:
        result = export_novel(save, pack, provider, output=out_path, force=False)
    except ExportError as exc:
        print(f"[error] {exc}")
        return "continue"
    except LLMError as exc:
        print(f"[error] provider failed: {exc}")
        return "continue"

    print(
        f"Novel exported to {result.output_path} "
        f"({result.turn_count} turns, {result.chunk_count} chunk(s))"
    )
    return "continue"


def _print_repl_help() -> None:
    print("Input syntax:")
    print('  "..."             character speech')
    print("  *...*             internal thought")
    print("  :look :wait ...   shortcut actions (also :rest :inventory :map :recap)")
    print("  otherwise         free-form action")
    print()
    print("Observation commands:")
    print("  /where            show current scene")
    print("  /who [name]       list NPCs / describe one")
    print("  /inv              show inventory (not tracked yet)")
    print("  /status           show character status")
    print("  /relations        show NPC relationships (not tracked yet)")
    print()
    print("Save commands:")
    print("  /save [name]       save (copy to 'name' if given)")
    print("  /load <name>       load another save")
    print("  /saves             list all saves")
    print("  /rewind [N]        undo the last N turns (default 1)")
    print("  /export novel [PATH]  rewrite this save into a prose novel")
    print()
    print("Other:")
    print("  /help              this help")
    print("  /quit, /exit       exit")


def _build_system_prompt(pack) -> str:
    # Kept as a thin wrapper for callers (e.g. export/novel) that want the
    # world-static Narrator header without the summary/messages layer.
    return build_system_prompt(pack)


# ── compression: L2 memory (scene summary) ───────────────────────────────
#
# Triggered every 10 logical turns starting at turn 15. Each pass replaces
# the singleton scene_summary row with a new one, folding the prior summary
# together with turns since it was written. Runs synchronously — the player
# waits for one extra LLM call while `[the world remembers…]` is on screen.

_COMPRESSION_INTERVAL = 10
_COMPRESSION_FIRST_AT = 15
_RAW_KEEP = 5  # turns of raw context kept AFTER a compression cutoff


def _should_compress(save: Save) -> bool:
    turn_no = save.state.turn_count
    if turn_no < _COMPRESSION_FIRST_AT:
        return False
    if (turn_no - _COMPRESSION_FIRST_AT) % _COMPRESSION_INTERVAL != 0:
        return False
    cutoff_target = turn_no - _RAW_KEEP
    summary = save.summary()
    return summary is None or summary.covered_up_to_turn < cutoff_target


def _run_compression(save: Save, provider, pack) -> None:
    turn_no = save.state.turn_count
    cover_upto = turn_no - _RAW_KEEP
    prior = save.summary()
    prior_text = prior.summary_text if prior else None
    since = prior.covered_up_to_turn if prior else 0

    raw = [
        t
        for t in save.turns()
        if since < t.turn_no <= cover_upto and t.role in ("player", "gm")
    ]
    if not raw:
        return  # nothing new to fold in; the modulo already gates this

    print("\n[the world remembers…]", flush=True)
    try:
        new_text = memory_keeper_compress(provider, prior_text, raw, pack)
    except LLMError as exc:
        # Compression failure must NOT kill the turn — the player already
        # got their GM reply; the summary can be retried next tick.
        print(f"[memory keeper failed: {exc}]", file=sys.stderr)
        return
    save.set_summary(new_text, covered_up_to_turn=cover_upto)
    print()


# ── saves (top-level) ────────────────────────────────────────────────────


def _cmd_saves(args) -> int:
    saves = list_saves()
    if not saves:
        print("No saves yet. Run `tavern play <world-id>` to start one.")
        return 0
    _render_saves(saves, long=args.long)
    return 0


def _render_saves(saves, *, long: bool) -> None:
    name_w = max(len("NAME"), *(len(s.name) for s in saves))
    world_w = max(len("WORLD"), *(len(s.world_id) for s in saves))
    header = f"{'NAME':<{name_w}}  {'WORLD':<{world_w}}  TURNS  UPDATED"
    print(header)
    for s in saves:
        print(
            f"{s.name:<{name_w}}  {s.world_id:<{world_w}}  "
            f"{s.turn_count:>5}  {s.updated_at}"
        )
    if long:
        print()
        for s in saves:
            print(f"  {s.name} → {s.path}")


# ── export ───────────────────────────────────────────────────────────────


def _cmd_export(args) -> int:
    sub = args.export_command
    if sub == "novel":
        return _cmd_export_novel(args)
    print(
        "tavern export: expected one of {novel}",
        file=sys.stderr,
    )
    return 2


def _cmd_export_novel(args) -> int:
    save_name: str = args.save_name

    # Locate save.
    try:
        save = Save.open(save_name)
    except SaveError as exc:
        print(f"tavern export novel: {exc}", file=sys.stderr)
        return 1

    try:
        # Locate world (may be missing; export tolerates None pack).
        pack = _load_world_for_save(save.world_id)

        # Pick provider role.
        try:
            provider = _load_export_provider(args.provider)
        except LLMError as exc:
            print(f"tavern export novel: {exc}", file=sys.stderr)
            return 1

        try:
            result = export_novel(
                save,
                pack,
                provider,
                output=args.output,
                force=args.force,
            )
        except ExportError as exc:
            print(f"tavern export novel: {exc}", file=sys.stderr)
            return 1
        except LLMError as exc:
            print(f"tavern export novel: provider failed: {exc}", file=sys.stderr)
            return 1
    finally:
        save.close()

    print(
        f"Novel exported to {result.output_path} "
        f"({result.turn_count} turns, {result.chunk_count} chunk(s))"
    )
    return 0


def _load_export_provider(role_override: str | None):
    """Pick the provider role for export.

    Priority:
      1. `--provider` explicit override
      2. `[llm.export]` if configured
      3. `[llm.default]`
    """
    cfg = load_config()
    if role_override:
        return load_provider(role_override, cfg=cfg)
    if "export" in cfg.llm:
        return load_provider("export", cfg=cfg)
    return load_provider("default", cfg=cfg)


def _load_world_for_save(world_id: str) -> WorldPack | None:
    """Best-effort load of the world for a save. Returns None if unavailable."""
    for w in list_installed():
        if w.id == world_id:
            result = load_worldpack(w.path)
            return result.pack
    print(
        f"[warning] world '{world_id}' is not installed; "
        f"exporting without world metadata",
        file=sys.stderr,
    )
    return None


# ── entry ────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "install":
        return _cmd_install(args)
    if args.command == "list":
        return _cmd_list(args)
    if args.command == "uninstall":
        return _cmd_uninstall(args)
    if args.command == "config":
        return _cmd_config(args)
    if args.command == "play":
        return _cmd_play(args)
    if args.command == "saves":
        return _cmd_saves(args)
    if args.command == "export":
        return _cmd_export(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
