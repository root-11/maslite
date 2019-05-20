from pathlib import Path
from datetime import datetime
import subprocess
import hashlib


folder = Path(__file__).parent

# find the sha256 of the files used for this build.
maslite_packages = [folder / 'maslite' / "__init__.py",
                    folder / 'license.md',
                    folder / 'readme.md',
                    folder / 'requirements.txt'
                    ]

sha = hashlib.sha3_256()
for package_path in maslite_packages:
    with open(str(package_path), mode='rb') as fi:
        data = fi.read()
        sha.update(data)

current_build_tag = sha.hexdigest()

# get the sha256 of the existing build.
setup = folder / "setup.py"
with open(str(setup), encoding='utf-8') as f:
    lines = f.readlines()
    for row in lines:
        if "build_tag" in row:
            a = row.find('"')+1
            b = row.rfind('"')
            last_build_tag = row[a:b]
            break
    else:
        last_build_tag = 0

# compare
if current_build_tag == last_build_tag:
    print("build already in setup.py")

else:  # make a new setup.py.

    v = datetime.now()
    version = "\"{}.{}.{}.{}\"".format(v.year, v.month, v.day, v.hour * 3600 + v.minute*60 + v.second)

    script = """# Maslite setup script created by package.py
build_tag = \"{}\"
from pathlib import Path
from setuptools import setup


folder = Path(__file__).parent
filename = "readme.md"
readme = folder / filename
assert isinstance(readme, Path)
assert readme.exists(), readme
with open(str(readme), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name="MASlite",
    version={},
    url="https://github.com/root-11/maslite",
    license="MIT",
    author="Bjorn Madsen",
    author_email="bjorn.madsen@operationsresearchgroup.com",
    description="A lightweight multi-agent system",
    long_description=long_description,
    long_description_content_type='text/markdown',
    keywords="multi agent system MAS",
    packages=["maslite"],
    include_package_data=True,
    data_files=[(".", ["license.md", "readme.md"])],
    platforms="any",
    install_requires=[],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Natural Language :: English",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
    ],
)
""".format(current_build_tag, version)
    with open(str(setup), mode='w', encoding='utf-8') as f:
        f.write(script)

    response = subprocess.Popen(["python", "setup.py", "sdist"], stdout=subprocess.PIPE)
    response.wait()
    return_code = response.returncode
    if return_code != 0:
        print(response.stdout.read().decode())
    else:
        print("new setup.py created with build_tag {}".format(current_build_tag))