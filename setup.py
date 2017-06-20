from setuptools import setup, find_packages
import re

def get_version(path):
    version_file_as_str = open(path, "rt").read()
    version_re = r"^__version__ = ['\"]([^'\"]*)['\"]"
    match = re.search(version_re, version_file_as_str, re.M)
    if match:
        return match.group(1)
    else:
        raise RuntimeError("Unable to find version string.")


setup(
    name="abaverify",
    version=get_version("abaverify/_version.py"),
    url="https://github.com/nasa/abaverify",
    license="NASA Open Source Agreement Version 1.3",
    author="Andrew Bergan",
    author_email="andrew.c.bergan@nasa.gov",
    install_requires=["paramiko", "plotly"],
    packages=["abaverify",],
)