"""Build a Windows portable package and validate it before creating archives."""
from pathlib import Path
import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import zipfile
from comparador import __version__

ROOT = Path(__file__).resolve().parent
APP = "VideoDuplicateFinder"


def main():
    parser = argparse.ArgumentParser(description="Build Video Duplicate Finder for Windows x64")
    parser.add_argument("--ffmpeg-dir", type=Path, help="Directory containing ffmpeg.exe, ffprobe.exe and their DLLs")
    parser.add_argument("--package-only", action="store_true", help="Validate and package an existing build")
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("Build this executable on Windows x64.")
    ffmpeg = args.ffmpeg_dir or Path(shutil.which("ffmpeg") or "").parent
    if not all((ffmpeg/name).is_file() for name in ("ffmpeg.exe","ffprobe.exe")):
        raise SystemExit("Use --ffmpeg-dir to specify the FFmpeg bin directory.")
    release = ROOT / "dist" / ("v" + ".".join(__version__.split(".")[:2]))
    command = [sys.executable,"-m","PyInstaller","--noconfirm","--clean","--onedir","--windowed",
               "--name",APP,"--distpath",str(release),"--workpath",str(ROOT/"build"),"--specpath",str(ROOT/"build"),
               "--noupx","--exclude-module","tkinter","--exclude-module","PIL","--exclude-module","PySide6.QtQml","--exclude-module","PySide6.QtQuick",
               "--manifest",str(ROOT/"windows.manifest"),"--add-data",f"{ROOT/'assets'};assets",
               "--add-data",f"{ROOT/'comparador/locales'};comparador/locales"]
    qt = importlib.metadata.distribution("PySide6-Essentials")
    command += ["--add-data",f"{qt.locate_file('PySide6/translations/qtbase_es.qm')};translations"]
    for source in [ffmpeg/"ffmpeg.exe",ffmpeg/"ffprobe.exe",*ffmpeg.glob("*.dll")]:
        command += ["--add-data",f"{source};bin"]
    command.append(str(ROOT/"main.py"))
    env = os.environ.copy()
    windows = Path(env.get("WINDIR","C:/Windows"))
    env["PATH"] = os.pathsep.join(map(str,[Path(sys.executable).parent,Path(sys.base_prefix),ffmpeg.resolve(),windows/"System32",windows]))
    for name in ("PYTHONPATH","PYTHONHOME","QT_PLUGIN_PATH","QT_QPA_PLATFORM_PLUGIN_PATH"):
        env.pop(name,None)
    if not args.package_only:
        subprocess.run(command,cwd=ROOT,env=env,check=True)
    output = release / APP
    if not (output/(APP+".exe")).is_file():
        raise SystemExit("Build the executable before using --package-only.")
    for name in ("README.md","THIRD_PARTY.md","TESTING.md","PRIVACY.md","CHANGELOG.md"):
        shutil.copy2(ROOT/name,output/name)
    licenses = output/"licenses"
    licenses.mkdir(exist_ok=True)
    for source, target in [(Path(sys.base_prefix)/"LICENSE.txt","Python-LICENSE.txt"),(ffmpeg.parent/"LICENSE.txt","FFmpeg-LICENSE.txt")]:
        if source.is_file():
            shutil.copy2(source,licenses/target)
    packages=("PySide6-Essentials","shiboken6","numpy","Send2Trash","PyInstaller","av")
    for package in packages:
        distribution=importlib.metadata.distribution(package)
        for file in distribution.files or []:
            if any(word in str(file).lower() for word in ("license","copying")):
                source=Path(distribution.locate_file(file))
                if source.is_file():
                    target=licenses/package/str(file)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(source,target)
    version=subprocess.run([str(ffmpeg/"ffmpeg.exe"),"-version"],capture_output=True,text=True,check=True).stdout
    (licenses/"FFmpeg-build.txt").write_text(version,encoding="utf-8")
    (output/"versions.json").write_text(json.dumps({p:importlib.metadata.version(p) for p in packages},indent=2),encoding="utf-8")
    artifacts=ROOT/"artifacts"
    artifacts.mkdir(exist_ok=True)
    report=artifacts/"build-selftest.json"
    report.unlink(missing_ok=True)
    env["PATH"]=str(windows/"System32")
    result=subprocess.run([str(output/(APP+".exe")),"--self-test",str(report)],env=env,cwd=artifacts,timeout=180)
    if result.returncode or not report.exists() or not json.loads(report.read_text(encoding="utf-8")).get("ok"):
        raise SystemExit(f"Portable verification failed. Inspect {report}")
    archive=shutil.make_archive(str(release/f"{APP}-{__version__}-Windows-x64"),"zip",release,APP)
    source_archive=release/f"{APP}-{__version__}-source.zip"
    from tools.audit_public import public_files, audit
    files=public_files(ROOT)
    findings=audit(files,ROOT)
    if findings:
        raise SystemExit("Source privacy audit failed: "+str(findings))
    with zipfile.ZipFile(source_archive,"w",zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            bundle.write(path,"video-duplicate-finder/"+path.relative_to(ROOT).as_posix())
    print(f"Executable: {output/(APP+'.exe')}")
    print(f"Portable archive: {archive}")
    print(f"Source archive: {source_archive}")


if __name__=="__main__":
    main()
