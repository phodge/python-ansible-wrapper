# type: ignore
from setuptools import setup


setup(
    name='python-ansible-wrapper',
    version='0.0.0',
    description='',
    packages=['python_ansible_wrapper'],
    package_data={'python_ansible_wrapper': ['py.typed', '**/py.typed']},
    install_requires=[
        'pyyaml',
        'chromalog',
    ],
)
