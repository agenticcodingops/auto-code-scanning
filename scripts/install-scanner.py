#!/usr/bin/env python3
"""Install only a named scanner binary after verifying the committed digest."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import stat
import sysconfig
import tarfile
import tempfile
import urllib.request
import zipfile
from safe_io import assert_safe_path

LOCK = Path(__file__).with_name('scanner-downloads.json')


def verified_binary(payload, expected, executable, zipped):
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError('Scanner archive checksum mismatch')
    if zipped:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            info = archive.getinfo(executable)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('Scanner archive member must be a regular file')
            return archive.read(info)
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
        member = archive.getmember(executable)
        if not member.isfile():
            raise ValueError('Scanner archive member must be a regular file')
        return archive.extractfile(member).read()


def install(tool, destination):
    system = platform.system().lower()
    architecture = platform.machine().lower()
    if not architecture and system == 'windows':
        architecture = sysconfig.get_platform().removeprefix('win-')
    machine = {'x86_64':'amd64','amd64':'amd64','aarch64':'arm64','arm64':'arm64'}.get(architecture)
    if machine is None:
        raise ValueError('Unsupported scanner platform architecture')
    settings = json.loads(LOCK.read_text())[tool]['platforms'][f'{system}-{machine}']
    name = tool + ('.exe' if system == 'windows' else '')
    destination = assert_safe_path(Path(destination) / name)
    payload = urllib.request.urlopen(settings['url'], timeout=120).read()
    binary = verified_binary(payload, settings['sha256'], name, settings['url'].endswith('.zip'))
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.scanner-', dir=destination.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(binary)
        os.chmod(temporary, 0o755)
        assert_safe_path(destination)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tool', choices=['trivy','tflint','gitleaks'])
    parser.add_argument('--destination', default=str(Path.home() / '.local-scanning-tools' / 'bin'))
    args = parser.parse_args()
    print(install(args.tool, args.destination))
