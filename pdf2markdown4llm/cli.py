#!/usr/bin/env python3
"""
PDF to Markdown Converter Command Line Tool

This tool converts PDF files to Markdown format, with options for extracting images,
controlling page demarcation, and other formatting options.
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List, Optional
from pdf2markdown4llm import PDF2Markdown4LLM, ProgressInfo

def progress_callback(progress: ProgressInfo) -> None:
    """Callback function to display progress information."""
    print(f"\r{progress.phase.value.capitalize()}: Page {progress.current_page}/{progress.total_pages} - {progress.percentage:.1f}% - {progress.message}", end="")
    if progress.percentage >= 100:
        print()  # Add newline at the end

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert PDF files to Markdown format with options for image extraction and page demarcation."
    )
    
    # Input and output options
    parser.add_argument(
        "input_files", 
        nargs="+", 
        help="One or more PDF files to convert"
    )
    parser.add_argument(
        "-o", "--output-dir", 
        help="Output directory (default: same as input file)"
    )
    
    # Image extraction options
    parser.add_argument(
        "-n", "--no-images", 
        action="store_true", 
        help="Disable image extraction (default: extract images)"
    )
    
    # Page demarcation options
    parser.add_argument(
        "-p", "--page-demarcation", 
        choices=["none", "rule", "split"], 
        default="none",
        help="Page demarcation style: none (default), rule (horizontal rule with page number), or split (separate files per page)"
    )
    
    # Formatting options
    parser.add_argument(
        "--remove-headers", 
        action="store_true", 
        help="Remove headers from the output"
    )
    parser.add_argument(
        "--table-header", 
        default="###", 
        help="Header level for tables (default: ###)"
    )
    parser.add_argument(
        "--skip-empty-tables", 
        action="store_true", 
        help="Skip empty tables in the output"
    )
    parser.add_argument(
        "--keep-empty-table-header", 
        action="store_true", 
        help="Keep headers for empty tables when skipping them"
    )
    
    # Progress reporting
    parser.add_argument(
        "--no-progress", 
        action="store_true", 
        help="Disable progress reporting"
    )
    
    return parser.parse_args()

def convert_pdf_to_markdown(
    input_file: str,
    output_dir: Optional[str] = None,
    extract_images: bool = True,
    page_demarcation: str = "none",
    remove_headers: bool = False,
    table_header: str = "###",
    skip_empty_tables: bool = False,
    keep_empty_table_header: bool = False,
    show_progress: bool = True
) -> None:
    """
    Convert a PDF file to Markdown format with the specified options.
    
    Args:
        input_file: Path to the input PDF file
        output_dir: Directory to save the output files (default: same as input file)
        extract_images: Whether to extract images from the PDF
        page_demarcation: Page demarcation style ("none", "rule", or "split")
        remove_headers: Whether to remove headers from the output
        table_header: Header level for tables
        skip_empty_tables: Whether to skip empty tables
        keep_empty_table_header: Whether to keep headers for empty tables
        show_progress: Whether to show progress information
    """
    # Validate input file
    if not os.path.isfile(input_file):
        print(f"Error: Input file '{input_file}' does not exist.")
        return
    
    # Determine output directory and filename
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        output_base = os.path.splitext(os.path.basename(input_file))[0]
        output_file = os.path.join(output_dir, f"{output_base}.md")
    else:
        output_dir = os.path.dirname(os.path.abspath(input_file))
        output_base = os.path.splitext(os.path.basename(input_file))[0]
        output_file = os.path.join(output_dir, f"{output_base}.md")
    
    # Initialize converter with options
    converter = PDF2Markdown4LLM(
        remove_headers=remove_headers,
        table_header=table_header,
        skip_empty_tables=skip_empty_tables,
        keep_empty_table_header=keep_empty_table_header,
        progress_callback=progress_callback if show_progress else None,
        extract_images=extract_images,
        page_demarcation=page_demarcation,
        output_dir=output_dir
    )
    
    try:
        # Convert PDF to Markdown
        print(f"Converting {input_file} to Markdown...")
        markdown_content = converter.convert(input_file, output_file)
        
        # Save to file if not using split mode (split mode saves files automatically)
        if page_demarcation != "split":
            with open(output_file, "w", encoding="utf-8") as md_file:
                md_file.write(markdown_content)
            print(f"Saved Markdown to {output_file}")
        else:
            print(f"Saved Markdown pages to {os.path.splitext(output_file)[0]}_page*.md")
        
        # Report image extraction if enabled
        if extract_images:
            media_dir = f"{os.path.join(output_dir, output_base)}_media"
            if os.path.exists(media_dir) and os.listdir(media_dir):
                print(f"Extracted images to {media_dir}")
    
    except Exception as e:
        print(f"Error converting {input_file}: {e}")

def main() -> None:
    """Main entry point for the command-line tool."""
    args = parse_arguments()
    
    for input_file in args.input_files:
        convert_pdf_to_markdown(
            input_file=input_file,
            output_dir=args.output_dir,
            extract_images=not args.no_images,
            page_demarcation=args.page_demarcation,
            remove_headers=args.remove_headers,
            table_header=args.table_header,
            skip_empty_tables=args.skip_empty_tables,
            keep_empty_table_header=args.keep_empty_table_header,
            show_progress=not args.no_progress
        )

if __name__ == "__main__":
    main()
