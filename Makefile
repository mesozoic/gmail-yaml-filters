test:
	tox

clean:
	rm -rf dist/

upload: venv_build clean
	venv_build/bin/python setup.py sdist || exit
	venv_build/bin/twine upload --repository-url https://test.pypi.org/legacy/ dist/* || exit
	venv_build/bin/twine upload --repository-url https://upload.pypi.org/legacy/ dist/*

venv_%:
	virtualenv -p python3 $@
	$@/bin/pip install --upgrade pip
	$@/bin/pip install setuptools twine wheel
