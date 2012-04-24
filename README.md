# Ludum Dare 23

This game is DONE.

## How to get py2app to work 

It's really hard.

First, run `mac_setup`.

Then, go into the generated app, find `__boot__.py` and insert the following line into the `_run` method.

    sys.path.insert(0, os.path.join(base, 'lib', 'python2.5', 'lib-dynload'))

## Compiling from source on OSX:

     port install py-game

     python main.py

## Compiling from source on Ubuntu:

		sudo apt-get install python-pygame

		python main.py
