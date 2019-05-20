# Maslite setup script created by package.py
build_tag = "24e8f359f8677ac64aab1f373ccc49015f842ff5b51dc88005e4642e4dcfe2b5"
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
    version="2019.5.20.52173",
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
