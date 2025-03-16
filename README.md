# PDF2Markdown4LLM

PDF2Markdown4LLM is a Python library that converts PDF documents to Markdown format, specifically optimized for Large Language Models (LLMs). It intelligently preserves document structure, identifies headers based on font sizes, and handles tables while maintaining the original document flow.


## Demo
[demo](https://huggingface.co/spaces/HawkClaws/pdf2markdown4llm_demo)

## Features

- Intelligent header detection based on font size analysis
- Table extraction and conversion to Markdown format
- Image extraction with page number tracking
- Multiple page demarcation options (none, horizontal rule, or split files)
- Maintains document structure and flow
- Handles nested content and complex layouts
- Font size classification for consistent header levels
- Clean table formatting with proper alignment
- Optional header removal functionality
- Command-line interface for easy use
- Robust error handling and validation

## Installation

```bash
pip install pdf2markdown4llm
```

## Dependencies

- pdfplumber
- pdfminer.six[image] (for robust image extraction)
- pillow (PIL)
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
converter = PDF2Markdown4LLM(remove_headers=False, skip_empty_tables=True, table_header="### Table", progress_callback=progress_callback)


# Convert PDF to Markdown
markdown_content = converter.convert("input.pdf")

# Save to file
with open("output.md", "w", encoding="utf-8") as md_file:
    md_file.write(markdown_content)
```

## Configuration Options

- `remove_headers`: Boolean flag to remove existing markdown headers from text (default: False)
- `table_header`: String to specify the header level for tables (default: "###")
- `skip_empty_tables`: Boolean flag to skip empty tables in the output (default: False)
- `keep_empty_table_header`: Boolean flag to keep headers for empty tables when skipping them (default: False)
- `extract_images`: Boolean flag to extract images from the PDF (default: True)
- `page_demarcation`: How to mark page boundaries (default: "none")
  - "none": No page demarcation
  - "rule": Add horizontal rule with page number between pages
  - "split": Split output into separate files per page
- `output_dir`: Directory to save extracted images and split page files (default: same directory as output file)

## Advanced Usage

### Image Extraction

```python
from pdf2markdown4llm import PDF2Markdown4LLM

# Initialize converter with image extraction enabled
converter = PDF2Markdown4LLM(
    extract_images=True,
    output_dir="/path/to/output/directory"  # Optional
)

# Convert PDF to Markdown with images
markdown_content = converter.convert("input.pdf", "output.md")
```

Images will be extracted to a directory named `{output_filename}_media` alongside the markdown file.

### Page Demarcation

```python
from pdf2markdown4llm import PDF2Markdown4LLM

# Initialize converter with page demarcation
converter = PDF2Markdown4LLM(
    page_demarcation="rule"  # Options: "none", "rule", "split"
)

# Convert PDF to Markdown with page demarcation
markdown_content = converter.convert("input.pdf", "output.md")
```

## Command-Line Tool

PDF2Markdown4LLM includes a command-line tool (`pdf2md`) for easy conversion of PDF files to Markdown.

```bash
# Basic usage
pdf2md input.pdf

# Convert multiple PDFs
pdf2md file1.pdf file2.pdf file3.pdf

# Specify output directory
pdf2md input.pdf -o /path/to/output/directory

# Enable image extraction (enabled by default)
pdf2md input.pdf

# Disable image extraction
pdf2md input.pdf -n  # or --no-images

# Set page demarcation style
pdf2md input.pdf -p rule  # or --page-demarcation rule (Options: none, rule, split)

# Additional options
pdf2md input.pdf --remove-headers --skip-empty-tables --table-header "##"
```

For a complete list of options, run:

```bash
pdf2md --help
```

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
