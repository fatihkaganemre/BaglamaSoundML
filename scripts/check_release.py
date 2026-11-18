#!/usr/bin/env python3
"""Validate stable SPM release tags. CLI uses Python 3.11+ (tomllib)."""
from __future__ import annotations
import argparse
from pathlib import Path
import re


def validate_release(tag: str, project_version: str) -> str:
    if not re.fullmatch(r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)',tag):
        raise ValueError('Use a stable semantic-version tag such as v0.1.0. Prerelease/build suffixes are not configured yet.')
    version=tag[1:]
    if version!=project_version:
        raise ValueError(f'Tag {tag} does not match pyproject.toml version {project_version}. Update the version on main before tagging.')
    return version


def main():
    import tomllib
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',required=True)
    parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]/'pyproject.toml')
    args=parser.parse_args()
    with args.project.open('rb') as source:version=tomllib.load(source)['project']['version']
    try:print(validate_release(args.tag,version))
    except ValueError as error:parser.error(str(error))


if __name__=='__main__':main()
