from pathlib import Path
from datetime import datetime
import subprocess


v = datetime.now()
version = "\"{}.{}.{}.{}\"".format(v.year, v.month, v.day, v.hour * 3600 + v.minute*60 + v.second)

script = """# Maslite setup script created by package.py
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
""".format(version)

folder = Path(__file__).parent
file = "setup.py"
setup = folder / file

with open(setup, mode='w', encoding='utf-8') as f:
    f.write(script)

response = subprocess.Popen(["python", "setup.py", "sdist"], stdout=subprocess.PIPE)
response.wait()
return_code = response.returncode
if return_code != 0:
    print(response.stdout.read().decode())

