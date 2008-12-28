from ez_setup import use_setuptools
use_setuptools()
from setuptools import setup, find_packages

setup(
    name='twactor',
    version='0.1alpha',
    description="Zack's Python twitter client.",
    author='Zachary Voase',
    author_email='zack@biga.mp',
    url='http://github.com/zvoase/twactor/tree/master',
    packages=find_packages(exclude='tests'),
    package_data={'', '*.conf'},
    install_requires=['simplejson==2.0.6', 'pytz==2008i'],
    )