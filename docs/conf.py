# Configuration file for the Sphinx documentation builder.
#
# see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import datetime
import os
import sys
from inspect import getsourcefile
import subprocess

DOCS_DIR = os.path.dirname(os.path.abspath(getsourcefile(lambda: 0)))
REPO_DIR = os.path.dirname(DOCS_DIR)
sys.path.insert(0, REPO_DIR)
# ~ sys.path.insert(1,os.path.join(REPO_DIR,'scullery'))

# -- versioning -----------------------------------------------------
try:
  rc = subprocess.run(
      [ 'git','describe','--always' ],
      capture_output = True,
      text = True,
      check = True
    )
  VERSION = rc.stdout.strip()
except Exception as e:
  sys.stderr.write(f'Error {e}')
  VERSION = 'Development'

# -- Project information -----------------------------------------------------

project = 'tcurl'
author = 'A Liu Ly'
copyright = "{}, {}".format(datetime.datetime.now().year, author)
# The full version, including alpha/beta/rc tags
release = VERSION
# The short X.Y version
version = ".".join(VERSION.split(".")[0]) if '.' in VERSION else VERSION

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
               'sphinxarg.ext',   # argparse https://sphinx-argparse.readthedocs.io/en/stable/index.html
               'myst_parser',     # Markdown support
               'autodoc2',        # Automatic doc generation
              ]
myst_enable_extensions = [
  'tasklist',
  'fieldlist',
]
autodoc2_render_plugin = 'myst'
# Point to the python source to document.  Can be either a directory
# or a py file.  It *NEEDS* to be a relative path.
autodoc2_packages = [ os.path.join('..','tcurl.py') ]


# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store', '.venv']


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'alabaster'

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Set up intersphinx maps
intersphinx_mapping = {'numpy': ('https://numpy.org/doc/stable', None)}
