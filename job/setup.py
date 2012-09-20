from setuptools import setup, find_packages
import os

here = os.path.abspath(os.path.dirname(__file__))
try:
    README = open(os.path.join(here, 'README.rst')).read()
except IOError:
    README = ''

setup(
    name='Magma',
    version="1.1",
    license='commercial',
    author='Lars Ridder',
    author_email='lars.ridder@esciencecenter.nl>',
    url='http://www.esciencecenter.nl',
    description='Ms Annotation based on in silico Generated Metabolites',
    long_description=README,
    packages=find_packages(),
    install_requires=[ 'sqlalchemy', 'lxml'],
    dependency_links=[ 'http://www.rdkit.org' ],
    package_data={
        'magma': ['data/*.smirks', 'script/reactor'],
        },
    entry_points={
      'console_scripts': [
        'magma = magma.script:main',
      	'sygma = magma.script.sygma:main',
        'mscore_mzxml = magma.script.mscore_mzxml:main'
      ],
    }
)