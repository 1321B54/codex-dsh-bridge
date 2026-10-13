"""Behavioral checks for the user-level skill entrypoint; never paid model runs."""
import os
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import bridge

SKILL = bridge.BASE / "skills" / "dsh-collaboration"


class SkillEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        launch = json.loads((bridge.STATE / "runtime-launch.json").read_text(encoding="utf-8-sig"))
        cls.pwsh = launch.get("pwsh_path")

    def invoke(self, script, cwd, *arguments):
        if os.name != "nt":
            script = script.with_suffix(".sh") if script.name == "invoke-dsh.ps1" else bridge.BASE / "install-skill.sh"
            converted = []
            flags = {"-Workspace": "--workspace", "-TaskFile": "--task-file",
                     "-ContinueFrom": "--continue-from", "-SkillRoot": "--skill-root"}
            for arg in arguments:
                if arg != "-Command":
                    converted.append(flags.get(arg, arg))
            return subprocess.run([str(script), *converted], cwd=cwd, capture_output=True,
                                  text=True, encoding="utf-8", timeout=60)
        return subprocess.run([self.pwsh, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                               "-File", str(script), *arguments], cwd=cwd, capture_output=True,
                              text=True, encoding="utf-8", timeout=60)

    def test_doctor_works_from_unrelated_project_without_editing_it(self):
        with tempfile.TemporaryDirectory(dir=bridge.STATE, prefix="skill-project-") as temp:
            project = Path(temp).resolve()
            self.assertTrue(project.is_relative_to(bridge.STATE.resolve()))
            marker = project / "existing-user-file.txt"
            marker.write_text("preserve me", encoding="utf-8")
            result = self.invoke(SKILL / "scripts" / "invoke-dsh.ps1", project, "-Command", "doctor")
            self.assertEqual(result.returncode, 0, result.stderr)
            status = json.loads(result.stdout)
            self.assertEqual(status["sdk_initialization"], "passed")
            self.assertEqual(status["paid_model_tasks"], 0)
            self.assertEqual(status["model"], "deepseek-flash")
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve me")
            self.assertEqual({p.name for p in project.iterdir()}, {marker.name})

    def test_run_requires_explicit_task_and_never_defaults_to_a_project(self):
        (bridge.STATE / "runs").mkdir(exist_ok=True)
        before = {p.name for p in (bridge.STATE / "runs").iterdir()}
        result = self.invoke(SKILL / "scripts" / "invoke-dsh.ps1", bridge.BASE.parent,
                             "-Command", "run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("explicit workspace and task contract", result.stderr)
        self.assertEqual(before, {p.name for p in (bridge.STATE / "runs").iterdir()})

    def test_missing_installation_fails_without_reinstallation(self):
        with tempfile.TemporaryDirectory(dir=bridge.STATE, prefix="skill-missing-") as temp:
            root = Path(temp).resolve()
            self.assertTrue(root.is_relative_to(bridge.STATE.resolve()))
            scripts = root / "scripts"
            scripts.mkdir()
            script = scripts / "invoke-dsh.ps1"
            for name in ("invoke-dsh.ps1", "invoke-dsh.sh", "invoke-dsh.py"):
                shutil.copy2(SKILL / "scripts" / name, scripts / name)
            missing = root / "missing-bridge"
            (root / "bridge-location.json").write_text(json.dumps({"bridge_root": str(missing)}), encoding="utf-8")
            result = self.invoke(script, root, "-Command", "doctor")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No automatic reinstall or permission fallback", result.stderr)
            self.assertFalse(missing.exists())

    def test_source_skill_resolves_portable_bridge_without_private_mapping(self):
        self.assertFalse((SKILL / "bridge-location.json").exists())
        result = self.invoke(SKILL / "scripts" / "invoke-dsh.ps1", bridge.BASE.parent, "-Command", "doctor")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["paid_model_tasks"], 0)

    def test_installer_creates_portable_local_mapping_and_entry(self):
        with tempfile.TemporaryDirectory(dir=bridge.STATE, prefix="skill-install-") as folder:
            root = Path(folder).resolve()
            result = self.invoke(bridge.BASE / "Install-Skill.ps1", root, "-SkillRoot", str(root))
            self.assertEqual(result.returncode, 0, result.stderr)
            installed = root / "dsh-collaboration"
            mapping = json.loads((installed / "bridge-location.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(Path(mapping["bridge_root"]), bridge.BASE)
            result = self.invoke(installed / "scripts" / "invoke-dsh.ps1", root, "-Command", "doctor")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["paid_model_tasks"], 0)
            self.assertEqual({p.name for p in root.iterdir()}, {"dsh-collaboration"})

    def test_installer_never_overwrites_an_existing_skill(self):
        with tempfile.TemporaryDirectory(dir=bridge.STATE, prefix="skill-preserve-") as folder:
            root = Path(folder).resolve()
            installed = root / "dsh-collaboration"
            installed.mkdir()
            marker = installed / "user-content.txt"
            marker.write_text("preserve existing skill", encoding="utf-8")
            result = self.invoke(bridge.BASE / "Install-Skill.ps1", root, "-SkillRoot", str(root))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve existing skill")
            self.assertEqual({p.name for p in installed.iterdir()}, {marker.name})


if __name__ == "__main__":
    unittest.main()
