from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Union, Callable
from collections import Counter
import re
import pdfplumber
from pdfplumber.page import Page
from pdfplumber.table import Table
from enum import Enum
import unicodedata

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

Content = Union[TextContent, TableContent]
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

class LigatureHandler:
    """Handles ligature normalization and character encoding issues in PDF text extraction."""
    
    def __init__(self, normalization_mode: str = 'NFKD'):
        self.normalization_mode = normalization_mode
        
    def normalize_text(self, text: str) -> str:
        """
        Normalize text by handling ligatures and applying Unicode normalization.
        
        Args:
            text: Input text to normalize
            normalization_mode: Unicode normalization mode ('NFC', 'NFKC', 'NFD', 'NFKD')
        
        Returns:
            Normalized text with expanded ligatures
        """
        if not text:
            return text
            
        # Apply Unicode normalization
        text = unicodedata.normalize(self.normalization_mode, text)
        
        # Remove NULL bytes
        text = text.replace('\x00', '')
        
        return text

    def clean_extracted_text(self, text: str, remove_control_chars: bool = True) -> str:
        """
        Clean extracted text by removing problematic characters and normalizing content.
        
        Args:
            text: Input text to clean
            remove_control_chars: Whether to remove control characters
            
        Returns:
            Cleaned text
        """
        if not text:
            return text
            
        # Normalize text with NFKD (recommended for most cases)
        text = self.normalize_text(text)
        
        if remove_control_chars:
            # Remove control characters except common whitespace
            text = ''.join(char for char in text 
                          if unicodedata.category(char)[0] != 'C' 
                          or char in ('\n', '\t', '\r'))
            
        return text

        
class PDFContentExtractor:
    def __init__(self, page: Page, size_to_level: Dict[float, str], normal_text_size: float, ligature_handler: LigatureHandler):
        self.page = page
        self.size_to_level = size_to_level
        self.normal_text_size = normal_text_size
        self.ligature_handler = ligature_handler

    @staticmethod
    def sanitize_cell(cell: Optional[str]) -> str:
        """Clean up table cell content."""
        if cell is None:
            return ""
        return ' '.join(str(cell).split())

    def _process_text_line(self, text: str, size: float, top: float, fontname: Optional[str]) -> TextContent:
        """Process a line of text and create appropriate TextContent."""
        # Clean and normalize text before processing
        text = self.ligature_handler.clean_extracted_text(text)

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
                 skip_empty_tables: bool = False, 
                 keep_empty_table_header: bool = False,
                 progress_callback: Optional[ProgressCallback] = None,
                 normalization_mode: Optional[str] = 'NFKD',):
        """
        Initialize PDF to Markdown converter with configurable ligature handling.
        
        Args:
            remove_headers: Whether to remove headers from the output
            table_header: Header level for tables
            skip_empty_tables: Whether to skip empty tables
            keep_empty_table_header: Whether to keep headers for empty tables
            progress_callback: Callback function for progress updates
            ligature_handler: Custom LigatureHandler instance
            custom_ligatures: Dictionary of custom ligature mappings to add/override
        """
        self.remove_headers = remove_headers
        self.table_header = table_header
        self.skip_empty_tables = skip_empty_tables
        self.keep_empty_table_header = keep_empty_table_header
        self.markdown_converter = MarkdownConverter()
        self.progress_callback = progress_callback
        self.ligature_handler = LigatureHandler(normalization_mode=normalization_mode)


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
    
    def convert(self, pdf_path: str) -> str:
        """Convert PDF to Markdown with detailed progress tracking."""
        with pdfplumber.open(pdf_path) as pdf:
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
            md_content: List[str] = []
            total_pages = len(pdf.pages)
            
            for i, page in enumerate(pdf.pages, 1):
                progress_info = self._create_progress_info(
                    phase=ProcessPhase.CONVERSION,
                    current_page=i,
                    total_pages=total_pages,
                    message=f"Converting content to Markdown"
                )
                self._report_progress(progress_info)
                
                extractor = PDFContentExtractor(
                    page, 
                    classifier.size_to_level, 
                    classifier.normal_text_size,
                    ligature_handler=self.ligature_handler
                )
                contents = extractor.extract_contents()
                
                for content in contents:
                    if isinstance(content, TextContent):
                        text = content.text.strip()
                        if text:
                            if self.remove_headers:
                                text = self.markdown_converter.remove_markdown_headers(text)
                            
                            if content.is_header:
                                md_content.append(f"\n{content.level} {text}\n\n")
                            else:
                                md_content.append(f"{text}\n")
                    elif isinstance(content, TableContent):
                        # Check for empty tables and skip according to settings
                        if self.skip_empty_tables and self._is_table_empty(content.table):
                            md_content.append(self._process_empty_table())
                            continue
                        
                        md_content.append(
                            self.ligature_handler.clean_extracted_text(
                                self.markdown_converter.table_to_markdown(
                                    content.table, 
                                    self.table_header
                                )
                            )
                        )
            
            # Final progress report
            completion_progress = self._create_progress_info(
                phase=ProcessPhase.CONVERSION,
                current_page=total_pages,
                total_pages=total_pages,
                message="Conversion complete"
            )
            self._report_progress(completion_progress)
            
            return "".join(md_content)

