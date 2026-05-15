#!/usr/bin/env python3
"""Setup script for tcurl."""

from setuptools import setup

# Read the version from tcurl.py without importing it
VERSION = None
with open('tcurl.py', encoding='utf-8') as f:
    for line in f:
        if line.startswith('VERSION'):
            VERSION = line.split("'")[1] if "'" in line else line.split('"')[1]
            break

if VERSION is None:
    raise RuntimeError('Unable to find version string in tcurl.py')

# Long description from README.md
with open('README.md', encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='tcurl',
    version=VERSION,
    description='CLI tool and Python module for T Cloud Public REST API calls',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Alejandro Liu',
    author_email='alejandrol@t-systems.com',
    url='https://github.com/aliuly/tcurl',
    license='MIT',
    license_files=['LICENSE'],
    py_modules=['tcurl', 'tcurl_login'],
    python_requires='>=3.10',
    install_requires=[
        'requests',
        'pyyaml',
        'urwid',
    ],
    extras_require={
        'debug': ['icecream'],
        'all': ['icecream'],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Utilities',
    ],
    entry_points={
        'console_scripts': [
            'tcurl = tcurl:main',
            'tcurl-login = tcurl_login:main',
        ],
    },
    project_urls={
        'Source': 'https://github.com/aliuly/tcurl',
        'Bug Reports': 'https://github.com/aliuly/tcurl/issues',
    },
)
