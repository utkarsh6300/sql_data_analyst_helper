"""Individual compiler passes.

Each pass has one responsibility and reports failures as
:class:`~sql_compiler.errors.Violation` objects rather than raising, so the
compiler can decide whether a failure is fatal or collectible.
"""
