"""
Outscale
"""
from datetime import datetime
from setuptools import setup

v = datetime.now()
__version__ = "{}.{}.{}.{}".format(v.year, v.month, v.day, v.hour * 3600 + v.minute*60 + v.second)

setup(
    name="MASlite",
    version=__version__,
    url="https://github.com/root-11/outscale",
    license="MIT",
    author="Bjorn Madsen",
    author_email="bjorn.madsen@operationsresearchgroup.com",
    description="A framework for fast multiprocessing multi-agent systems",
    packages=["maslite"],
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
