from pathlib import Path
from datetime import datetime
import subprocess
import hashlib


folder = Path(__file__).parent

# find the sha256 of the files used for this build.
packages = [
    folder / 'maslite' / "__init__.py",
    folder / 'license.md',
    folder / 'readme.md',
]

sha = hashlib.sha3_256()
for package_path in packages:
    with open(str(package_path), mode='rb') as fi:
        data = fi.read()
        sha.update(data)

current_build_tag = sha.hexdigest()

# get the sha256 of the existing build.
setup = folder / "setup.py"
build_tag_idx, version_idx = None, None
with open(str(setup), encoding='utf-8') as f:
    lines = f.readlines()
    for idx, row in enumerate(lines):
        if "build_tag" in row:
            if build_tag_idx is None:
                build_tag_idx = idx
            a = row.find('"') + 1
            b = row.rfind('"')
            last_build_tag = row[a:b]
        if "version=" in row and version_idx is None:
            version_idx = idx

if build_tag_idx is None:
    build_tag_idx = 0
if version_idx is None:
    raise ValueError("version not declared in setup.py")

# compare
if current_build_tag == last_build_tag:
    print("build already in setup.py")

else:  # make a new setup.py.
    v = datetime.now()
    version = "\"{}.{}.{}.{}\"".format(v.year, v.month, v.day, v.hour * 3600 + v.minute * 60 + v.second)

    # update the setup.py file.
    with open(str(setup), encoding='utf-8') as fi:
        old_setup = fi.readlines()
        old_setup[build_tag_idx] = "build_tag = \"{}\"\n".format(current_build_tag)
        old_setup[version_idx] = "    version={},\n".format(version)

    script = "".join(old_setup)
    with open(str(setup), mode='w', encoding='utf-8') as f:
        f.write(script)

    response = subprocess.Popen(["python", "setup.py", "sdist"], stdout=subprocess.PIPE)
    response.wait()
    return_code = response.returncode
    if return_code != 0:
        print(response.stdout.read().decode())
    else:
        print("new setup.py created with build_tag {}".format(current_build_tag))
        print(">>> next: run: twine upload dist\\MASlite-<THE SPECIFIC PACKAGE>")