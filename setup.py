"""
Outscale
"""
from setuptools import setup
from outscale.__init__ import __version__

setup(
    name='Outscale',
    version=__version__,
    url='https://github.com/root-11/outscale',
    license='MIT',
    author='Bjorn Madsen',
    author_email='bjorn.madsen@operationsresearchgroup.com',
    description='A framework for fast multiprocessing multi-agent systems',
    packages=['outscale'],
    platforms='any',
    install_requires=[],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Science/Research',
        'Natural Language :: English',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
)