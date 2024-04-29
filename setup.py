from os import path
from setuptools import setup, find_packages
import sys
import subprocess

here = path.abspath(path.dirname(__file__))

with open(path.join(here, "README.md"), encoding="utf-8") as readme_file:
    readme = readme_file.read()

with open(path.join(here, "requirements.txt")) as requirements_file:
    # Parse requirements.txt, ignoring any commented-out lines.
    requirements = [
        line
        for line in requirements_file.read().splitlines()
        if not line.startswith("#")
    ]

try:
    from semantic_release import setup_hook
    setup_hook(sys.argv)
except ImportError:
    pass

__version__='0.0.1'
setup(
    name="PerformanceTestRunner",
    version= __version__,
    description="Python package for performance load testing",
    long_description_content_type="text/markdown",
    long_description=readme,
    author="Shervin Abdollahi, Mark Williams",
    author_email="shervin.abdollahi@Nih.gov, mark.williams5@nih.gov",
    url="https://github.com/TranslatorSRI/PerformanceTestRunner",
    packages=find_packages(),
    include_package_data=True,
    install_requires=requirements,
    license="Public Domain",
    package_data={
        'ARS_Test_Runner': ['templates/treats.json', 'templates/treats_creative.json','templates/affects_creative.json']
    },
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
    ],
    entry_points={
        "console_scripts": [
            "PerformanceTestRunner=PerformanceTestRunner.cli:main"
        ]
    },

)

