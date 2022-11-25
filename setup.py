# Maslite setup script created by package.py
build_tag = "f10f2e5a4fe11f1ca964881eedb1509ac851d07abb2ab48f7e2dbedee304af6a"
from pathlib import Path
from setuptools import setup

__version__ = None
version_file = Path(__file__).parent / "maslite" / "version.py"
exec(version_file.read_text())

folder = Path(__file__).parent
filename = "readme.md"
readme = folder / filename
assert isinstance(readme, Path)
assert readme.exists(), readme
with open(str(readme), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name="MASlite",
    version=__version__,  
    url="https://github.com/root-11/maslite",
    license="MIT",
    author="root-11",
    description="A fast & lightweight multi-agent system kernel",
    long_description=long_description,
    long_description_content_type='text/markdown',
    keywords=["multi agent system", "MAS", "maslite"],
    packages=["maslite"],
    include_package_data=True,
    data_files=[(".", ["license.md", "readme.md"])],
    platforms="any",
    install_requires=[],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Science/Research",
        "Natural Language :: English",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
