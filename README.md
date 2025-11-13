# Live Monitoring Software

This is a live monitoring software for use in my experment. It is written in Python and uses PySide6 UI.

# Requirements

This software requires a GenTL producer to connect to a camera.
This can be found on the website of the imaging source.
https://www.theimagingsource.com/en-us/support/download/

It also requires a micromanager setup. This can be downloaded at:
https://micro-manager.org/Micro-Manager_Nightly_Builds

The dependent python modules are found in the requirements text file.

The imagingcontrol4 modules are only found on the PyPI repository (not conda or eg. apt), so using pip (and a venv) is recommended.

pip install -r ./requirements.txt
