#!/usr/bin/env python3
"""
PDF to Markdown Converter Command Line Tool

This is a simple wrapper script that imports and runs the main function from
the pdf2markdown4llm.cli module. This allows the tool to be run directly
without installing the package.
"""

from pdf2markdown4llm.cli import main

if __name__ == "__main__":
    main()
