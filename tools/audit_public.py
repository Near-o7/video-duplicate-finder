"""Audit an explicit source allowlist before its first public commit."""
from pathlib import Path
import argparse
import json
import re
import subprocess

DIRECTORIES=("comparador","assets","tests","tools",".github")
ROOT_FILES=(".gitignore",".gitattributes","README.md","THIRD_PARTY.md","TESTING.md","PRIVACY.md","CHANGELOG.md",
            "main.py","build.py","requirements.txt","requirements-dev.txt","windows.manifest")
EXTENSIONS={".py",".json",".svg",".md",".txt",".yml",".yaml",".manifest"}


def public_files(root):
    files=[root/name for name in ROOT_FILES if (root/name).is_file()]
    patterns=("comparador/*.py","comparador/locales/es.json","assets/*.svg","tests/*.py","tools/*.py",".github/workflows/*.yml")
    for pattern in patterns:
        files.extend(p for p in root.glob(pattern) if p.is_file())
    return sorted(set(files))


def audit(files,root,private_terms=(),snapshots=None):
    patterns=[r"(?i)[a-z]:[\\/]users[\\/][^\s\"'<>]+",r"/home/[a-zA-Z0-9_.-]+/",r"/Users/[a-zA-Z0-9_.-]+/",
              r"gh[pousr]_[a-zA-Z0-9]{25,}",r"github_pat_[a-zA-Z0-9_]{30,}",r"sk-[a-zA-Z0-9]{25,}"]
    findings=[]
    for path in files:
        relative=path.relative_to(root).as_posix()
        if path not in public_files(root):
            findings.append({"path":relative,"reason":"outside source allowlist"})
            continue
        text=snapshots[relative] if snapshots is not None else path.read_text(encoding="utf-8")
        if any(re.search(pattern,text) for pattern in patterns):
            findings.append({"path":relative,"reason":"absolute home path or token pattern"})
        if any(term.casefold() in text.casefold() for term in private_terms if term):
            findings.append({"path":relative,"reason":"private term"})
    return findings


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--staged",action="store_true")
    parser.add_argument("--private-term",action="append",default=[])
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    files=public_files(root)
    snapshots=None
    if args.staged:
        names=subprocess.run(["git","diff","--cached","--name-only","--diff-filter=ACMRT","-z"],cwd=root,check=True,capture_output=True).stdout.decode().split("\0")
        files=[root/name for name in names if name]
        snapshots={name:subprocess.run(["git","show",":"+name],cwd=root,check=True,capture_output=True).stdout.decode("utf-8") for name in names if name}
    findings=audit(files,root,args.private_term,snapshots)
    print(json.dumps({"files_checked":len(files),"findings":findings},indent=2))
    if findings:
        raise SystemExit(1)


if __name__=="__main__":
    main()
