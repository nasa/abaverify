from setuptools import setup, find_packages

setup(
	name="abaverify",
	version="0.1dev",
	packages=[
		"abaverify",
	],
	install_requires=[
		"jsonparser==0.1",
	],
	dependency_links=[
		"ssh://fe.larc.nasa.gov/scr2/git/jsonparser.git@master#egg=jsonparser-0.1"
	]
)