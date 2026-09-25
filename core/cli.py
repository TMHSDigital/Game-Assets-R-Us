# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line entry point, run inside Blender:

    blender --background --factory-startup --python core/cli.py -- run \
        --kit stone-dungeon-wall-sampler --profile unity --seed 1337 \
        [--stages generate,validate,export,render,package] [--fix] \
        [--generator-path DIR ...] [--build-dir build] [--dist-dir dist]

    blender --background --factory-startup --python core/cli.py -- brandscan PATH [PATH ...]

--stages adds missing prerequisites: generate always runs, export implies
validate, package implies validate and export.

Exit codes: 0 ok, 1 validation or brand failure, 2 usage or contract error,
3 profile is a stub (nothing exported).
"""

import argparse
import os
import shutil
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

STAGES = ["generate", "validate", "export", "render", "package"]
# Stages a stage cannot run without. generate always runs (every other stage
# works on the generated scene); nothing is exported or packaged unvalidated.
PREREQUISITES = {"export": ["validate"], "package": ["validate", "export"]}


def plan_stages(requested):
    """Return (stages in pipeline order, prerequisites that were added)."""
    wanted = set(requested) | {"generate"}
    for stage in requested:
        wanted.update(PREREQUISITES.get(stage, []))
    added = [s for s in STAGES if s in wanted and s not in requested and s != "generate"]
    return [s for s in STAGES if s in wanted], added


def _args(argv):
    parser = argparse.ArgumentParser(prog="core/cli.py")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="generate, validate, export, render and package one profile")
    run.add_argument("--kit", required=True)
    run.add_argument("--profile", required=True)
    run.add_argument("--seed", type=int)
    run.add_argument("--stages", default=",".join(STAGES))
    run.add_argument("--fix", action="store_true", help="apply deterministic fixes (logged in reports)")
    run.add_argument("--generator-path", action="append", default=[])
    run.add_argument("--build-dir", default=os.path.join(ROOT, "build"))
    run.add_argument("--dist-dir", default=os.path.join(ROOT, "dist"))
    run.add_argument("--save-blend", action="store_true", help="also save the generated scene as .blend")
    scan = sub.add_parser("brandscan", help="scan file names and text files for blocklisted marks")
    scan.add_argument("paths", nargs="+")
    return parser.parse_args(argv)


def _fresh_dir(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path)


def cmd_run(args):
    from core.contract import ContractError, load_contract, resolve
    from core.generators import RegistryError, get, load_module

    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    unknown = [s for s in stages if s not in STAGES]
    if unknown:
        print(f"ERROR unknown stages {unknown}; valid: {STAGES}")
        return 2
    stages, added = plan_stages(stages)
    if added:
        print(f"STAGES added prerequisites: {','.join(added)}")
    try:
        info = get(args.kit, args.generator_path)
        contract = load_contract(info.contract_path)
        if contract["kit"]["generator"] != info.id:
            raise ContractError(info.contract_path, [("/kit/generator", f"names '{contract['kit']['generator']}', "
                                                      f"but the manifest id is '{info.id}'")])
        resolved = resolve(contract, args.profile)
    except (ContractError, RegistryError) as exc:
        print(f"ERROR {exc}")
        return 2

    profile = resolved["profile"]
    if profile["kind"] == "stub":
        from core.exporters import stubs
        return stubs.run(resolved)

    if profile.get("exporter") == "sollumz":
        from core import fivem
        try:
            fivem.ensure_sollumz(profile)
        except fivem.SollumzUnavailable as exc:
            print(f"UNAVAILABLE profile '{profile['name']}' ({profile['status']}): {exc}")
            return 3

    seed = args.seed if args.seed is not None else contract["kit"]["default_seed"]
    out_dir = os.path.join(args.build_dir, contract["kit"]["id"], args.profile)
    _fresh_dir(out_dir)
    print(f"RUN kit={info.id} ({info.source}) profile={args.profile} seed={seed} stages={','.join(stages)}")

    from core import pipeline
    module = load_module(info)
    scene = pipeline.generate(resolved, module, seed)
    print(f"GENERATED {len(scene.sets)} piece variants")
    if args.save_blend:
        import bpy
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "scene.blend"))

    if "validate" in stages:
        from core.validators import runner
        summary = runner.validate(scene, out_dir, fix=args.fix)
        if not summary["passed"]:
            print(f"VALIDATION FAILED: {len(summary['failed_pieces'])} failing reports in {out_dir}/reports")
            return 1
        print("VALIDATION PASSED")

    wants_output = any(s in stages for s in ("export", "render", "package"))
    textures = resolved.get("textures")
    if wants_output and profile["kind"] == "mesh" and textures and textures["bake"]:
        from core import bake
        texdir = os.path.join(out_dir, "exports", "textures")
        if profile.get("material_mode") == "single_baked":
            # Tiling textures are baked in memory only, then each piece is
            # baked from them into its own single-material texture set.
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                bake.bake_and_apply(resolved, tmp)
                from core import roblox
                try:
                    baked = roblox.prepare(scene, texdir)
                except roblox.RobloxLimitError as exc:
                    print(f"ERROR {exc}")
                    return 1
        else:
            baked = bake.bake_and_apply(resolved, texdir)
        scene.textures = baked
        print(f"BAKED {len(baked)} textures")

    if "export" in stages:
        from core.exporters import export_scene
        manifest = export_scene(scene, out_dir)
        if not manifest["roundtrip_passed"]:
            print("EXPORT ROUNDTRIP FAILED")
            return 1
        print(f"EXPORTED {len(manifest['files'])} files")

    if "render" in stages:
        from core.render import render_previews
        render_previews(scene, out_dir)

    if "package" in stages:
        from core.packagers import PackagingError, package
        try:
            zip_path = package(resolved, info, out_dir, args.dist_dir)
        except PackagingError as exc:
            print(f"PACKAGING FAILED: {exc}")
            return 1
        print(f"PACKAGED {zip_path}")
    return 0


def cmd_brandscan(args):
    from core.validators.legal_checks import BrandScanner
    scanner = BrandScanner()
    surfaces = []
    text_ext = {".toml", ".md", ".txt", ".json", ".py", ".ps1", ".yml", ".gltf"}
    skip_files = {os.path.normcase(os.path.abspath(p)) for p in
                  (os.path.join(ROOT, "data", "brand_blocklist.txt"), os.path.join(ROOT, "data", "brand_allowlist.txt"))}

    def walk(root_path):
        if os.path.isfile(root_path):
            yield root_path
            return
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = sorted(d for d in dirnames if d not in {".git", "__pycache__"})
            for name in sorted(filenames):
                yield os.path.join(dirpath, name)

    for root_path in args.paths:
        if not os.path.exists(root_path):
            print(f"BRANDSCAN missing path {root_path}")
            return 2
        for path in walk(root_path):
            if os.path.normcase(os.path.abspath(path)) in skip_files:
                continue
            name = os.path.basename(path)
            surfaces.append((f"file:{path}", name))
            if os.path.splitext(name)[1].lower() in text_ext:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    for lineno, line in enumerate(fh, 1):
                        surfaces.append((f"{path}:{lineno}", line))
    hits = scanner.scan(surfaces)
    for hit in hits:
        print(f"BRAND HIT {hit['mark']!r} at {hit['where']}")
    print(f"BRANDSCAN scanned={len(surfaces)} hits={len(hits)}")
    return 1 if hits else 0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = _args(argv)
    try:
        code = cmd_run(args) if args.command == "run" else cmd_brandscan(args)
    except Exception:
        traceback.print_exc()
        code = 2
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
