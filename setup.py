from setuptools import find_packages
from setuptools import setup


def contents(filename):
    from os.path import abspath, dirname, join
    with open(join(abspath(dirname(__file__)), filename)) as fh:
        return fh.read()


setup(
    name='gmail-yaml-filters',
    author='Alex Levy',
    author_email='mesozoic@users.noreply.github.com',
    description='A quick tool for generating Gmail filters from YAML rules.',
    long_description=contents('README.md'),
    long_description_content_type='text/markdown',
    url='https://github.com/mesozoic/gmail-yaml-filters',
    version='0.9.2',
    classifiers=[
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    packages=find_packages('.'),
    entry_points={
        'console_scripts': [
            'gmail-yaml-filters = gmail_yaml_filters.main:main',
        ],
    },
    install_requires=[
        'google-api-python-client',
        'lxml',
        'oauth2client',
        'pyyaml',
        'six',
    ],
)
