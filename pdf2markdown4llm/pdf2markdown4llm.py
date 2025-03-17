from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Union, Callable, Literal
from collections import Counter
import re
import os
import io
import csv
import json
from pathlib import Path
from PIL import Image
import pdfplumber
from pdfplumber.page import Page
from pdfplumber.table import Table
from pdfminer.layout import LTImage, LTFigure
from pdfminer.high_level import extract_pages
from pdfminer.image import ImageWriter
from enum import Enum

class ProcessPhase(Enum):
    ANALYSIS = "analysis"
    CONVERSION = "conversion"

@dataclass
class ProgressInfo:
    """Progress information for PDF processing."""
    phase: ProcessPhase
    current_page: int
    total_pages: int
    percentage: float
    message: str

@dataclass
class TextStyle:
    """Text style information."""
    is_bold: bool = False
    font_name: Optional[str] = None

@dataclass
class TextContent:
    text: str
    top: float
    is_header: bool
    style: TextStyle
    level: Optional[str] = None

@dataclass
class TableContent:
    table: Table
    top: float

@dataclass
class ImageContent:
    """Image content information."""
    image_path: str  # Path to the saved image file
    alt_text: str    # Alternative text for the image
    top: float       # Position on the page
    page_num: int    # Page number where the image appears

Content = Union[TextContent, TableContent, ImageContent]
ProgressCallback = Callable[[ProgressInfo], None]


def round_font_size(size: float) -> float:
    """Round font size to one decimal place."""
    return round(size, 1)

def is_bold_font(fontname: Optional[str]) -> bool:
    """
    Determine if a font is bold based on its name.
    Uses stricter rules to prevent over-detection of bold text.
    """
    if not fontname:
        return False
    
    # Convert font name to lowercase for comparison
    fontname_lower = fontname.lower()
    
    # Common bold font name patterns
    bold_indicators = {
        'bold',      # Most common indicator
        '-bold',     # Often used with hyphen
        '.bold',     # Sometimes used with dot
        ' bold',     # Used with space
    }
    
    # Exclude certain terms that might contain 'bold' but aren't necessarily bold
    exclude_terms = {
        'semibold',  # Usually lighter than true bold
        'demibold',  # Usually lighter than true bold
        'book',      # Regular weight
        'light',     # Light weight
        'regular',   # Regular weight
    }
    
    # First check if any exclusion terms are in the font name
    if any(term in fontname_lower for term in exclude_terms):
        return False
    
    # Then check for bold indicators
    return any(indicator in fontname_lower for indicator in bold_indicators)

class FontSizeClassifier:
    def __init__(self, font_sizes: List[float], font_size_counts: Counter):
        # Round font sizes when initializing
        self.font_sizes = [round_font_size(size) for size in font_sizes]
        # Create new Counter with rounded font sizes
        rounded_counts = Counter()
        for size, count in font_size_counts.items():
            rounded_counts[round_font_size(size)] += count
        self.font_size_counts = rounded_counts
        self.size_to_level: Dict[float, str] = {}
        self.normal_text_size: float = 0
        self._classify()

    def _calculate_size_ratios(self, larger_sizes: List[float]) -> Tuple[float, float]:
        """Calculate average ratio and standard deviation between consecutive font sizes."""
        size_ratios = [larger_sizes[i] / larger_sizes[i + 1] 
                      for i in range(len(larger_sizes) - 1)]
        
        if not size_ratios:
            return 0, 0
            
        avg_ratio = sum(size_ratios) / len(size_ratios)
        ratio_std = (sum((r - avg_ratio) ** 2 for r in size_ratios) / len(size_ratios)) ** 0.5
        
        return avg_ratio, ratio_std

    def _classify(self) -> None:
        """Classify font sizes into heading levels."""
        if not self.font_sizes:
            return

        unique_sizes = sorted(set(self.font_sizes), reverse=True)
        if len(unique_sizes) <= 1:
            self.normal_text_size = unique_sizes[0]
            return

        self.normal_text_size = self.font_size_counts.most_common(1)[0][0]
        larger_sizes = [size for size in unique_sizes if size > self.normal_text_size]
        
        if not larger_sizes:
            return

        avg_ratio, ratio_std = self._calculate_size_ratios(larger_sizes)
        if avg_ratio == 0:
            return

        min_diff_ratio = max(1.02, min(1.15, avg_ratio - ratio_std))
        
        # Identify headers
        heading_sizes = []
        current_size = max(larger_sizes)
        heading_sizes.append(current_size)
        
        for size in larger_sizes[1:]:
            ratio = current_size / size
            if ratio >= min_diff_ratio:
                heading_sizes.append(size)
                current_size = size
                if len(heading_sizes) >= 6:
                    break

        # Map sizes to markdown header levels
        levels = ["#", "##", "###", "####", "#####", "######"]
        self.size_to_level = {
            size: level for size, level in zip(heading_sizes, levels)
        }
    
class PDFContentExtractor:
    def __init__(self, page: Page, size_to_level: Dict[float, str], normal_text_size: float):
        self.page = page
        self.size_to_level = size_to_level
        self.normal_text_size = normal_text_size

    @staticmethod
    def sanitize_cell(cell: Optional[str]) -> str:
        """Clean up table cell content."""
        if cell is None:
            return ""
        return ' '.join(str(cell).split())

    def _process_text_line(self, text: str, size: float, top: float, fontname: Optional[str]) -> TextContent:
        """Process a line of text and create appropriate TextContent."""

        rounded_size = round_font_size(size)
        style = TextStyle(is_bold=is_bold_font(fontname), font_name=fontname)
        
        if rounded_size == self.normal_text_size:
            return TextContent(text=text, top=top, is_header=False, style=style)
        
        level = self.size_to_level.get(rounded_size, "")
        return TextContent(
            text=text,
            top=top,
            is_header=bool(level),
            style=style,
            level=level
        )

    def _is_valid_table(self, table: Table) -> bool:
        """Check if table bounds are within page bounds."""
        page_bbox = self.page.bbox
        table_bbox = table.bbox
        
        return (table_bbox[0] >= 0 and table_bbox[1] >= 0 and 
                table_bbox[2] <= page_bbox[2] and 
                table_bbox[3] <= page_bbox[3])

    def extract_contents(self) -> List[Content]:
        """Extract text and table content from a page while preserving order."""
        contents: List[Content] = []
        tables = self.page.find_tables()
        valid_tables = [table for table in tables if self._is_valid_table(table)]
        
        # Extract non-table content
        non_table_content = self.page
        for table in valid_tables:
            try:
                non_table_content = non_table_content.outside_bbox(table.bbox)
            except ValueError:
                continue
        
        # Process text content with font information
        words = non_table_content.extract_words(extra_attrs=["size", "fontname"])
        current_line: List[Tuple[str, Optional[str]]] = []  # (text, fontname)
        current_size: Optional[float] = None
        current_top: Optional[float] = None
        
        for word in words:
            if current_top is None:
                current_top = word["top"]
                current_size = round_font_size(word["size"])
                current_line = [(word["text"], word.get("fontname"))]
            elif abs(word["top"] - current_top) <= 3:  # Same line
                current_line.append((word["text"], word.get("fontname")))
            else:  # New line
                if current_size is not None and current_top is not None:
                    # Process line with mixed styles
                    processed_text = self._process_mixed_styles(current_line)
                    contents.append(self._process_text_line(
                        processed_text,
                        current_size,
                        current_top,
                        current_line[0][1]  # Use first word's font as reference
                    ))
                
                current_top = word["top"]
                current_size = round_font_size(word["size"])
                current_line = [(word["text"], word.get("fontname"))]
        
        # Process last line if exists
        if current_line and current_size is not None and current_top is not None:
            processed_text = self._process_mixed_styles(current_line)
            contents.append(self._process_text_line(
                processed_text,
                current_size,
                current_top,
                current_line[0][1]
            ))
        
        # Add valid tables
        for table in valid_tables:
            contents.append(TableContent(table=table, top=table.bbox[1]))
        
        return sorted(contents, key=lambda x: x.top)

    def _process_mixed_styles(self, line: List[Tuple[str, Optional[str]]]) -> str:
        """Process a line with mixed text styles."""
        result = []
        current_bold = False
        current_text = []

        for text, fontname in line:
            is_bold = is_bold_font(fontname)
            
            if is_bold != current_bold:
                if current_text:
                    text_segment = " ".join(current_text)
                    if current_bold:
                        result.append(f"**{text_segment}**")
                    else:
                        result.append(text_segment)
                    current_text = []
                current_bold = is_bold
            
            current_text.append(text)
        
        # Process remaining text
        if current_text:
            text_segment = " ".join(current_text)
            if current_bold:
                result.append(f"**{text_segment}**")
            else:
                result.append(text_segment)
        
        return " ".join(result)

class MarkdownConverter:
    @staticmethod
    def remove_markdown_headers(text: str) -> str:
        """Remove existing markdown headers from text."""
        return re.sub(r'^#+\s*', '', text.strip())

    @staticmethod
    def table_to_markdown(table: Table, header: str = "###") -> str:
        """Convert a table to Markdown format."""
        unsanitized_table = table.extract()
        sanitized_table = [[PDFContentExtractor.sanitize_cell(cell) for cell in row] 
                          for row in unsanitized_table]
        
        if not sanitized_table:
            return ""
        
        markdown_lines = []
        
        if sanitized_table[0] and sanitized_table[0][0].strip():
            markdown_lines.extend([
                f"{header}",
                ""
            ])
        
        # Create table structure
        markdown_lines.extend([
            '| ' + ' | '.join(sanitized_table[0]) + ' |',
            '|' + '|'.join(':---:' for _ in sanitized_table[0]) + '|'
        ])
        
        # Add data rows
        markdown_lines.extend(
            '| ' + ' | '.join(row) + ' |'
            for row in sanitized_table[1:]
        )
        
        return '\n'.join(markdown_lines) + '\n\n'

class PDF2Markdown4LLM:
    def __init__(self, 
                 remove_headers: bool = False, 
                 table_header: str = "###",
                 skip_empty_tables: bool = True, 
                 keep_empty_table_header: bool = False,
                 progress_callback: Optional[ProgressCallback] = None,
                 normalization_mode: Optional[Literal["NFC", "NFKC", "NFD", "NFKD"]] = "NFKD",
                 extract_images: bool = True,
                 page_demarcation: Literal["none", "rule", "split"] = "none",
                 output_dir: Optional[str] = None,
                 table_export_format: Optional[Literal["csv", "json"]] = None):
        """
        Initialize PDF to Markdown converter with configurable options.
        
        Args:
            remove_headers: Whether to remove headers from the output
            table_header: Header level for tables
            skip_empty_tables: Whether to skip empty tables
            keep_empty_table_header: Whether to keep headers for empty tables
            progress_callback: Callback function for progress updates
            normalization_mode: Unicode normalization mode for text extraction
            extract_images: Whether to extract images from the PDF
            page_demarcation: How to mark page boundaries:
                - "none": No page demarcation (default)
                - "rule": Add horizontal rule with page number between pages
                - "split": Split output into separate files per page
            output_dir: Directory to save extracted images and split page files
                        (defaults to same directory as output file)
            table_export_format: Format to export tables (None, "csv", or "json")
                                Tables will be exported to the media directory
        """
        self.extract_images = extract_images
        self.page_demarcation = page_demarcation
        self.output_dir = output_dir
        self.remove_headers = remove_headers
        self.table_header = table_header
        self.skip_empty_tables = skip_empty_tables
        self.keep_empty_table_header = keep_empty_table_header
        self.markdown_converter = MarkdownConverter()
        self.progress_callback = progress_callback
        self.normalization_mode = normalization_mode
        self.table_export_format = table_export_format

    def _is_table_empty(self, table: Table) -> bool:
        """
        Checks if the table is empty.
        
        An empty table is defined as:
        1. Having no cells
        2. All cells are empty (None, empty string, or whitespace)
        3. Table data (extracted content) is empty
        """
        try:
            # Check if table has no cells
            if not table.cells:
                return True
            
            def is_cell_empty(cell) -> bool:
                """
                Checks if a single cell is empty.
                
                - None is considered empty
                - Numeric types (int, float) are considered non-empty
                - For dictionaries, the 'text' key's stripped value determines emptiness
                - Strings are empty if stripped value is empty
                - Other types are evaluated by converting to string and stripping
                """
                if cell is None:
                    return True
                
                if isinstance(cell, (int, float)):
                    return False  # Numbers are always considered non-empty
                
                if isinstance(cell, dict):
                    return not cell.get('text', '').strip()
                
                if isinstance(cell, str):
                    return not cell.strip()
                
                try:
                    return not str(cell).strip()
                except Exception:
                    return True

            # Extract table data and check if it's empty
            table_data = table.extract()
            if not table_data:
                return True

            # Check if all rows are empty
            if all(not any(row) for row in table_data):
                return True

            # Check the actual content of cells
            return all(
                is_cell_empty(cell)
                for row in table_data
                for cell in row
            )

        except Exception as e:
            # Log error if needed
            # print(f"Error in _is_table_empty: {e}")
            return False  # Default to considering the table non-empty in case of error
        
    def _create_progress_info(self, 
                            phase: ProcessPhase, 
                            current_page: int, 
                            total_pages: int, 
                            message: str) -> ProgressInfo:
        """Create a ProgressInfo object with calculated percentage."""
        if phase == ProcessPhase.ANALYSIS:
            # Analysis phase goes from 0% to 70%
            total_percentage = (current_page / total_pages) * 70
        else:
            # Conversion phase goes from 70% to 100%
            # Start at 70% and progress through remaining 30%
            total_percentage = 70 + ((current_page / total_pages) * 30)
        
        return ProgressInfo(
            phase=phase,
            current_page=current_page,
            total_pages=total_pages,
            percentage=total_percentage,
            message=message
        )

    def _report_progress(self, progress_info: ProgressInfo) -> None:
        """Report progress through the callback if it exists."""
        if self.progress_callback:
            self.progress_callback(progress_info)

    def _collect_font_statistics(self, pdf) -> Tuple[List[float], Counter]:
        """Collect font statistics from PDF with progress tracking."""
        font_sizes: List[float] = []
        font_size_text_count = Counter()
        total_pages = len(pdf.pages)
        
        for i, page in enumerate(pdf.pages):
            progress_info = self._create_progress_info(
                phase=ProcessPhase.ANALYSIS,
                current_page=i + 1,
                total_pages=total_pages,
                message=f"Analyzing"
            )
            self._report_progress(progress_info)
            
            tables = page.find_tables()
            non_table_content = page
            
            for table in tables:
                try:
                    if (table.bbox[0] >= 0 and table.bbox[1] >= 0 and 
                        table.bbox[2] <= page.bbox[2] and 
                        table.bbox[3] <= page.bbox[3]):
                        non_table_content = non_table_content.outside_bbox(table.bbox)
                except ValueError:
                    continue
            
            words = non_table_content.extract_words(extra_attrs=["size"])
            font_sizes.extend(round_font_size(word["size"]) for word in words)
            for word in words:
                font_size_text_count[round_font_size(word["size"])] += len(word["text"])
        
        return font_sizes, font_size_text_count
    
    def _process_empty_table(self) -> str:
        """
        Handles the header processing when dealing with an empty table.
        """
        if self.keep_empty_table_header:
            return f"{self.table_header}\n\n"  # Returns only the header.
        return ""  # Returns an empty string if skipping completely.
    
    def _extract_images(self, pdf_path: str, output_dir: str) -> Dict[int, List[ImageContent]]:
        """
        Extract images from PDF using pdfminer.six's ImageWriter.
        
        Args:
            pdf_path: Path to the PDF file
            output_dir: Directory to save extracted images
            
        Returns:
            Dictionary mapping page numbers to lists of ImageContent objects
        """
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Dictionary to store images by page
        images_by_page: Dict[int, List[ImageContent]] = {}
        
        # Create a temporary directory for initial image extraction
        temp_dir = os.path.join(output_dir, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Create an ImageWriter instance
        image_writer = ImageWriter(temp_dir)
        
        # Process each page
        for i, page_layout in enumerate(extract_pages(pdf_path)):
            page_num = i + 1
            page_images = []
            
            # Process each element on the page
            for element in page_layout:
                # Check if element is an image
                if isinstance(element, LTImage):
                    try:
                        # Use ImageWriter to save the image
                        image_filename = image_writer.export_image(element)
                        temp_image_path = os.path.join(temp_dir, image_filename)
                        
                        # Get file extension
                        _, ext = os.path.splitext(image_filename)
                        
                        # Create new filename with page prefix
                        new_filename = f"page{page_num}_{image_filename}"
                        new_image_path = os.path.join(output_dir, new_filename)
                        
                        # Copy the file to the output directory with the new name
                        with open(temp_image_path, 'rb') as src, open(new_image_path, 'wb') as dst:
                            dst.write(src.read())
                        
                        # Create ImageContent object
                        image_content = ImageContent(
                            image_path=new_image_path,
                            alt_text=f"Image from page {page_num}",
                            top=element.y0,
                            page_num=page_num
                        )
                        page_images.append(image_content)
                    except Exception as e:
                        # Skip images that can't be processed
                        continue
                
                # Check if element is a figure (might contain images)
                elif isinstance(element, LTFigure):
                    for figure_element in element:
                        if isinstance(figure_element, LTImage):
                            try:
                                # Use ImageWriter to save the image
                                image_filename = image_writer.export_image(figure_element)
                                temp_image_path = os.path.join(temp_dir, image_filename)
                                
                                # Get file extension
                                _, ext = os.path.splitext(image_filename)
                                
                                # Create new filename with page prefix
                                new_filename = f"page{page_num}_{image_filename}"
                                new_image_path = os.path.join(output_dir, new_filename)
                                
                                # Copy the file to the output directory with the new name
                                with open(temp_image_path, 'rb') as src, open(new_image_path, 'wb') as dst:
                                    dst.write(src.read())
                                
                                # Create ImageContent object
                                image_content = ImageContent(
                                    image_path=new_image_path,
                                    alt_text=f"Figure from page {page_num}",
                                    top=figure_element.y0,
                                    page_num=page_num
                                )
                                page_images.append(image_content)
                            except Exception as e:
                                # Skip images that can't be processed
                                continue
            
            # Store images for this page
            if page_images:
                images_by_page[page_num] = sorted(page_images, key=lambda x: x.top)
        
        # Clean up temporary directory
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        return images_by_page
    
    def _export_table_to_csv(self, table: Table, filepath: str) -> None:
        """
        Export a table to CSV format.
        
        Args:
            table: The table to export
            filepath: Path to save the CSV file
        """
        table_data = table.extract()
        if not table_data:
            return
        
        # Sanitize table data
        sanitized_table = [[PDFContentExtractor.sanitize_cell(cell) for cell in row] 
                          for row in table_data]
        
        # Write to CSV file
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            for row in sanitized_table:
                writer.writerow(row)
    
    def _export_table_to_json(self, table: Table, filepath: str) -> None:
        """
        Export a table to JSON format.
        
        Args:
            table: The table to export
            filepath: Path to save the JSON file
        """
        table_data = table.extract()
        if not table_data or len(table_data) < 2:  # Need at least headers and one row
            return
        
        # Sanitize table data
        sanitized_table = [[PDFContentExtractor.sanitize_cell(cell) for cell in row] 
                          for row in table_data]
        
        # Get headers from first row
        headers = sanitized_table[0]
        
        # Convert to list of dictionaries
        json_data = []
        for row in sanitized_table[1:]:
            # Create a dictionary for each row, mapping headers to values
            row_dict = {}
            for i, header in enumerate(headers):
                # Use empty string for missing values
                value = row[i] if i < len(row) else ""
                row_dict[header] = value
            json_data.append(row_dict)
        
        # Write to JSON file
        with open(filepath, 'w', encoding='utf-8') as jsonfile:
            json.dump(json_data, jsonfile, indent=2, ensure_ascii=False)
    
    def _apply_page_demarcation(self, content: str, page_num: int, total_pages: int) -> str:
        """Apply page demarcation according to the selected option."""
        if self.page_demarcation == "none":
            return content
        elif self.page_demarcation == "rule":
            return f"\n\n---\n**Page {page_num} of {total_pages}**\n---\n\n{content}"
        else:
            # For "split" option, we just return the content as is
            # The actual splitting happens in the convert method
            return content
    
    def convert(self, pdf_path: str, output_path: Optional[str] = None) -> str:
        """
        Convert PDF to Markdown with detailed progress tracking.
        
        Args:
            pdf_path: Path to the PDF file
            output_path: Path to save the output markdown file (optional)
                         If not provided, the function will just return the markdown content
        
        Returns:
            Markdown content as a string
        """
        # Determine output directory for images and split files
        if output_path:
            output_dir = os.path.dirname(os.path.abspath(output_path))
            base_name = os.path.splitext(os.path.basename(output_path))[0]
        else:
            output_dir = os.path.dirname(os.path.abspath(pdf_path))
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        
        # Override with user-specified output directory if provided
        if self.output_dir:
            output_dir = self.output_dir
        
        # Create media directory for images
        media_dir = f"{os.path.join(output_dir, base_name)}_media"
        
        # Extract images if enabled
        images_by_page = {}
        if self.extract_images:
            progress_info = self._create_progress_info(
                phase=ProcessPhase.ANALYSIS,
                current_page=0,
                total_pages=1,
                message="Extracting images"
            )
            self._report_progress(progress_info)
            images_by_page = self._extract_images(pdf_path, media_dir)
        
        with pdfplumber.open(pdf_path, unicode_norm=self.normalization_mode) as pdf:
            # Initial progress report
            initial_progress = self._create_progress_info(
                phase=ProcessPhase.ANALYSIS,
                current_page=0,
                total_pages=len(pdf.pages),
                message="Starting PDF analysis"
            )
            self._report_progress(initial_progress)
            
            # Analyze font statistics
            font_sizes, font_size_text_count = self._collect_font_statistics(pdf)
            
            if not font_sizes:
                raise ValueError("No text found in the PDF.")
            
            # Report analysis completion
            analysis_complete = self._create_progress_info(
                phase=ProcessPhase.CONVERSION,
                current_page=0,
                total_pages=len(pdf.pages),
                message="Analysis complete, beginning content extraction"
            )
            self._report_progress(analysis_complete)
            
            classifier = FontSizeClassifier(font_sizes, font_size_text_count)
            total_pages = len(pdf.pages)
            
            # For split mode, we'll store content for each page separately
            if self.page_demarcation == "split":
                page_contents = {}
            else:
                # For other modes, we'll collect all content in a single list
                md_content: List[str] = []
            
            for i, page in enumerate(pdf.pages, 1):
                progress_info = self._create_progress_info(
                    phase=ProcessPhase.CONVERSION,
                    current_page=i,
                    total_pages=total_pages,
                    message=f"Converting content to Markdown"
                )
                self._report_progress(progress_info)
                
                # For split mode, create a new content list for this page
                if self.page_demarcation == "split":
                    page_md_content: List[str] = []
                    current_content = page_md_content
                else:
                    current_content = md_content
                
                # Add page demarcation if needed (except for first page in non-split mode)
                if self.page_demarcation == "rule" and i > 1:
                    current_content.append(f"\n\n---\n**Page {i} of {total_pages}**\n---\n\n")
                
                # Extract content from the page
                extractor = PDFContentExtractor(
                    page, 
                    classifier.size_to_level, 
                    classifier.normal_text_size,
                )
                contents = extractor.extract_contents()
                
                # Add extracted images for this page if available
                if self.extract_images and i in images_by_page:
                    # Merge images with other content and sort by position
                    contents.extend(images_by_page[i])
                    contents.sort(key=lambda x: x.top)
                
                # Process all content
                for content in contents:
                    if isinstance(content, TextContent):
                        text = content.text.strip()
                        if text:
                            if self.remove_headers:
                                text = self.markdown_converter.remove_markdown_headers(text)
                            
                            if content.is_header:
                                current_content.append(f"\n{content.level} {text}\n\n")
                            else:
                                current_content.append(f"{text}\n")
                    elif isinstance(content, TableContent):
                        # Check for empty tables and skip according to settings
                        if self.skip_empty_tables and self._is_table_empty(content.table):
                            current_content.append(self._process_empty_table())
                            continue
                        
                        # Export table to CSV or JSON if requested
                        if self.table_export_format:
                            # Create media directory if it doesn't exist
                            os.makedirs(media_dir, exist_ok=True)
                            
                            # Generate a unique filename for the table
                            table_index = len([f for f in os.listdir(media_dir) 
                                              if f.startswith(f"page{i}_table") and 
                                              f.endswith(f".{self.table_export_format}")])
                            
                            # Create the table filename with page number prefix
                            table_filename = f"page{i}_table{table_index + 1}.{self.table_export_format}"
                            table_filepath = os.path.join(media_dir, table_filename)
                            
                            # Export the table in the requested format
                            if self.table_export_format == "csv":
                                self._export_table_to_csv(content.table, table_filepath)
                            elif self.table_export_format == "json":
                                self._export_table_to_json(content.table, table_filepath)
                        
                        # Add table to markdown content
                        current_content.append(
                            self.markdown_converter.table_to_markdown(
                                    content.table, 
                                    self.table_header
                            )
                        )
                    elif isinstance(content, ImageContent):
                        # Add image reference to markdown
                        rel_path = os.path.relpath(content.image_path, output_dir)
                        current_content.append(f"\n![{content.alt_text}]({rel_path})\n\n")
                
                # For split mode, store the page content
                if self.page_demarcation == "split":
                    page_contents[i] = "".join(page_md_content).replace('\x00', '')
            
            # Final progress report
            completion_progress = self._create_progress_info(
                phase=ProcessPhase.CONVERSION,
                current_page=total_pages,
                total_pages=total_pages,
                message="Conversion complete"
            )
            self._report_progress(completion_progress)
            
            # Handle output based on page demarcation mode
            if self.page_demarcation == "split" and output_path:
                # Save each page to a separate file
                output_base = os.path.splitext(output_path)[0]
                for page_num, content in page_contents.items():
                    page_path = f"{output_base}_page{page_num}.md"
                    with open(page_path, "w", encoding="utf-8") as f:
                        f.write(content)
                
                # Return the content of the first page as a sample
                return page_contents.get(1, "")
            else:
                # For other modes, return the combined content
                return "".join(md_content).replace('\x00', '')
