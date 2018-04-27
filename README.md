# WITYPI 

 __WI__ kipedia

 __T__ erminolog __Y__

 __PI__ cker

*****

![PyPI status](https://img.shields.io/badge/stage-alpha-green.svg)
![PyPI status](https://img.shields.io/badge/licence-CC-red.svg)
![PyPI status](https://img.shields.io/badge/version-1.0.0-blue.svg)

*****

## ABOUT WITYPI

WITYPI is a Python project aiming to automatically design a terminology by using the Wikipedia's DB (unsuppervised learning).

On Wiki, categories are linked together, and pages belong to these categories.

By creating a network graph between categories and applying TF-IDF on the vocabulary contained in all pages of every categories, we can extract important vocabulary for every class.

## INSTALLATION on UNIX systems

First, create a virtual environnement.

	virtualenv -p /usr/bin/env python3 WITYPI
	source /WITYPI/bin/activate

Then, by using pip3 after sourcing your virtualenv:

	pip3 install -r requierement.txt

## CONFIGURATION

LipSuM

## LAUNCH

Then, simply launch

	python3 __main__.py
