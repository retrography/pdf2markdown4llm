from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Union, Callable
from collections import Counter
from operator import itemgetter
import re
import pdfplumber
from pdfplumber.page import Page
from pdfplumber.table import Table
import traceback

ProgressCallback = Callable[[float, str], None]

@dataclass
class TextContent:
    text: str
    top: float
    is_header: bool
    level: Optional[str] = None

@dataclass
class TableContent:
    table: Table
    top: float

Content = Union[TextContent, TableContent]

def round_font_size(size: float) -> float:
    """Round font size to one decimal place."""
    return round(size, 1)

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

    def _process_text_line(self, text: str, size: float, top: float) -> TextContent:
        """Process a line of text and create appropriate TextContent."""
        rounded_size = round_font_size(size)
        if rounded_size == self.normal_text_size:
            return TextContent(text=text, top=top, is_header=False)
        
        level = self.size_to_level.get(rounded_size, "")
        return TextContent(
            text=text,
            top=top,
            is_header=bool(level),
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
                continue  # Skip tables that cause bounding box errors
        
        # Process text content
        words = non_table_content.extract_words(extra_attrs=["size"])
        current_line: List[str] = []
        current_size: Optional[float] = None
        current_top: Optional[float] = None
        
        for word in words:
            if current_top is None:
                current_top = word["top"]
                current_size = round_font_size(word["size"])  # Round size when setting
                current_line = [word["text"]]
            elif abs(word["top"] - current_top) <= 3:  # Same line
                current_line.append(word["text"])
            else:  # New line
                if current_size is not None and current_top is not None:
                    text = " ".join(current_line)
                    contents.append(self._process_text_line(text, current_size, current_top))
                
                current_top = word["top"]
                current_size = round_font_size(word["size"])  # Round size when setting
                current_line = [word["text"]]
        
        # Process last line if exists
        if current_line and current_size is not None and current_top is not None:
            text = " ".join(current_line)
            contents.append(self._process_text_line(text, current_size, current_top))
        
        # Add valid tables
        for table in valid_tables:
            contents.append(TableContent(table=table, top=table.bbox[1]))
        
        return sorted(contents, key=lambda x: x.top)

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
                 progress_callback: Optional[ProgressCallback] = None):
        self.remove_headers = remove_headers
        self.table_header = table_header
        self.markdown_converter = MarkdownConverter()
        self.progress_callback = progress_callback

    def _report_progress(self, progress: float, message: str) -> None:
        """Report progress through the callback if it exists."""
        if self.progress_callback:
            self.progress_callback(progress, message)

    def _collect_font_statistics(self, pdf) -> Tuple[List[float], Counter]:
        """Collect font statistics from PDF with progress tracking."""
        font_sizes: List[float] = []
        font_size_text_count = Counter()
        total_pages = len(pdf.pages)
        
        for i, page in enumerate(pdf.pages):
            # Report progress for first phase (0-50%)
            progress = (i / total_pages) * 50
            self._report_progress(progress, f"Analyzing fonts: page {i + 1}/{total_pages}")
            
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

    def convert(self, pdf_path: str) -> str:
        """Convert PDF to Markdown with progress tracking."""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                self._report_progress(0, "Starting conversion...")
                
                font_sizes, font_size_text_count = self._collect_font_statistics(pdf)
                
                if not font_sizes:
                    raise ValueError("No text found in the PDF.")
                
                self._report_progress(50, "Font analysis complete, starting content extraction...")
                
                classifier = FontSizeClassifier(font_sizes, font_size_text_count)
                md_content: List[str] = []
                total_pages = len(pdf.pages)
                
                for i, page in enumerate(pdf.pages, 1):
                    # Report progress for second phase (50-100%)
                    progress = 50 + (i / total_pages) * 50
                    self._report_progress(progress, f"Converting page {i}/{total_pages}")
                    
                    extractor = PDFContentExtractor(
                        page, 
                        classifier.size_to_level, 
                        classifier.normal_text_size
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
                            md_content.append(
                                self.markdown_converter.table_to_markdown(
                                    content.table, 
                                    self.table_header
                                )
                            )
                
                self._report_progress(100, "Conversion complete!")
                
                return "".join(md_content)
                
        except Exception as e:
            raise RuntimeError(f"Failed to convert PDF to Markdown: {str(e)} traceback: {traceback.format_exc()}")

