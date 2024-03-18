# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys

sys.path.insert(0, os.path.abspath("../"))


# -- Project information -----------------------------------------------------

project = "contextvars-registry"
copyright = "2021, Dmitry Vasilyanov"  # pylint: disable=redefined-builtin
author = "Dmitry Vasilyanov"


# -- General configuration ---------------------------------------------------

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Don't add module names to functions/classes.
#
# That allows to simplify this:
#
#    class contextvars_registry.context_var_ext.ContextVarExt
#
# to just this:
#
#    class ContextVarExt
#
# which is much more readable.
add_module_names = False
python_use_unqualified_type_names = True

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx_copybutton",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__call__,__init__",
}

# Remove type hints from function signatures (and instead put them to function description).
#
# This is done because this whole project is about Generic containers (ContextVarExt,
# ContextVarDescriptor, etc), so that means there is a lot of TypeVar and Union in the code,
# which makes function signatures ugly.
#
# So, to make signatures look nice in the docs, I'm removing type hints from them
# (type hints are still there, but they're placed inside the function description).
autodoc_typehints = "description"

# Don't evaluate default values for function parameters.
#
# Because I have a lot of special singletons on the project,
# and they look ugly in function signatures, e.g.:
#
#   def get(default=contextvars_registry.context_var_ext.NO_DEFAULT)
#
# And with this option enabled, they look nice and pretty:
#
#   def get(default=NO_DEFAULT)
#
# Of course, it may hurt defaults in other cases, but I have a lot
# of such special singletons on the project, so the net result is good.
autodoc_preserve_defaults = True

# Don't generate files when using sphinx.ext.autosummary
# I just don't use this feature (that enabled by default).
autosummary_generate = False


# Configure sphinx_copybutton extensions to work with Python doctest code snippets
copybutton_prompt_text = r">>> |\.\.\. | $"
copybutton_prompt_is_regexp = True
copybutton_remove_prompts = True
copybutton_only_copy_prompt_lines = False

# Allow links to standard Python docs and other documentation sites.
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "greenlet": ("https://www.gevent.org/", None),
}


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "sphinx_rtd_theme"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]
