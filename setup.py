from setuptools import setup


setup(
    name='gmail-yaml-filters',
    entry_points={
        'console_scripts': [
            'gmail-yaml-filters = gmail_yaml_filters.main:main',
        ],
    },
)
