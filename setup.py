from distutils.core import setup

setup(
	name="abaverify",
	version="0.1dev",
	packages=["abaverify",],
	install_requires=["jsonparser",],
	dependency_links=["ssh://fe.larc.nasa.gov/scr2/git/jsonparser.git/tarball/master#egg=jsonparser"]
)