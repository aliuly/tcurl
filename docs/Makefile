# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= $(shell type sphinx-build 1>&2 && echo sphinx-build || echo $$(pwd)/pys sphinx-build)

SOURCEDIR     = .
BUILDDIR      = _build
PYS			  = ./pys

# Put it first so that "make" without argument is like "make help".
help:
	type sphinx-build || $(PYS) type sphinx-build || $(PYS) pip install --requirement requirements.txt
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	type sphinx-build || $(PYS) type sphinx-build || $(PYS) pip install --requirement requirements.txt
	echo $(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
	$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
