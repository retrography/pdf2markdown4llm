# PDF2Markdown4LLM

PDF2Markdown4LLM is a Python library that converts PDF documents to Markdown format, specifically optimized for Large Language Models (LLMs). It intelligently preserves document structure, identifies headers based on font sizes, and handles tables while maintaining the original document flow.

## Features

- Intelligent header detection based on font size analysis
- Table extraction and conversion to Markdown format
- Maintains document structure and flow
- Handles nested content and complex layouts
- Font size classification for consistent header levels
- Clean table formatting with proper alignment
- Optional header removal functionality
- Robust error handling and validation

## Installation

```bash
pip install pdf2markdown4llm
```

## Dependencies

- pdfplumber
- dataclasses (Python 3.7+)
- typing
- collections
- re

## Usage

Basic usage example:

```python
from pdf2markdown4llm import PDF2Markdown4LLM

def progress_callback(progress): 
    """Callback function to handle progress"""
    print(f"Phase: {progress.phase.value}, Page {progress.current_page}/{progress.total_pages}, Progress: {progress.percentage:.1f}%, Message: {progress.message}")


# Initialize converter
converter = PDF2Markdown4LLM(remove_headers=False, table_header="### Table", progress_callback=progress_callback)


# Convert PDF to Markdown
markdown_content = converter.convert("input.pdf")

# Save to file
with open("output.md", "w", encoding="utf-8") as md_file:
    md_file.write(markdown_content)
```

## Configuration Options

- `remove_headers`: Boolean flag to remove existing markdown headers from text (default: False)
- `table_header`: String to specify the header level for tables (default: "###")

## Key Components

### FontSizeClassifier

Analyzes font sizes throughout the document to determine appropriate header levels:
- Automatically identifies the normal text size
- Classifies larger fonts into appropriate header levels
- Handles font size variations and inconsistencies

### PDFContentExtractor

Extracts content while preserving structure:
- Processes text and tables separately
- Maintains original document flow
- Validates table boundaries
- Handles nested content

### MarkdownConverter

Converts extracted content to clean Markdown:
- Proper table formatting
- Header level preservation
- Clean text formatting

## Error Handling

The library includes comprehensive error handling:
- Validates table boundaries
- Checks for invalid content
- Provides detailed error messages
- Includes stack traces for debugging

## Contributing

Contributions are welcome! Please feel free to submit pull requests.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/new-feature`)
3. Commit your changes (`git commit -am 'Add new feature'`)
4. Push to the branch (`git push origin feature/new-feature`)
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

[HawkClaws]

## Acknowledgements

- PDFPlumber team for the excellent PDF parsing library
- Contributors and maintainers